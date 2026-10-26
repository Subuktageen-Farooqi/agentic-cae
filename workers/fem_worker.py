"""FreeCAD FEM / Gmsh / CalculiX adapter with artifact-bound setup review."""
from __future__ import annotations

import hashlib
import json
import math
import os
from pathlib import Path
import re
import shutil
import subprocess
import tempfile

from analysis.materials import validate_material
from analysis.static_structural_template import validate_static_setup
from schemas import AnalysisResults, AnalysisSpec, FEMPreparation, MeshInformation, ResolvedRegion
from workers.process import run_owned


class FEMUnavailable(RuntimeError):
    pass


def _digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def spec_digest(spec: AnalysisSpec) -> str:
    return _digest(json.dumps(spec.model_dump(mode="json"), sort_keys=True, separators=(",", ":")).encode())


def availability(freecad_cmd: str | None, calculix_exe: str | None = None,
                 gmsh_exe: str | None = None) -> tuple[bool, str]:
    missing = [name for name, path in [("FreeCADCmd", freecad_cmd), ("CalculiX ccx", calculix_exe), ("Gmsh", gmsh_exe)]
               if not path or not (Path(path).is_file() or shutil.which(path))]
    if missing:
        return False, "Not configured or not found: " + ", ".join(missing)
    return True, "Executable presence only; FreeCAD FEM API and solver execution remain unverified until run"


def _invoke(mode: str, spec: AnalysisSpec, step: Path, directory: Path, *, freecad_cmd: str,
            calculix_exe: str, gmsh_exe: str, timeout_seconds: int) -> None:
    job = {"mode": mode, "spec": spec.model_dump(mode="json"), "step": str(step.resolve()),
           "directory": str(directory.resolve()), "publication_directory": str(directory.resolve()),
           "freecad_executable": freecad_cmd,
           "ccx": calculix_exe, "gmsh": gmsh_exe,
           "timeout": timeout_seconds}
    job_path = directory / f"{mode}_job.json"
    with job_path.open("x", encoding="utf-8") as stream:
        json.dump(job, stream, indent=2)
    # Native FreeCAD/Gmsh/CalculiX IO has legacy Windows path restrictions.
    # Stage only this reviewed job, then retain immutable outputs in its real
    # artifact directory. This is trusted solver infrastructure, not a sandbox.
    with tempfile.TemporaryDirectory(prefix="cae-fem-") as temporary:
        staging = Path(temporary)
        step_bytes = step.read_bytes()
        if _digest(step_bytes) != spec.geometry_hash:
            raise ValueError("STEP changed before the FEM worker started")
        staged_step = staging / "model.step"
        staged_step.write_bytes(step_bytes)
        inputs = {"model.step", "worker_job.json"}
        if mode == "solve":
            for name in ("setup.FCStd", "regions.json", "analysis_spec.json"):
                shutil.copyfile(directory / name, staging / name)
                inputs.add(name)
        staged_job = {**job, "directory": str(staging), "step": str(staged_step)}
        (staging / "worker_job.json").write_text(json.dumps(staged_job), encoding="utf-8")
        environment = {**os.environ, "CAE_FEM_JOB": str(staging / "worker_job.json")}
        try:
            result = run_owned([freecad_cmd, str(Path(__file__).with_name("fem_script.py").resolve())],
                               env=environment, timeout=timeout_seconds + 30)
        except subprocess.TimeoutExpired as error:
            (directory / f"{mode}.log").write_text(f"Owned FEM worker exceeded its time limit: {error}", encoding="utf-8")
            raise
        finally:
            for source in staging.rglob("*"):
                if source.is_file() and source.relative_to(staging).as_posix() not in inputs:
                    destination = directory / source.relative_to(staging)
                    destination.parent.mkdir(parents=True, exist_ok=True)
                    with source.open("rb") as incoming, destination.open("xb") as outgoing:
                        shutil.copyfileobj(incoming, outgoing)
    (directory / f"{mode}.log").write_text(result.stdout + "\n" + result.stderr, encoding="utf-8")
    if result.returncode != 0:
        raise RuntimeError(f"FreeCAD FEM {mode} failed; see {directory / (mode + '.log')}")


def _region_preview(directory: Path, raw: dict) -> None:
    import plotly.graph_objects as go
    figure = go.Figure()
    for label, mesh, color, opacity in [("Accepted geometry", raw["model"], "lightgray", 0.25), *[
            (r["selector_id"] + " / " + r["face_name"], r["mesh"], color, 1.0)
            for r, color in zip(raw["regions"], ["royalblue", "orangered", "green", "purple"])]]:
        vertices, triangles = mesh["vertices"], mesh["triangles"]
        if not vertices or not triangles:
            raise RuntimeError("Resolved region has no actual preview geometry")
        x, y, z = zip(*vertices)
        i, j, k = zip(*triangles)
        figure.add_trace(go.Mesh3d(x=x, y=y, z=z, i=i, j=j, k=k, name=label,
                                  color=color, opacity=opacity, showlegend=True))
    figure.update_layout(title="Review resolved FreeCAD faces before confirming loads/supports",
                         scene={"aspectmode": "data", "xaxis_title": "X (mm)", "yaxis_title": "Y (mm)", "zaxis_title": "Z (mm)"})
    figure.write_html(directory / "regions.html", include_plotlyjs=True)


def prepare_static(*, spec: AnalysisSpec, accepted_step: Path, output_dir: Path,
                   freecad_cmd: str | None, calculix_exe: str | None, gmsh_exe: str | None,
                   timeout_seconds: int = 300) -> FEMPreparation:
    spec = AnalysisSpec.model_validate_json(spec.model_dump_json())
    validate_static_setup(spec, accepted_step)
    present, reason = availability(freecad_cmd, calculix_exe, gmsh_exe)
    if not present:
        raise FEMUnavailable(reason)
    validate_material(spec.material)
    if spec.expected_bounds_mm is None:
        raise ValueError("Accepted geometry bounds in mm are required to detect scaling errors")
    directory = output_dir.resolve()
    directory.mkdir(parents=True, exist_ok=False)
    (directory / "analysis_spec.json").write_text(spec.model_dump_json(indent=2), encoding="utf-8")
    _invoke("prepare", spec, accepted_step, directory, freecad_cmd=freecad_cmd,
            calculix_exe=calculix_exe, gmsh_exe=gmsh_exe, timeout_seconds=timeout_seconds)
    raw = json.loads((directory / "regions.json").read_text(encoding="utf-8"))
    if raw.get("completed") is not True or raw.get("geometry_hash") != spec.geometry_hash:
        raise RuntimeError("FreeCAD FEM region completion evidence is absent or stale")
    _region_preview(directory, raw)
    regions_hash = _digest((directory / "regions.json").read_bytes())
    setup_hash = _digest((directory / "setup.FCStd").read_bytes())
    digest = spec_digest(spec)
    confirmation = _digest((digest + spec.geometry_hash + regions_hash + setup_hash).encode())
    prepared = FEMPreparation(analysis_id=spec.analysis_id, analysis_spec_version=spec.version,
        accepted_revision_id=spec.accepted_revision_id, geometry_hash=spec.geometry_hash,
        spec_hash=digest, regions_hash=regions_hash, setup_hash=setup_hash, confirmation_hash=confirmation,
        regions=[ResolvedRegion.model_validate({k: v for k, v in r.items() if k != "mesh"}) for r in raw["regions"]],
        directory=str(directory))
    (directory / "preparation.json").write_text(prepared.model_dump_json(indent=2), encoding="utf-8")
    return prepared


def parse_reaction_totals(text: str) -> tuple[float, float, float]:
    lines = text.splitlines()
    found = []
    for index, line in enumerate(lines):
        if "total force" in line.lower() and "cae_support_nodes" in line.lower():
            for candidate in lines[index + 1:index + 6]:
                values = re.findall(r"[-+]?(?:\d+\.\d*|\.\d+|\d+)(?:[EeDd][-+]?\d+)?", candidate)
                if len(values) == 3:
                    found.append(tuple(float(v.replace("D", "E").replace("d", "e")) for v in values))
                    break
    if not found or not all(math.isfinite(v) for v in found[-1]):
        raise ValueError("CalculiX DAT output has no finite support reaction totals")
    return found[-1]


def _result_images(directory: Path, raw: dict) -> list[str]:
    import matplotlib
    matplotlib.use("Agg")
    import matplotlib.pyplot as plt
    points = [raw["coordinates"][str(n)] for n in raw["node_numbers"]]
    names = []
    for key, label, unit in [("displacements_mm", "Displacement", "mm"), ("von_mises_mpa", "von Mises stress", "MPa")]:
        fig = plt.figure(figsize=(9, 4.5))
        axis = fig.add_subplot(111, projection="3d")
        x, y, z = zip(*points)
        artist = axis.scatter(x, y, z, c=raw[key], cmap="viridis", s=4)
        axis.set(xlabel="X (mm)", ylabel="Y (mm)", zlabel="Z (mm)", title=label + " (preliminary nodal results)")
        axis.set_box_aspect([max(x)-min(x), max(y)-min(y), max(z)-min(z)])
        fig.colorbar(artist, ax=axis, label=unit, shrink=.6)
        filename = key + ".png"
        fig.savefig(directory / filename, dpi=150, bbox_inches="tight")
        plt.close(fig)
        names.append(filename)
    return names


def execute_static_or_block(*, spec: AnalysisSpec, accepted_step: Path,
                            freecad_cmd: str | None, calculix_exe: str | None = None,
                            gmsh_exe: str | None = None, preparation: FEMPreparation | None = None,
                            confirmation_hash: str | None = None, timeout_seconds: int = 300) -> AnalysisResults:
    validate_static_setup(spec, accepted_step)
    common = dict(analysis_id=spec.analysis_id, analysis_spec_version=spec.version,
                  accepted_revision_id=spec.accepted_revision_id, geometry_hash=spec.geometry_hash)
    present, reason = availability(freecad_cmd, calculix_exe, gmsh_exe)
    if not present:
        return AnalysisResults(**common, status="blocked", provenance="unavailable", error=reason)
    if preparation is None or confirmation_hash != preparation.confirmation_hash:
        raise ValueError("Review actual resolved regions and explicitly confirm this exact FEM setup before solving")
    directory = Path(preparation.directory)
    expected = _digest((spec_digest(spec) + spec.geometry_hash +
        _digest((directory / "regions.json").read_bytes()) + _digest((directory / "setup.FCStd").read_bytes())).encode())
    if expected != confirmation_hash or spec_digest(spec) != preparation.spec_hash:
        raise ValueError("Stale/tampered FEM preparation; review the current geometry and setup again")
    validate_material(spec.material)
    if (directory / "results.json").exists() or (directory / "solve_job.json").exists():
        raise FileExistsError("Analysis runs are immutable; create a new preparation for an explicit retry")
    try:
        _invoke("solve", spec, accepted_step, directory, freecad_cmd=freecad_cmd,
                calculix_exe=calculix_exe, gmsh_exe=gmsh_exe, timeout_seconds=timeout_seconds)
        raw = json.loads((directory / "solver_results.json").read_text(encoding="utf-8"))
        if raw.get("completed") is not True:
            raise RuntimeError("No successful FreeCAD FEM completion manifest")
        reactions = parse_reaction_totals((directory / raw["dat_path"]).read_text(encoding="utf-8"))
        images = _result_images(directory, raw)
        result = AnalysisResults(**common, status="succeeded", provenance="actual_solver",
            solver_version="FreeCAD %s / CalculiX %s" % (raw["freecad_version"], ".".join(map(str, raw["solver_version"]))),
            maximum_displacement_mm=raw["maximum_displacement_mm"], maximum_von_mises_mpa=raw["maximum_von_mises_mpa"],
            reaction_force_n=reactions, mesh=MeshInformation(nodes=raw["nodes"], elements=raw["elements"]),
            image_paths=images, log_paths=["solve.log", "calculix.log", raw["dat_path"], raw["frd_path"]])
    except (OSError, RuntimeError, ValueError, subprocess.TimeoutExpired) as error:
        result = AnalysisResults(**common, status="failed", provenance="unavailable", error=f"{type(error).__name__}: {error}")
    from reporting import render_report
    (directory / "results.json").write_text(result.model_dump_json(indent=2), encoding="utf-8")
    (directory / "report.md").write_text(render_report(spec, result), encoding="utf-8")
    artifacts = {p.relative_to(directory).as_posix(): {"sha256": _digest(p.read_bytes()), "size_bytes": p.stat().st_size}
                 for p in directory.rglob("*") if p.is_file() and p.name != "completion.json"}
    (directory / "completion.json").write_text(json.dumps({"completed": result.status == "succeeded",
        "geometry_hash": spec.geometry_hash, "analysis_spec_version": spec.version,
        "confirmation_hash": confirmation_hash, "artifacts": artifacts}, indent=2), encoding="utf-8")
    return result

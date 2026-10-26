"""Trusted deterministic CadQuery worker.

This worker executes repository-authored model code. It is not a sandbox for
LLM-generated code. Generated code will require the no-network, no-secret,
resource-limited container boundary specified for M6.
"""

from __future__ import annotations

import hashlib
import importlib.util
import json
from pathlib import Path
import shutil
import tempfile
import time

from schemas import Artifact, ArtifactManifest, new_id, utc_now


CAD_ROLES = {"step", "preview", "model_source", "parameters", "cad_metadata", "cad_log"}


def _artifact(path: Path, project_root: Path, role: str, media_type: str) -> Artifact:
    data = path.read_bytes()
    return Artifact(relative_path=path.relative_to(project_root).as_posix(),
                    sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                    media_type=media_type, role=role)


def run_trusted_build(*, project_id: str, job_id: str, model_source: Path,
                      params: dict[str, float], output_dir: Path, project_root: Path,
                      execution_kind: str = "trusted_deterministic") -> ArtifactManifest:
    """Run a repository-authored build and require all CAD outputs.

    The output directory must be a new revision directory. Existing outputs are
    rejected to preserve revision history.
    """
    import cadquery as cq
    from cadquery import exporters

    output_dir = output_dir.resolve()
    project_root = project_root.resolve()
    if not output_dir.is_relative_to(project_root):
        raise ValueError("CAD output must stay inside the project artifact root")
    output_dir.mkdir(parents=True, exist_ok=True)
    names = ["model.step", "preview.stl", "model.py", "parameters.json", "generation.json", "cad.log"]
    if any((output_dir / name).exists() for name in names):
        raise FileExistsError("Revision CAD outputs are immutable and cannot be overwritten")

    started = time.perf_counter()
    specification = importlib.util.spec_from_file_location("trusted_cad_model", model_source)
    if specification is None or specification.loader is None:
        raise RuntimeError("Could not load deterministic model source")
    module = importlib.util.module_from_spec(specification)
    module.cq = cq
    specification.loader.exec_module(module)
    if not callable(getattr(module, "build", None)):
        raise TypeError("Model source must define build(params)")
    result = module.build(dict(params))
    if result is None or not hasattr(result, "val"):
        raise TypeError("build(params) did not return a CadQuery object")

    step = output_dir / "model.step"
    preview = output_dir / "preview.stl"
    # The native STL writer can silently fail above Windows MAX_PATH even when
    # Python supports extended paths. Export to a short private staging folder,
    # verify both outputs, then publish without clobbering revision artifacts.
    with tempfile.TemporaryDirectory(prefix="cae-cad-") as temporary:
        staged_step, staged_stl = Path(temporary) / "model.step", Path(temporary) / "preview.stl"
        exporters.export(result, str(staged_step), exportType="STEP")
        exporters.export(result, str(staged_stl), exportType="STL", tolerance=0.05, angularTolerance=0.1)
        for source, target in [(staged_step, step), (staged_stl, preview)]:
            if not source.is_file() or source.stat().st_size == 0:
                raise RuntimeError("CadQuery native export did not produce a nonempty " + source.name)
        for source, target in [(staged_step, step), (staged_stl, preview)]:
            with source.open("rb") as incoming, target.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
    shutil.copyfile(model_source, output_dir / "model.py")
    (output_dir / "parameters.json").write_text(json.dumps(params, indent=2, sort_keys=True), encoding="utf-8")
    elapsed = time.perf_counter() - started
    metadata = {
        "schema_version": "1.0", "completed": True, "worker": execution_kind,
        "cadquery_version": getattr(cq, "__version__", "unknown"),
        "started_at": utc_now().isoformat(), "elapsed_seconds": elapsed,
        "note": ("Generated source executed inside the restricted container" if execution_kind == "generated_container"
                 else "Repository-authored deterministic model; not generated-code sandbox execution"),
    }
    (output_dir / "generation.json").write_text(json.dumps(metadata, indent=2), encoding="utf-8")
    (output_dir / "cad.log").write_text(
        f"CadQuery deterministic build completed in {elapsed:.3f} seconds\n", encoding="utf-8")

    paths = [step, preview, output_dir / "model.py", output_dir / "parameters.json",
             output_dir / "generation.json", output_dir / "cad.log"]
    if any(not path.is_file() or path.stat().st_size == 0 for path in paths):
        raise RuntimeError("CadQuery completed without all expected nonempty outputs")
    role_media = [
        ("step", "model/step"), ("preview", "model/stl"), ("model_source", "text/x-python"),
        ("parameters", "application/json"), ("cad_metadata", "application/json"),
        ("cad_log", "text/plain"),
    ]
    artifacts = [_artifact(path, project_root, role, media)
                 for path, (role, media) in zip(paths, role_media)]
    if {item.role for item in artifacts} != CAD_ROLES:
        raise RuntimeError("CAD completion manifest is incomplete")
    return ArtifactManifest(manifest_id=new_id(), project_id=project_id, job_id=job_id,
                            stage="CAD_EXECUTION", completed=True, artifacts=artifacts)

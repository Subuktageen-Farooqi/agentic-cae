"""FreeCADCmd adapter with output and manifest verification."""

from __future__ import annotations

import hashlib
import json
import os
from pathlib import Path
import subprocess
import tempfile
import shutil

from schemas import Artifact, ArtifactManifest, BoundingBox, GeometryMetrics, new_id
from workers.process import run_owned


FREECAD_ROLES = {"fcstd", "freecad_metrics", "freecad_log"}


def _artifact(path: Path, project_root: Path, role: str, media_type: str) -> Artifact:
    data = path.read_bytes()
    return Artifact(relative_path=path.relative_to(project_root).as_posix(),
                    sha256=hashlib.sha256(data).hexdigest(), size_bytes=len(data),
                    media_type=media_type, role=role)


def run_freecad_validation(*, freecad_cmd: str, project_id: str, job_id: str,
                           revision_id: str, step_path: Path, output_dir: Path,
                           project_root: Path, timeout_seconds: int = 300) -> tuple[GeometryMetrics, ArtifactManifest]:
    step_path, output_dir, project_root = step_path.resolve(), output_dir.resolve(), project_root.resolve()
    if not step_path.is_file() or not step_path.is_relative_to(project_root):
        raise ValueError("FreeCAD input STEP must exist inside the project artifact root")
    if not output_dir.is_relative_to(project_root):
        raise ValueError("FreeCAD output must stay inside the project artifact root")
    output_dir.mkdir(parents=True, exist_ok=True)
    fcstd = output_dir / "model.FCStd"
    metrics_path = output_dir / "freecad_metrics.json"
    log_path = output_dir / "freecad.log"
    if any(path.exists() for path in (fcstd, metrics_path, log_path)):
        raise FileExistsError("Revision FreeCAD outputs are immutable and cannot be overwritten")

    script = Path(__file__).with_name("freecad_script.py").resolve()
    geometry_bytes = step_path.read_bytes()
    geometry_hash = hashlib.sha256(geometry_bytes).hexdigest()
    # FreeCAD's native STEP/FCStd IO does not consistently accept long Windows
    # paths. Stage only this job's input and copy verified outputs back using
    # Python's extended-path support; revision paths and hashes stay unchanged.
    with tempfile.TemporaryDirectory(prefix="cae-freecad-") as temporary:
        staging = Path(temporary)
        staged_step, staged_fcstd, staged_metrics = staging / "model.step", staging / "model.FCStd", staging / "metrics.json"
        staged_step.write_bytes(geometry_bytes)
        environment = {**os.environ, "CAE_STEP_PATH": str(staged_step), "CAE_FCSTD_PATH": str(staged_fcstd),
                       "CAE_FREECAD_METRICS_PATH": str(staged_metrics)}
        try:
            process = run_owned([freecad_cmd, str(script)], timeout=timeout_seconds, env=environment)
            log = f"exit_code={process.returncode}\n--- stdout ---\n{process.stdout}\n--- stderr ---\n{process.stderr}"
        except BaseException as error:
            log_path.write_text(f"FreeCAD invocation failed: {type(error).__name__}: {error}\n", encoding="utf-8")
            raise
        log_path.write_text(log, encoding="utf-8")
        if process.returncode != 0:
            raise RuntimeError(f"FreeCADCmd failed with exit code {process.returncode}; see {log_path}")
        for source, destination in [(staged_fcstd, fcstd), (staged_metrics, metrics_path)]:
            if not source.is_file() or source.stat().st_size == 0:
                raise RuntimeError("FreeCAD exited without all expected nonempty outputs")
        for source, destination in [(staged_fcstd, fcstd), (staged_metrics, metrics_path)]:
            with source.open("rb") as incoming, destination.open("xb") as outgoing:
                shutil.copyfileobj(incoming, outgoing)
    if any(not path.is_file() or path.stat().st_size == 0 for path in (fcstd, metrics_path, log_path)):
        raise RuntimeError("FreeCAD exited without all expected nonempty outputs")
    try:
        raw = json.loads(metrics_path.read_text(encoding="utf-8"))
    except (OSError, json.JSONDecodeError) as error:
        raise RuntimeError("FreeCAD completion metrics are unreadable") from error
    if raw.get("completed") is not True:
        raise RuntimeError("FreeCAD completion manifest did not confirm completion")
    if hashlib.sha256(step_path.read_bytes()).hexdigest() != geometry_hash:
        raise RuntimeError("Input STEP changed during FreeCAD validation")
    metrics = GeometryMetrics(
        revision_id=revision_id, geometry_hash=geometry_hash,
        step_import_succeeded=raw["step_import_succeeded"], shape_nonempty=raw["shape_nonempty"],
        shape_valid=raw["shape_valid"], solid_count=raw["solid_count"],
        volume_mm3=raw["volume_mm3"], surface_area_mm2=raw.get("surface_area_mm2"),
        bounding_box=BoundingBox.model_validate(raw["bounding_box"]),
        evidence_path=metrics_path.relative_to(project_root).as_posix(),
    )
    artifacts = [_artifact(fcstd, project_root, "fcstd", "application/x-freecad"),
                 _artifact(metrics_path, project_root, "freecad_metrics", "application/json"),
                 _artifact(log_path, project_root, "freecad_log", "text/plain")]
    if {item.role for item in artifacts} != FREECAD_ROLES:
        raise RuntimeError("FreeCAD completion manifest is incomplete")
    manifest = ArtifactManifest(manifest_id=new_id(), project_id=project_id, job_id=job_id,
                                stage="FREECAD_VALIDATION", completed=True, artifacts=artifacts)
    return metrics, manifest

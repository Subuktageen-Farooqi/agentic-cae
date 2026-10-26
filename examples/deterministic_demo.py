"""Repeatable real CadQuery → FreeCAD → rule-check demonstration."""

from __future__ import annotations

import json
from pathlib import Path

from config import Config
from rules.geometry import bounding_dimension_rules, core_geometry_rules, mandatory_geometry_passes
from rules.manufacturing import scaffolded_rules
from schemas import DesignBrief, DesignSpec, Dimension, Feature, Intake, JobStatus, Requirement
from storage import Store
from workers.cad_worker import run_trusted_build
from workers.freecad_worker import run_freecad_validation


PARAMS = {"length_mm": 100.0, "width_mm": 20.0, "height_mm": 10.0, "fillet_mm": 0.0}


def run(data_dir: str | Path, freecad_cmd: str | None = None) -> dict:
    config = Config.from_env()
    executable = freecad_cmd or config.freecad_cmd
    if not executable:
        raise RuntimeError("BLOCKED: FreeCADCmd was not found; set FREECAD_CMD")
    store = Store(data_dir)
    project_id = store.create_project(Intake(
        idea="A deterministic solid cantilever support arm",
        purpose="Prove the real CAD and FreeCAD integration path",
        hard_requirements=[Requirement(requirement_id="R-SOLID", text="Exactly one connected solid",
                                      verification_method="FreeCAD solid count")],
        units="mm",
        dimensions=[Dimension(name="length", value=100, unit="mm", origin="accepted", accepted_from="user_provided"),
                    Dimension(name="width", value=20, unit="mm", origin="accepted", accepted_from="user_provided"),
                    Dimension(name="height", value=10, unit="mm", origin="accepted", accepted_from="user_provided")],
    ))
    brief = store.save_brief(project_id, DesignBrief(
        design_name="Deterministic cantilever", purpose="Integration proof",
        hard_requirements=store.original_intake(project_id).hard_requirements,
        dimensions=store.original_intake(project_id).dimensions,
        accepted_decisions=[], assumptions=["Rectangular prismatic test geometry"],
    ), expected_version=0, actor="deterministic_demo", reason="Freeze deterministic integration brief")
    attempt = store.create_attempt(project_id, brief.version)
    revision = store.create_revision(attempt["attempt_id"])
    revision_dir = store.path(revision["relative_path"])
    spec = DesignSpec(
        brief_id=brief.brief_id, brief_version=brief.version, design_name=brief.design_name,
        purpose=brief.purpose, units="mm", dimensions=brief.dimensions,
        features=[Feature(feature_id="F-BEAM", kind="extrusion", description="Rectangular beam",
                          parameter_names=["length", "width", "height"])],
        hard_requirements=brief.hard_requirements, assumptions=brief.assumptions,
    )
    store.save_record(project_id, spec.spec_id, spec.version, spec)

    cad_job = store.enqueue(project_id, f"cad:{revision['revision_id']}:deterministic-v1", "CAD_EXECUTION",
                            {"revision_id": revision["revision_id"], "params": PARAMS})
    owner = f"demo-{project_id[:8]}"
    if store.claim(cad_job.job_id, owner) is None:
        raise RuntimeError("CAD job could not be claimed")
    try:
        cad_manifest = run_trusted_build(
            project_id=project_id, job_id=cad_job.job_id,
            model_source=Path(__file__).with_name("cantilever_model.py"), params=PARAMS,
            output_dir=revision_dir, project_root=store.root,
        )
        store.verify_manifest(cad_manifest, required_roles=["step", "preview", "model_source", "parameters"])
        store.save_record(project_id, cad_manifest.manifest_id, 1, cad_manifest)
        store.finish(cad_job.job_id, owner, JobStatus.SUCCEEDED,
                     result={"manifest_id": cad_manifest.manifest_id})
    except BaseException as error:
        store.finish(cad_job.job_id, owner, JobStatus.FAILED, error=f"{type(error).__name__}: {error}")
        raise

    freecad_job = store.enqueue(project_id, f"freecad:{revision['revision_id']}:v1", "FREECAD_VALIDATION",
                                {"revision_id": revision["revision_id"], "cad_manifest_id": cad_manifest.manifest_id})
    if store.claim(freecad_job.job_id, owner) is None:
        raise RuntimeError("FreeCAD job could not be claimed")
    try:
        metrics, freecad_manifest = run_freecad_validation(
            freecad_cmd=executable, project_id=project_id, job_id=freecad_job.job_id,
            revision_id=revision["revision_id"], step_path=revision_dir / "model.step",
            output_dir=revision_dir, project_root=store.root,
            timeout_seconds=config.worker_timeout_seconds,
        )
        store.verify_manifest(freecad_manifest, required_roles=["fcstd", "freecad_metrics", "freecad_log"])
        store.save_record(project_id, revision["revision_id"], 1, metrics)
        store.save_record(project_id, freecad_manifest.manifest_id, 1, freecad_manifest)
        store.finish(freecad_job.job_id, owner, JobStatus.SUCCEEDED,
                     result={"manifest_id": freecad_manifest.manifest_id, "geometry_hash": metrics.geometry_hash})
    except BaseException as error:
        store.finish(freecad_job.job_id, owner, JobStatus.FAILED, error=f"{type(error).__name__}: {error}")
        raise

    results = core_geometry_rules(metrics)
    results.extend(bounding_dimension_rules(metrics, {
        "x": (PARAMS["length_mm"], 0.01), "y": (PARAMS["width_mm"], 0.01),
        "z": (PARAMS["height_mm"], 0.01),
    }))
    results.extend(scaffolded_rules(metrics))
    for index, result in enumerate(results, 1):
        store.save_record(project_id, f"{revision['revision_id']}:{result.rule_id}", index, result)
    summary = {
        "project_id": project_id, "attempt_id": attempt["attempt_id"],
        "revision_id": revision["revision_id"], "geometry_hash": metrics.geometry_hash,
        "freecad_version": json.loads((revision_dir / "freecad_metrics.json").read_text(encoding="utf-8"))["freecad_version"],
        "geometry": metrics.model_dump(mode="json"),
        "rules": [result.model_dump(mode="json") for result in results],
        "mandatory_geometry_passed": mandatory_geometry_passes(results),
        "artifact_directory": revision["relative_path"],
        "limitations": [
            "This demonstrates repository-authored deterministic code; generated-code container isolation is not implemented.",
            "FCStd contains imported STEP geometry; the parametric source is model.py plus parameters.json.",
            "No engineering analysis has run; geometry acceptance is not engineering acceptance.",
        ],
    }
    summary_path = revision_dir / "demo_summary.json"
    summary_path.write_text(json.dumps(summary, indent=2), encoding="utf-8")
    if not summary["mandatory_geometry_passed"]:
        raise RuntimeError("Mandatory geometry checks failed; see demo summary")
    return summary

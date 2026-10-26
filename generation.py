"""Durable M6 pipeline. Generated CAD is never executed in the app process."""
from __future__ import annotations

from concurrent.futures import Executor
import json
from pathlib import Path
import traceback
import subprocess

from agents.cad_creator import cad_parameters, create_cad
from agents.spec_writer import write_spec
from config import Config
from providers.vertex import ImagePayload, ProviderUnavailable, VisionTextProvider
from reporting import render_design_spec
from rules.geometry import bounding_dimension_rules, core_geometry_rules, mandatory_geometry_passes
from rules.manufacturing import scaffolded_rules
from schemas import JobStatus, WorkflowState as S, new_id
from storage import Store
from workers.code_validation import CodeRejected, validate_code
from workers.freecad_worker import run_freecad_validation
from workers.runtime import CADBuildError, SandboxUnavailable, execute_generated
from workflow import Workflow


GENERATION_STATES = {S.SPEC_GENERATION, S.CAD_GENERATION, S.CAD_EXECUTION, S.FREECAD_VALIDATION, S.RULE_CHECKS}


def brief_images(store: Store, project_id: str, brief) -> list[ImagePayload]:
    return [ImagePayload(data=store.read_image(project_id, image.image_id), media_type=image.media_type,
                         role=image.role, image_id=image.image_id) for image in store.images(project_id)
            if image.image_id in brief.reference_image_ids]


def latest_generation(store: Store, project_id: str):
    brief = store.brief(project_id)
    jobs = [j for j in store.jobs(project_id) if j.kind == "DESIGN_GENERATION" and
            j.payload.get("brief_id") == brief.brief_id and j.payload.get("brief_version") == brief.version]
    return jobs[-1] if jobs else None


def enqueue_generation(store: Store, project_id: str, *, request_key: str | None = None):
    brief = store.brief(project_id)
    if store.project(project_id)["state"] != S.SPEC_GENERATION:
        raise ValueError("Generation must start from a frozen brief in SPEC_GENERATION")
    return store.enqueue(project_id, request_key or f"generation:{brief.brief_id}:{brief.version}", "DESIGN_GENERATION",
                         {"brief_id": brief.brief_id, "brief_version": brief.version})


def run_generation_job(*, store: Store, job_id: str, provider: VisionTextProvider, config: Config):
    job = store.claim(job_id, owner := "generation-" + new_id())
    if job is None:
        return store.job(job_id)
    project_id, flow, evidence = job.project_id, Workflow(store), {}

    def transition(target, reason):
        current = store.project(project_id)
        if current["state"] != target:
            flow.transition(project_id, target, expected_version=current["row_version"], reason=reason)

    try:
        brief = store.brief(project_id, job.payload["brief_version"])
        images = brief_images(store, project_id, brief)
        attempt = store.create_attempt(project_id, brief.version)
        revision = store.create_revision(attempt["attempt_id"])
        relative = revision["relative_path"]
        evidence.update(attempt_id=attempt["attempt_id"], revision_id=revision["revision_id"], artifact_directory=relative)
        spec = write_spec(brief=brief, provider=provider, images=images)
        store.save_record(project_id, spec.spec_id, spec.version, spec)
        store.write_once(relative + "/design_spec.json", spec.model_dump_json(indent=2).encode())
        store.write_once(relative + "/design_spec.md", render_design_spec(spec).encode())
        evidence["spec_id"] = spec.spec_id
        transition(S.CAD_GENERATION, "Validated specification saved from the frozen brief")
        previous, failure = None, None
        for repair in range(2):
            generation = create_cad(spec=spec, attempt_id=attempt["attempt_id"], revision_id=revision["revision_id"],
                provider=provider, images=images, previous=previous, technical_error=failure)
            store.save_record(project_id, generation.generation_id, 1, generation)
            store.write_once(relative + f"/generation-{repair}.json", generation.model_dump_json(indent=2).encode())
            try:
                validate_code(generation.code)
                transition(S.CAD_EXECUTION, "Restricted source validated; container execution requested")
                cad = execute_generated(generation=generation, project_id=project_id, job_id=job.job_id,
                    output_dir=store.path(relative + f"/build-{repair}"), project_root=store.root, config=config)
                store.verify_manifest(cad, required_roles=["step", "preview", "model_source", "parameters"])
                store.save_record(project_id, cad.manifest_id, 1, cad)
                transition(S.FREECAD_VALIDATION, "Container CAD outputs and hashes verified")
                if not config.freecad_cmd:
                    raise SandboxUnavailable("FreeCADCmd is unavailable; generated CAD remains unvalidated")
                step = store.path(next(a.relative_path for a in cad.artifacts if a.role == "step"))
                metrics, imported = run_freecad_validation(freecad_cmd=config.freecad_cmd, project_id=project_id,
                    job_id=job.job_id, revision_id=revision["revision_id"], step_path=step,
                    output_dir=store.path(relative + f"/freecad-{repair}"), project_root=store.root,
                    timeout_seconds=config.worker_timeout_seconds)
                store.verify_manifest(imported, required_roles=["fcstd", "freecad_metrics", "freecad_log"])
                store.save_record(project_id, imported.manifest_id, 1, imported)
                store.save_record(project_id, revision["revision_id"], repair + 1, metrics)
                transition(S.RULE_CHECKS, "FreeCAD imported and saved the actual generated STEP")
                checks = core_geometry_rules(metrics) + scaffolded_rules(metrics)
                parameters = cad_parameters(spec)
                checks.extend(bounding_dimension_rules(metrics, {axis: (parameters[name],
                    next((d.tolerance * {"mm": 1, "m": 1000, "in": 25.4}[d.unit]
                          for d in spec.dimensions if d.name == name and d.tolerance is not None), .01))
                    for axis, name in spec.bounding_dimensions.items()}))
                for check in checks:
                    store.save_record(project_id, revision["revision_id"] + ":" + check.rule_id, repair + 1, check)
                if not mandatory_geometry_passes(checks):
                    raise CADBuildError("Mandatory geometry checks failed: " + json.dumps([c.model_dump(mode="json") for c in checks if c.mandatory]))
                evidence.update(geometry_hash=metrics.geometry_hash, cad_manifest_id=cad.manifest_id,
                                freecad_manifest_id=imported.manifest_id)
                transition(S.DESIGN_REVIEW, "Generated geometry passed all implemented mandatory checks; engineering analysis has not run")
                return store.finish(job.job_id, owner, JobStatus.SUCCEEDED, result=evidence)
            except SandboxUnavailable:
                raise
            except (CodeRejected, CADBuildError, RuntimeError, OSError, ValueError, subprocess.TimeoutExpired) as error:
                failure = "".join(traceback.format_exception(error))[-12000:]
                store.write_once(relative + f"/technical-error-{repair}.txt", failure.encode())
                if repair == 1:
                    raise
                store.consume_technical_repair(revision["revision_id"])
                previous = generation
                transition(S.CAD_GENERATION, "One automatic technical repair using actual failure evidence")
    except (ProviderUnavailable, SandboxUnavailable) as error:
        transition(S.BLOCKED, str(error))
        return store.finish(job.job_id, owner, JobStatus.BLOCKED, result=evidence, error=str(error))
    except Exception as error:
        transition(S.ERROR, f"Generation stopped: {type(error).__name__}")
        return store.finish(job.job_id, owner, JobStatus.FAILED, result=evidence,
                            error=f"{type(error).__name__}: {error}")


def start_generation(*, store: Store, project_id: str, provider: VisionTextProvider, config: Config, executor: Executor):
    # Existing pending/running jobs are displayed, never silently re-executed on
    # application restart. An operator can inspect/recover and explicitly retry.
    existing = latest_generation(store, project_id)
    if existing is not None:
        return existing
    job = enqueue_generation(store, project_id)
    executor.submit(run_generation_job, store=store, job_id=job.job_id, provider=provider, config=config)
    return job


def retry_generation(*, store: Store, project_id: str, provider: VisionTextProvider, config: Config, executor: Executor):
    """Explicit user retry creates a fresh attempt; interrupted work is never reused."""
    with store._connection(write=True) as db:
        project = store._project_row(db, project_id)
        if project["state"] not in (S.BLOCKED, S.ERROR) or project["resume_state"] not in GENERATION_STATES:
            raise ValueError("Only a blocked/failed generation can be explicitly retried")
        if db.execute("SELECT 1 FROM jobs WHERE project_id=? AND status IN ('pending','running')", (project_id,)).fetchone():
            raise ValueError("Inspect/recover existing pending/running work before retrying")
        db.execute("UPDATE projects SET state=?,resume_state=NULL,row_version=row_version+1 WHERE project_id=?",
                   (S.SPEC_GENERATION, project_id))
        store._event(db, project_id, "generation_retry_requested", {"from": project["state"], "preserve_previous_attempts": True})
    job = enqueue_generation(store, project_id, request_key="generation-retry:" + new_id())
    executor.submit(run_generation_job, store=store, job_id=job.job_id, provider=provider, config=config)
    return job

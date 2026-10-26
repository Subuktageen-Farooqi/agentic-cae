"""Persistent app boundary for actual FreeCAD FEM setup review, solve and reporting."""
from __future__ import annotations

import hashlib
import json

from analysis.materials import reference_steel
from analysis.sanity import (cantilever_tip_displacement_mm, rectangular_second_moment_mm4,
                             reaction_imbalance_n, vector_magnitude, relative_difference)
from reporting import render_analysis_spec, render_report
from review import current_review, review_artifacts, _state
from schemas import (AnalysisSpec, Artifact, ArtifactManifest, JobStatus, Load, MeshSettings,
                     RegionSelector, Support, WorkflowState as S, new_id)
from storage import ConflictError, IntegrityError
from workers.fem_worker import FEMUnavailable, prepare_static, execute_static_or_block


def accepted_artifacts(store, project_id):
    project = store.project(project_id)
    accepted = [a for a in store.records(project_id, "DesignAcceptance")
                if a.revision_id == project["accepted_revision_id"] and a.geometry_hash == project["accepted_geometry_hash"]]
    if not accepted:
        raise ValueError("Accept the exact checked design before preparing an analysis")
    review = store.record(project_id, "DesignReview", accepted[-1].revision_id, 1)
    artifacts = review_artifacts(store, project_id, review)
    if artifacts["step"].sha256 != accepted[-1].geometry_hash:
        raise IntegrityError("Accepted geometry is stale or altered")
    return review, artifacts


def propose_static(store, project_id, *, question: str, force_n, mesh_mm: float):
    review, artifacts = accepted_artifacts(store, project_id)
    brief = store.brief(project_id, review.brief_version)
    if brief.materials and not all("steel" in material.casefold() for material in brief.materials):
        raise ValueError("The reference-steel allowlist conflicts with this brief's material; add reviewed material properties before execution")
    return AnalysisSpec(accepted_revision_id=review.revision_id, geometry_hash=review.geometry_hash,
        analysis_type="linear_static_structural", engineering_question=question, material=reference_steel(),
        selectors=[RegionSelector(selector_id="fixed", kind="planar_min_x", position_tolerance_mm=.01, normal_tolerance_degrees=1),
                   RegionSelector(selector_id="tip", kind="planar_max_x", position_tolerance_mm=.01, normal_tolerance_degrees=1)],
        supports=[Support(selector_id="fixed")], loads=[Load(selector_id="tip", force_n=force_n)],
        mesh=MeshSettings(element_size_mm=mesh_mm), requested_outputs=["displacement", "von_mises", "reaction_forces"],
        execution_supported=True, expected_bounds_mm=artifacts["metrics"].bounding_box,
        assumptions=["Linear elastic small-deflection model; fixed min-X face; force distributed over max-X face.",
                     "Reference-steel properties explicitly selected for this analysis; not stock certification."])


def _matches_acceptance(store, project_id, spec):
    review, artifacts = accepted_artifacts(store, project_id)
    if (review.revision_id, review.geometry_hash) != (spec.accepted_revision_id, spec.geometry_hash):
        raise ConflictError("Analysis no longer matches the accepted geometry")
    return review, artifacts


def enqueue_prepare(store, project_id, spec, *, expected_version):
    _matches_acceptance(store, project_id, spec)
    if spec.execution_issues():
        raise ValueError("Analysis inputs are incomplete: " + "; ".join(spec.execution_issues()))
    with store._connection(write=True) as db:
        project = store._project_row(db, project_id)
        if project["row_version"] != expected_version or project["state"] != S.ANALYSIS_INTAKE:
            raise ConflictError("Stale analysis form; reload the current design")
        store._insert_record(db, project_id, spec.analysis_id, spec.version, spec)
        job = store._enqueue(db, project_id, "prepare:" + spec.analysis_id, "FEM_PREPARE",
                             {"analysis_id": spec.analysis_id, "spec_version": spec.version})
        _state(store, db, project_id, S.ANALYSIS_SPEC_REVIEW, "Prepare actual imported faces for user review; no solve authorized")
        return job


def enqueue_solve(store, project_id, spec, preparation, *, expected_version, confirmation_hash):
    _matches_acceptance(store, project_id, spec)
    if confirmation_hash != preparation.confirmation_hash:
        raise ValueError("Explicit confirmation of the current actual-region setup is required")
    with store._connection(write=True) as db:
        project = store._project_row(db, project_id)
        if project["row_version"] != expected_version or project["state"] != S.ANALYSIS_SPEC_REVIEW:
            raise ConflictError("Stale analysis confirmation")
        job = store._enqueue(db, project_id, "solve:" + spec.analysis_id + ":" + confirmation_hash, "FEM_SOLVE",
                             {"analysis_id": spec.analysis_id, "spec_version": spec.version, "confirmation_hash": confirmation_hash})
        _state(store, db, project_id, S.ANALYSIS_EXECUTION, "User confirmed actual faces, material, load, supports and mesh")
        store._event(db, project_id, "analysis_confirmed", {"analysis_id": spec.analysis_id, "confirmation_hash": confirmation_hash})
        return job


def numerical_checks(spec, results, review, design_spec, metrics=None):
    applied = tuple(sum(load.force_n[i] for load in spec.loads) for i in range(3))
    residual = reaction_imbalance_n(applied, results.reaction_force_n)
    checks = {"applied_force_n": applied, "reaction_force_n": results.reaction_force_n,
              "reaction_residual_n": residual, "reaction_residual_magnitude_n": vector_magnitude(residual),
              "reaction_relative_residual": vector_magnitude(residual) / sum(vector_magnitude(load.force_n) for load in spec.loads),
              "beam_applicable": False, "beam_reason": "Elementary beam comparison requires the reference cantilever or a verified full rectangular-prism solid with matching dimensions and tip loading."}
    rectangular = False
    if metrics and metrics.bounding_box and metrics.shape_valid and metrics.solid_count == 1:
        spans = tuple(b-a for a,b in zip(metrics.bounding_box.minimum, metrics.bounding_box.maximum))
        # A valid solid contained in its bounds with the full box volume is a
        # rectangular prism to this tight numerical tolerance. Do not infer a
        # beam section from a design name, code comment, or bounding box alone.
        box_volume = spans[0] * spans[1] * spans[2]
        rectangular = (all(v > 0 for v in spans) and abs(metrics.volume_mm3-box_volume) <= .01
                       and design_spec.bounding_dimensions == {"x":"length", "y":"width", "z":"height"})
    compatible = (len(spec.supports) == len(spec.loads) == 1
        and {s.selector_id:s.kind for s in spec.selectors}.get(spec.supports[0].selector_id) == "planar_min_x"
        and {s.selector_id:s.kind for s in spec.selectors}.get(spec.loads[0].selector_id) == "planar_max_x")
    if (review.source == "trusted_reference" or rectangular) and compatible and applied[0] == applied[1] == 0:
        dims = {d.name: d.value * {"mm": 1, "m": 1000, "in": 25.4}.get(d.unit, 1) for d in design_spec.dimensions}
        estimate = cantilever_tip_displacement_mm(force_n=abs(applied[2]), length_mm=dims["length"],
            youngs_modulus_mpa=spec.material.youngs_modulus_mpa,
            second_moment_mm4=rectangular_second_moment_mm4(dims["width"], dims["height"]))
        checks.update(beam_applicable=True, beam_estimate_mm=estimate,
            solver_displacement_mm=results.maximum_displacement_mm,
            displacement_relative_difference=relative_difference(results.maximum_displacement_mm, estimate),
            beam_reason="Euler–Bernoulli F L^3 / (3 E I), I = width × height^3 / 12; slender rectangular beam, matching tip resultant and linear elasticity.")
    return checks


def verification_markdown(checks):
    text = ["", "## Numerical integration checks", "", checks["beam_reason"], ""]
    if checks["beam_applicable"]:
        text += [f"- Beam-theory estimate: {checks['beam_estimate_mm']:.10g} mm",
                 f"- Solver displacement: {checks['solver_displacement_mm']:.10g} mm",
                 f"- Relative displacement difference: {checks['displacement_relative_difference']:.6%}"]
    text += [f"- Applied resultant: {checks['applied_force_n']} N", f"- Extracted support reaction: {checks['reaction_force_n']} N",
             f"- Force-balance residual: {checks['reaction_residual_n']} N",
             f"- Residual magnitude: {checks['reaction_residual_magnitude_n']:.8g} N",
             f"- Relative reaction residual: {checks['reaction_relative_residual']:.8g}", "",
             "These are numerical sanity comparisons, not design acceptance criteria or evidence of mesh convergence."]
    return "\n".join(text) + "\n"


def _publish_manifest(store, project_id, spec, directory, result, job_id):
    artifacts = []
    names = {"analysis.FCStd": "analysis_project", "integration_report.md": "report", "results.json": "results", "calculix.log": "solver_log"}
    for path in directory.rglob("*"):
        if path.is_file():
            data = path.read_bytes()
            artifacts.append(Artifact(relative_path=path.relative_to(store.root).as_posix(), sha256=hashlib.sha256(data).hexdigest(),
                                      size_bytes=len(data), media_type="application/octet-stream", role=names.get(path.name, path.name)))
    manifest = ArtifactManifest(manifest_id=new_id(), project_id=project_id, job_id=job_id,
        revision_id=spec.accepted_revision_id, analysis_id=spec.analysis_id, stage="ANALYSIS_EXECUTION",
        completed=result.status == "succeeded", artifacts=artifacts)
    if result.status == "succeeded":
        store.verify_manifest(manifest, ["analysis_project", "report", "results", "solver_log"])
    store.save_record(project_id, manifest.manifest_id, 1, manifest)
    return manifest


def run_fem_job(*, store, job_id, config):
    job = store.claim(job_id, owner := "fem-" + new_id())
    if job is None:
        return store.job(job_id)
    project_id = job.project_id
    evidence = {"analysis_id": job.payload["analysis_id"]}
    try:
        spec = store.record(project_id, "AnalysisSpec", job.payload["analysis_id"], job.payload["spec_version"])
        review, artifacts = _matches_acceptance(store, project_id, spec)
        step = store.path(artifacts["step"].relative_path)
        relative = f"projects/{project_id}/analyses/{spec.analysis_id}"
        directory = store.path(relative)
        kwargs = dict(spec=spec, accepted_step=step, freecad_cmd=config.freecad_cmd,
                      calculix_exe=config.calculix_exe, gmsh_exe=config.gmsh_exe, timeout_seconds=config.worker_timeout_seconds)
        evidence["artifact_directory"] = relative
        if job.kind == "FEM_PREPARE":
            prepared = prepare_static(**kwargs, output_dir=directory)
            _matches_acceptance(store, project_id, spec)
            store.save_record(project_id, spec.analysis_id, spec.version, prepared)
            store.write_once(relative + "/analysis_spec.md", render_analysis_spec(spec).encode())
            return store.finish(job_id, owner, JobStatus.SUCCEEDED, result=evidence)
        prepared = store.record(project_id, "FEMPreparation", spec.analysis_id, spec.version)
        result = execute_static_or_block(**kwargs, preparation=prepared, confirmation_hash=job.payload["confirmation_hash"])
        _matches_acceptance(store, project_id, spec)
        result.assert_matches(spec)
        store.save_record(project_id, result.run_id, 1, result)
        if result.status == "succeeded":
            if result.provenance != "actual_solver":
                raise IntegrityError("A successful app integration requires actual solver evidence")
            checks = numerical_checks(spec, result, review, artifacts["spec"], artifacts["metrics"])
            store.write_once(relative + "/verification.json", json.dumps(checks, indent=2).encode())
            report = render_report(spec, result) + verification_markdown(checks)
            execution = json.loads((directory / "execution.json").read_text(encoding="utf-8"))
            report += "\n## Executables, versions and actual commands\n\n```json\n" + json.dumps(execution, indent=2) + "\n```\n"
            report += "\n## Solver evidence\n\n" + "\n".join("- [" + name + "](" + name + ")" for name in
                ["prepare.log", "solve.log", "gmsh.log", "calculix.log", "solver/Mesh.inp", "solver/Mesh.frd", "solver/Mesh.dat", "analysis.FCStd", "results.json", "verification.json"]) + "\n"
        else:
            report = render_report(spec, result)
        store.write_once(relative + "/integration_report.md", report.encode())
        manifest = _publish_manifest(store, project_id, spec, directory, result, job_id)
        evidence.update(run_id=result.run_id, manifest_id=manifest.manifest_id)
        with store._connection(write=True) as db:
            _state(store, db, project_id, S.REPORT_READY, "Actual FEM run finished; report reflects its real solver status")
        status = JobStatus.SUCCEEDED if result.status == "succeeded" else JobStatus.BLOCKED if result.status == "blocked" else JobStatus.FAILED
        return store.finish(job_id, owner, status, result=evidence, error=result.error)
    except Exception as error:
        blocked = isinstance(error, FEMUnavailable)
        with store._connection(write=True) as db:
            prior = store._project_row(db, project_id)["state"]
            _state(store, db, project_id, S.BLOCKED if blocked else S.ERROR, str(error))
            db.execute("UPDATE projects SET resume_state=? WHERE project_id=?", (prior, project_id))
        return store.finish(job_id, owner, JobStatus.BLOCKED if blocked else JobStatus.FAILED,
                            result=evidence, error=f"{type(error).__name__}: {error}")


def edit_analysis_inputs(store, project_id, *, expected_version):
    """Explicit new setup; preserve failed/previous runs and never replay a solve."""
    accepted_artifacts(store, project_id)
    with store._connection(write=True) as db:
        project = store._project_row(db, project_id)
        if project["row_version"] != expected_version or project["state"] not in (S.ANALYSIS_SPEC_REVIEW, S.BLOCKED, S.ERROR):
            raise ConflictError("Stale analysis edit action")
        if project["state"] in (S.BLOCKED, S.ERROR) and project["resume_state"] not in (S.ANALYSIS_SPEC_REVIEW,S.ANALYSIS_EXECUTION):
            raise ValueError("This is not a failed analysis stage")
        if db.execute("SELECT 1 FROM jobs WHERE project_id=? AND kind IN ('FEM_PREPARE','FEM_SOLVE') AND status IN ('pending','running')",(project_id,)).fetchone():
            raise ConflictError("Inspect/recover the existing FEM job before editing inputs")
        _state(store,db,project_id,S.ANALYSIS_INTAKE,"User requested fresh analysis inputs; existing runs remain immutable")

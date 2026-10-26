"""M8: one grounded planning/specification request, followed by actual region review.

User quantities and the verified material are authoritative. A model response
cannot authorize solving, invent missing inputs, or change accepted geometry.
"""
import json

from pydantic import ValidationError

from analysis.materials import reference_steel
from fem_workflow import accepted_artifacts, propose_static
from providers.vertex import ProviderUnavailable
from schemas import AnalysisInputs, AnalysisPlan, AnalysisType, WorkflowState
from storage import ConflictError


def plan_analysis(*, store, project_id, inputs: AnalysisInputs, message: str, provider,
                  expected_version: int):
    review, artifacts = accepted_artifacts(store, project_id)
    project = store.project(project_id)
    if project["row_version"] != expected_version or project["state"] != WorkflowState.ANALYSIS_INTAKE:
        raise ConflictError("Stale analysis conversation; reload the current design")
    brief = store.brief(project_id, review.brief_version)
    missing = inputs.missing()
    supported = inputs.analysis_type == AnalysisType.LINEAR_STATIC
    candidate = None
    if supported and not missing:
        candidate = propose_static(store, project_id, question=inputs.engineering_question,
                                   force_n=inputs.force_n, mesh_mm=inputs.mesh_mm)
        candidate = candidate.model_copy(update={"acceptance_limits": inputs.acceptance_limits})
    context = {
        "brief": brief.model_dump(mode="json"), "design": artifacts["spec"].model_dump(mode="json"),
        "metrics": artifacts["metrics"].model_dump(mode="json"),
        "accepted_revision_id": review.revision_id, "geometry_hash": review.geometry_hash,
        "verified_material": reference_steel().model_dump(mode="json"),
        "inputs": inputs.model_dump(mode="json"), "user_message": message,
        "missing_inputs": missing, "executable_candidate": candidate.model_dump(mode="json") if candidate else None,
        "prior_conversation": [p.model_dump(mode="json") for p in store.records(project_id, "AnalysisPlan")
                               if p.accepted_revision_id == review.revision_id and p.geometry_hash == review.geometry_hash],
    }
    raw = provider.generate(system_instruction=(
        "You are the mechanical analysis advisor. Return only JSON matching AnalysisPlan. "
        "Recommend analyses using the purpose, requirements, material, accepted geometry and known conditions. "
        "Only linear_static_structural is executable; modal, random vibration, fatigue, transient and other analyses "
        "must be explicitly unsupported. Do not infer missing forces, support conditions, material properties, "
        "excitation spectra, histories, damping or acceptance criteria. Explain preliminary single-mesh limitations. "
        "Use at most two targeted questions per turn. Copy inputs, accepted_revision_id, geometry_hash, user_message "
        "and missing_inputs exactly. When executable_candidate is null, specification MUST be null. Otherwise copy "
        "executable_candidate exactly into specification. These selectors are proposals; actual face resolution "
        "and explicit user confirmation are still required before any solve. Never claim that preparation or solving occurred."),
        prompt=json.dumps({"context": context, "response_schema": AnalysisPlan.model_json_schema()}))
    try:
        plan = AnalysisPlan.model_validate_json(raw)
    except (ValidationError, ValueError):
        raise ProviderUnavailable("Analysis advisor returned invalid structured output; no preparation or solve started") from None
    if ((plan.accepted_revision_id, plan.geometry_hash) != (review.revision_id, review.geometry_hash)
            or plan.inputs != inputs or plan.user_message != message or plan.missing_inputs != missing
            or plan.specification != candidate):
        raise ValueError("Analysis response changed authoritative geometry, user inputs or verified specification")
    if missing and not plan.questions:
        raise ValueError("Missing analysis inputs require a follow-up question")
    # Recheck under the write lock: a slow response must never replace a newer edit.
    with store._connection(write=True) as db:
        current = store._project_row(db, project_id)
        if current["row_version"] != expected_version or current["state"] != WorkflowState.ANALYSIS_INTAKE:
            raise ConflictError("Analysis changed while the advisor was responding")
        if (current["accepted_revision_id"], current["accepted_geometry_hash"]) != (review.revision_id, review.geometry_hash):
            raise ConflictError("Accepted geometry changed during analysis planning")
        store._insert_record(db, project_id, plan.plan_id, 1, plan)
        db.execute("UPDATE projects SET row_version=row_version+1 WHERE project_id=?", (project_id,))
        store._event(db, project_id, "analysis_plan_saved", {"plan_id": plan.plan_id, "missing_inputs": missing})
    return plan

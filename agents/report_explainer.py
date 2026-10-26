"""Optional prose sidecar; never replaces the deterministic numerical report."""
import json
from pydantic import ValidationError
from schemas import ReportExplanation
from providers.vertex import ProviderUnavailable
from fem_workflow import accepted_artifacts
from storage import ConflictError


def explain_report(*, store, project_id, spec, result, provider):
    result.assert_matches(spec)
    if result.status != "succeeded" or result.provenance != "actual_solver":
        raise ValueError("Explain only an actual successful solver result")
    review, _ = accepted_artifacts(store, project_id)
    identity = (spec.accepted_revision_id, spec.geometry_hash)
    if (review.revision_id, review.geometry_hash) != identity:
        raise ConflictError("Report geometry is stale")
    existing = [r for r in store.records(project_id, "ReportExplanation") if r.run_id == result.run_id]
    if existing:
        return existing[-1]
    raw = provider.generate(system_instruction=(
        "Explain actual preliminary linear-static results in plain language. Return JSON matching ReportExplanation. "
        "Copy the analysis_id, run_id, accepted_revision_id and geometry_hash exactly. "
        "Do not invent acceptance criteria, convergence, fatigue, durability or safety conclusions. "
        "Keep numerical values in the deterministic report; use prose to explain displacement, von Mises stress, "
        "support reactions and idealized boundary conditions. Mention single-mesh and stock-certification limitations."),
        prompt=json.dumps({"analysis_specification":spec.model_dump(mode="json"),
                           "actual_solver_results":result.model_dump(mode="json"),
                           "response_schema":ReportExplanation.model_json_schema()}))
    try:
        explanation=ReportExplanation.model_validate_json(raw)
    except (ValidationError, ValueError):
        raise ProviderUnavailable("Report explanation was not valid structured output; deterministic results are preserved") from None
    if (explanation.analysis_id,explanation.run_id,explanation.accepted_revision_id,explanation.geometry_hash) != (
            spec.analysis_id,result.run_id,*identity):
        raise ValueError("Explanation does not match the actual solver result")
    current, _ = accepted_artifacts(store, project_id)
    if (current.revision_id,current.geometry_hash) != identity:
        raise ConflictError("Accepted geometry changed during explanation")
    store.save_record(project_id, explanation.explanation_id, 1, explanation)
    store.write_once(f"projects/{project_id}/explanations/{explanation.explanation_id}.json",
                     explanation.model_dump_json(indent=2).encode())
    return explanation

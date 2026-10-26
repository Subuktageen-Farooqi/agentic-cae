"""Gemini role: restricted CadQuery function, with one separate repair request."""
import json
from typing import Sequence

from pydantic import ValidationError
from providers.vertex import ImagePayload, VisionTextProvider
from schemas import CADGeneration, Contract, DesignSpec, Nonempty
from workers.code_validation import ALLOWED_METHODS, validate_code


class CADReply(Contract):
    code: Nonempty
    explanation: Nonempty


def cad_parameters(spec: DesignSpec) -> dict[str, float]:
    factors = {"mm": 1.0, "m": 1000.0, "in": 25.4, "deg": 1.0}
    return {d.name: d.value * factors[d.unit] for d in spec.dimensions}


def create_cad(*, spec: DesignSpec, attempt_id: str, revision_id: str, provider: VisionTextProvider,
               images: Sequence[ImagePayload] = (), previous: CADGeneration | None = None,
               technical_error: str | None = None, previous_revision: CADGeneration | None = None,
               design_feedback: dict | None = None) -> CADGeneration:
    if previous and (previous.technical_repair_count >= 1 or not technical_error):
        raise ValueError("One technical repair per generated revision; actual failure evidence is required")
    payload = {"spec": spec.model_dump(mode="json"), "parameters_mm_or_degrees": cad_parameters(spec),
               "reply_schema": CADReply.model_json_schema(), "allowed_cadquery_methods": sorted(ALLOWED_METHODS)}
    if previous:
        payload.update(previous_code=previous.code, technical_error=technical_error)
    if previous_revision:
        payload.update(previous_revision_code=previous_revision.code, design_feedback=design_feedback,
                       revision_instruction="Propose a reasoned revision from the requirements and saved feedback. Explain what changed; do not invent a reason for thumbs-only rejection.")
    raw = provider.generate(system_instruction="""Return JSON with code and explanation for one supported solid.
Code must contain only def build(params), returning a CadQuery Workplane shape.
The trusted worker supplies cq (cadquery), params, imports, exports and paths.
No imports, file/network/shell operations, infrastructure, dunder attributes,
decorators or nested functions. Use only the supplied approved CadQuery methods
and numeric helpers. Dimensions in params are already converted to mm (or degrees).
Preserve unaffected requirements. If repairing, use the actual error evidence.
Never claim a build or engineering analysis has run.""", prompt=json.dumps(payload), images=images)
    reply = CADReply.model_validate_json(raw)
    # Validation is performed by the orchestrator so rejected code and the
    # actual rejection reason can be retained and repaired once.
    return CADGeneration(attempt_id=attempt_id, revision_id=revision_id, spec_id=spec.spec_id,
        spec_version=spec.version, code=reply.code, parameters=cad_parameters(spec), explanation=reply.explanation,
        technical_repair_count=1 if previous else 0,
        previous_generation_id=previous.generation_id if previous else None)

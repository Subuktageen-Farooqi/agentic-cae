"""Vertex role: a frozen brief becomes a validated, requirement-preserving spec."""
from __future__ import annotations

import json
from typing import Sequence

from pydantic import ValidationError
from providers.vertex import ImagePayload, ProviderUnavailable, VisionTextProvider
from schemas import Contract, DesignBrief, DesignSpec, Nonempty, ValueOrigin


class SpecificationError(ValueError):
    pass


class UnsupportedDesign(Contract):
    unsupported_reason: Nonempty
    supported_simplification: Nonempty


def validate_against_brief(spec: DesignSpec, brief: DesignBrief) -> None:
    if (spec.brief_id, spec.brief_version) != (brief.brief_id, brief.version):
        raise SpecificationError("Specification does not reference the frozen brief version")
    for label in ("hard_requirements", "soft_requirements", "accepted_decisions", "reference_image_ids"):
        if getattr(spec, label) != getattr(brief, label):
            raise SpecificationError(f"Specification must preserve {label} exactly")
    if brief.materials and spec.material_intent != ", ".join(brief.materials):
        raise SpecificationError("Specification must preserve the brief's material intent")
    known = {d.name.casefold(): d for d in brief.dimensions}
    actual = {d.name.casefold(): d for d in spec.dimensions}
    if len(actual) != len(spec.dimensions):
        raise SpecificationError("Dimension names must be unique ignoring case")
    for name, dimension in known.items():
        if actual.get(name) != dimension:
            raise SpecificationError(f"Specification changed or removed known dimension: {dimension.name}")
    for name, dimension in actual.items():
        if name not in known and dimension.origin != ValueOrigin.INFERRED:
            raise SpecificationError("New model-chosen dimensions must be labeled inferred")
    if not spec.dimensions or not spec.features:
        raise SpecificationError("A supported solid needs dimensions and at least one geometric feature")
    if any(name not in known for name in actual) and not spec.assumptions:
        raise SpecificationError("Inferred dimensions need visible assumptions")


def write_spec(*, brief: DesignBrief, provider: VisionTextProvider,
               images: Sequence[ImagePayload] = ()) -> DesignSpec:
    prompt = json.dumps({"frozen_brief": brief.model_dump(mode="json"),
                         "output_schema": DesignSpec.model_json_schema()}, ensure_ascii=False)
    raw = provider.generate(system_instruction="""Create a DesignSpec JSON object for one simple connected solid.
Support prismatic extrusions, holes, cuts, unions and basic fillets only. Decline
assemblies or unsupported geometry; do not silently replace the requested object.
For an unsupported request return only unsupported_reason and supported_simplification
as two nonempty JSON strings instead of a DesignSpec.
Where a dimension specifies an overall axis-aligned extent, include its name in
bounding_dimensions (x/y/z). Do not map a hole diameter to an overall extent.
Preserve frozen brief identity/version, all requirements, known dimensions with
provenance, accepted decisions and image IDs exactly. Set material_intent to the
comma-separated brief.materials when specified. Add reasonable dimensions only
with origin inferred and visible assumptions. Never infer measurements,
loads or material properties from unscaled images. Do not perform analysis or
invent an engineering pass. Output only the supplied JSON schema.""", prompt=prompt, images=images)
    try:
        payload = json.loads(raw)
        if isinstance(payload, dict) and "unsupported_reason" in payload:
            refusal = UnsupportedDesign.model_validate(payload)
            raise SpecificationError(refusal.unsupported_reason + " Supported simplification: " + refusal.supported_simplification)
        spec = DesignSpec.model_validate_json(raw)
    except (ValidationError, json.JSONDecodeError) as error:
        raise SpecificationError("Specification response did not match DesignSpec") from error
    validate_against_brief(spec, brief)
    return spec

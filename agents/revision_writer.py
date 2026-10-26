"""Apply saved user feedback to the shared brief without losing other requirements."""
import json
from pydantic import Field
from agents.advisor import AdvisorReply, BriefUpdates, apply_reply_to_brief, explicit_dimension_edit
from schemas import Contract, DesignBrief, Dimension, Nonempty


class RequirementUpdate(Contract):
    requirement_id: Nonempty
    text: Nonempty
    evidence_quote: Nonempty


class RevisionReply(Contract):
    explanation: str = Field(min_length=1)
    brief_updates: BriefUpdates = Field(default_factory=BriefUpdates)
    dimension_updates: list[Dimension] = Field(default_factory=list)
    hard_requirement_updates: list[RequirementUpdate] = Field(default_factory=list)
    soft_requirement_updates: list[RequirementUpdate] = Field(default_factory=list)


def revise_brief(*, brief, previous_spec, feedback, provider, images):
    dimensions = {d.name.casefold(): d for d in previous_spec.dimensions}
    dimensions.update({d.name.casefold(): d for d in brief.dimensions})
    source = DesignBrief.model_validate({**brief.model_dump(), "dimensions": list(dimensions.values()),
        "reference_image_ids": list(dict.fromkeys(brief.reference_image_ids + feedback.reference_image_ids))})
    direct = explicit_dimension_edit(source, feedback.text)
    if direct:
        return apply_reply_to_brief(source, direct)
    if not feedback.text.strip() and not feedback.reference_image_ids:
        return source.model_copy(update={"version": source.version + 1,
            "assumptions": source.assumptions + ["User requested a revision without stating a reason; propose a reasoned alternative using existing requirements."]})
    raw = provider.generate(system_instruction="""Apply this design revision feedback to the existing brief.
Preserve every unaffected requirement, dimension, material choice and accepted
decision. Return the supplied patch schema; only explicit user changes belong
in brief_updates/dimension_updates. New inferred values need visible assumptions.
Images are desired references, not screenshots of the generated model unless
labeled as such. Never infer exact dimensions or material properties from photos.
Do not invent why the user disliked the design. CAD regeneration will follow.
Only update an existing hard/soft requirement when the user's feedback explicitly
names that requirement ID. Include an exact evidence_quote from that feedback;
preserve every other requirement and its stable ID. Otherwise leave requirement
updates empty and retain the requirement.""",
        prompt=json.dumps({"brief": source.model_dump(mode="json"), "previous_spec": previous_spec.model_dump(mode="json"),
                           "feedback": feedback.model_dump(mode="json"), "schema": RevisionReply.model_json_schema()}), images=images)
    reply = RevisionReply.model_validate_json(raw)
    requirements = {}
    for field, changes in (("hard_requirements", reply.hard_requirement_updates), ("soft_requirements", reply.soft_requirement_updates)):
        current = {r.requirement_id: r for r in getattr(source, field)}
        if len({change.requirement_id for change in changes}) != len(changes):
            raise ValueError("Requirement changes must have unique stable IDs")
        for change in changes:
            if (change.requirement_id not in current or change.requirement_id not in feedback.text or
                    change.evidence_quote not in feedback.text):
                raise ValueError("Requirement changes need an existing ID and exact evidence from explicit user feedback")
            current[change.requirement_id] = current[change.requirement_id].model_copy(update={"text": change.text, "confirmed": True})
        requirements[field] = list(current.values())
    source = DesignBrief.model_validate({**source.model_dump(), **requirements})
    return apply_reply_to_brief(source, AdvisorReply(text=reply.explanation, brief_updates=reply.brief_updates,
                                                    dimension_updates=reply.dimension_updates))

import pytest

from app_logic import dimensions_from_lines, draft_brief, requirements_from_lines
from schemas import Dimension, Intake


def test_requirements_get_stable_distinct_ids_and_ignore_blank_lines():
    values = requirements_from_lines("Must fit\n\nMust be one part", "HARD")
    assert [item.requirement_id for item in values] == ["HARD-001", "HARD-002"]
    assert all(item.confirmed for item in values)


def test_dimensions_accept_explicit_or_selected_units_and_reject_bad_lines():
    values = dimensions_from_lines("length = 100 mm\nwidth=2.5", "in")
    assert [(item.name, item.value, item.unit, item.origin.value) for item in values] == [
        ("length", 100, "mm", "user_provided"), ("width", 2.5, "in", "user_provided")]
    with pytest.raises(ValueError, match="look like"):
        dimensions_from_lines("about one hundred", "mm")
    with pytest.raises(ValueError, match="unique"):
        dimensions_from_lines("length=1 mm\nLength=2 mm", None)


def test_both_routes_produce_same_brief_contract_and_preserve_images():
    intake = Intake(idea="A mounting bracket", reference_image_ids=["image-1"])
    advisor = draft_brief(intake, automatic=False)
    automatic = draft_brief(intake, automatic=True)
    assert type(advisor) is type(automatic)
    assert advisor.reference_image_ids == automatic.reference_image_ids == ["image-1"]
    assert advisor.unresolved_questions and not advisor.assumptions
    assert automatic.assumptions and not automatic.unresolved_questions


def test_known_inputs_are_not_reasked_or_recast_as_assumptions():
    intake = Intake(idea="Bracket", purpose="Hold a sensor",
                    dimensions=[Dimension(name="length", value=50, unit="mm", origin="user_provided")],
                    material_preferences=["Aluminum"])
    for automatic in (False, True):
        brief = draft_brief(intake, automatic=automatic)
        assert brief.purpose == "Hold a sensor" and brief.dimensions == intake.dimensions
        assert brief.materials == ["Aluminum"]
        assert brief.assumptions == [] and brief.unresolved_questions == []

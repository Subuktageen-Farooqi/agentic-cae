"""Pure intake/brief helpers shared by Streamlit and focused tests."""

from __future__ import annotations

import re

from schemas import DesignBrief, Dimension, Intake, Requirement


def requirements_from_lines(text: str, prefix: str) -> list[Requirement]:
    lines = [line.strip() for line in text.splitlines() if line.strip()]
    return [Requirement(requirement_id=f"{prefix}-{index:03d}", text=line, confirmed=True)
            for index, line in enumerate(lines, 1)]


def dimensions_from_lines(text: str, default_unit: str | None) -> list[Dimension]:
    values: list[Dimension] = []
    pattern = re.compile(r"^\s*([^=]+?)\s*=\s*([0-9]+(?:\.[0-9]+)?)\s*(mm|m|in)?\s*$", re.I)
    for line_number, line in enumerate(text.splitlines(), 1):
        if not line.strip():
            continue
        match = pattern.match(line)
        if not match:
            raise ValueError(f"Dimension line {line_number} must look like: length = 100 mm")
        name, number, unit = match.groups()
        selected_unit = (unit or default_unit or "").lower()
        if selected_unit not in ("mm", "m", "in"):
            raise ValueError(f"Dimension line {line_number} needs mm, m, or in")
        values.append(Dimension(name=name.strip(), value=float(number), unit=selected_unit,
                                origin="user_provided"))
    if len({item.name.casefold() for item in values}) != len(values):
        raise ValueError("Dimension names must be unique")
    return values


def draft_brief(intake: Intake, *, automatic: bool) -> DesignBrief:
    name = intake.idea.strip().splitlines()[0][:80]
    assumptions: list[str] = []
    questions: list[str] = []
    if not intake.purpose:
        (assumptions if automatic else questions).append(
            "Purpose is not specified; infer only enough to propose a supported simple part." if automatic
            else "What should this design accomplish?")
    if not intake.dimensions:
        (assumptions if automatic else questions).append(
            "Dimensions will be inferred for an initial supported concept and remain clearly marked inferred."
            if automatic else "Which overall dimensions or interfaces are already known?")
    if not intake.material_preferences:
        (assumptions if automatic else questions).append(
            "Material remains unresolved until required by design or analysis."
            if automatic else "Do you have a material or manufacturing preference?")
    return DesignBrief(
        design_name=name, description=intake.idea, purpose=intake.purpose,
        hard_requirements=intake.hard_requirements, soft_requirements=intake.soft_requirements,
        dimensions=intake.dimensions, materials=intake.material_preferences,
        manufacturing=intake.manufacturing_preferences,
        reference_image_ids=intake.reference_image_ids,
        assumptions=assumptions, unresolved_questions=questions,
    )

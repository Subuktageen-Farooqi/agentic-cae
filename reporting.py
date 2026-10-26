"""Deterministic JSON/Markdown rendering from validated specs and results."""

from __future__ import annotations

import json

from schemas import AnalysisResults, AnalysisSpec, DesignSpec


NO_CRITERION = "Computed; acceptance criterion not provided."


def _cell(value) -> str:
    return str(value).replace("|", "\\|").replace("\n", "<br>")


def render_design_spec(spec: DesignSpec) -> str:
    """One validated JSON contract is the sole source of the human-readable spec."""
    spec = DesignSpec.model_validate_json(spec.model_dump_json())
    lines = [f"# {spec.design_name}", "", spec.purpose, "",
             f"- Spec: `{spec.spec_id}` v{spec.version}",
             f"- Frozen brief: `{spec.brief_id}` v{spec.brief_version}",
             f"- Units: {spec.units}; coordinate system: {spec.coordinate_system}", "",
             "## Dimensions", "", "| Name | Value | Unit | Origin | Tolerance |", "| --- | ---: | --- | --- | --- |"]
    for d in spec.dimensions:
        origin = d.origin.value + (f" (accepted from {d.accepted_from})" if d.accepted_from else "")
        lines.append(f"| {_cell(d.name)} | {d.value:g} | {d.unit} | {origin} | {d.tolerance if d.tolerance is not None else 'not specified'} |")
    for title, requirements in [("Hard requirements", spec.hard_requirements), ("Preferences", spec.soft_requirements)]:
        lines.extend(["", "## " + title, "", "| ID | Requirement | Verification | Confirmed |", "| --- | --- | --- | --- |"])
        lines.extend(f"| {_cell(r.requirement_id)} | {_cell(r.text)} | {_cell(r.verification_method or 'not specified')} | {r.confirmed} |" for r in requirements)
    lines.extend(["", "## Features", ""] + [f"- {f.feature_id}: {f.kind} — {f.description}; parameters: {', '.join(f.parameter_names)}" for f in spec.features])
    for title, values in [("Material intent", [spec.material_intent] if spec.material_intent else []),
                          ("Manufacturing", spec.manufacturing_intent),
                          ("Accepted decisions", [d.text for d in spec.accepted_decisions]),
                          ("Assumptions", spec.assumptions), ("Unresolved questions", spec.unresolved_questions),
                          ("Reference image IDs", spec.reference_image_ids)]:
        lines.extend(["", "## " + title, ""] + (["- " + value for value in values] or ["None recorded."]))
    return "\n".join(lines).rstrip() + "\n"


def render_analysis_spec(spec: AnalysisSpec) -> str:
    lines = ["# FreeCAD FEM analysis specification", "", spec.engineering_question, "",
             "Review material, loads, supports, units and actual regions before confirmation.", "",
             "```json", spec.model_dump_json(indent=2), "```", ""]
    return "\n".join(lines)


def results_json(results: AnalysisResults) -> str:
    return results.model_dump_json(indent=2)


def render_report(spec: AnalysisSpec, results: AnalysisResults) -> str:
    results.assert_matches(spec)
    lines = [
        "# Engineering analysis report", "",
        f"- Design revision: `{spec.accepted_revision_id}`",
        f"- Geometry SHA-256: `{spec.geometry_hash}`",
        f"- Analysis question: {spec.engineering_question}",
        f"- Analysis type: {spec.analysis_type.value}",
        f"- Unit system: {spec.unit_system}",
        f"- Solver status: **{results.status.upper()}**", "",
        f"- Solver: {results.solver_version or 'unavailable'}",
        f"- Evidence provenance: {results.provenance}", "",
    ]
    if spec.material:
        lines.extend(["## Material", "", f"- {spec.material.name} (`{spec.material.material_id}`)",
                      f"- Property source: {spec.material.property_source}", ""])
    lines.extend(["## Setup", "",
                  f"- Supports: {len(spec.supports)}", f"- Loads: {len(spec.loads)}",
                  f"- Mesh target: {spec.mesh.element_size_mm:g} mm, {spec.mesh.order}" if spec.mesh else "- Mesh: missing",
                  ""])
    if results.status != "succeeded":
        lines.extend(["## Failure / blocked result", "", results.error or "Solve did not complete.", "",
                      "No numerical solver results are available.", ""])
    else:
        limits = {item.quantity: item.maximum for item in spec.acceptance_limits}
        values = [("Maximum total displacement", "maximum_displacement_mm", results.maximum_displacement_mm, "mm"),
                  ("Maximum equivalent (von Mises) stress", "maximum_von_mises_mpa", results.maximum_von_mises_mpa, "MPa")]
        lines.extend(["## Numerical results", "", "| Quantity | Value | Acceptance |", "| --- | ---: | --- |"])
        for label, key, value, unit in values:
            criterion = (f"≤ {limits[key]:g} {unit}: {'PASS' if value <= limits[key] else 'FAIL'}"
                         if key in limits else NO_CRITERION)
            lines.append(f"| {label} | {value} {unit} | {criterion} |")
        reaction = results.reaction_force_n
        lines.extend(["", f"- Reaction force: ({reaction[0]}, {reaction[1]}, {reaction[2]}) N",
                      f"- Mesh: {results.mesh.nodes} nodes, {results.mesh.elements} elements", ""])
        applied = tuple(sum(load.force_n[axis] for load in spec.loads) for axis in range(3))
        imbalance = tuple(applied[axis] + reaction[axis] for axis in range(3))
        lines.append(f"- Force-equilibrium residual: ({imbalance[0]:g}, {imbalance[1]:g}, {imbalance[2]:g}) N")
        lines.extend(["", "## Result images", ""] + [f"![Nodal result]({path})" for path in results.image_paths])
    lines.extend(["## Assumptions and limitations", ""])
    for item in spec.assumptions + results.limitations:
        lines.append(f"- {item}")
    if results.status == "succeeded":
        lines.append("- Peak stresses at idealized constraints require engineering interpretation.")
    return "\n".join(lines).rstrip() + "\n"

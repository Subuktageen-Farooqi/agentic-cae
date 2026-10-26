"""Deterministic JSON/Markdown rendering from validated specs and results."""

from __future__ import annotations

import json

from schemas import AnalysisResults, AnalysisSpec


NO_CRITERION = "Computed; acceptance criterion not provided."


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
            lines.append(f"| {label} | {value:g} {unit} | {criterion} |")
        reaction = results.reaction_force_n
        lines.extend(["", f"- Reaction force: ({reaction[0]:g}, {reaction[1]:g}, {reaction[2]:g}) N",
                      f"- Mesh: {results.mesh.nodes} nodes, {results.mesh.elements} elements", ""])
    lines.extend(["## Assumptions and limitations", ""])
    for item in spec.assumptions + results.limitations:
        lines.append(f"- {item}")
    if results.status == "succeeded":
        lines.append("- Peak stresses at idealized constraints require engineering interpretation.")
    return "\n".join(lines).rstrip() + "\n"

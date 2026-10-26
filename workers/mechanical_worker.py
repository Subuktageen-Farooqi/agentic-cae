"""Truthful PyMechanical availability boundary.

No mock is selected here. Until an installed Mechanical version, compatible
PyMechanical and a licensed launch are verified, execution returns BLOCKED with
no numerical results. A future version-specific adapter will own face queries,
named selections, mesh, solve, extraction, exports and cleanup.
"""

from __future__ import annotations

import importlib.util
from pathlib import Path

from analysis.static_structural_template import validate_static_setup
from schemas import AnalysisResults, AnalysisSpec


def availability(mechanical_exe: str | None) -> tuple[bool, str]:
    if not mechanical_exe or not Path(mechanical_exe).is_file():
        return False, "Ansys Mechanical executable is not configured or was not found"
    if importlib.util.find_spec("ansys.mechanical.core") is None:
        return False, "PyMechanical is not installed; compatibility must be matched to the installed Mechanical version"
    return False, "Mechanical/PyMechanical version compatibility and license launch have not been verified"


def execute_static_or_block(*, spec: AnalysisSpec, accepted_step: Path,
                            mechanical_exe: str | None) -> AnalysisResults:
    validate_static_setup(spec, accepted_step)
    available, reason = availability(mechanical_exe)
    if not available:
        return AnalysisResults(
            analysis_id=spec.analysis_id, analysis_spec_version=spec.version,
            accepted_revision_id=spec.accepted_revision_id, geometry_hash=spec.geometry_hash,
            status="blocked", provenance="unavailable", error=reason,
            limitations=["No solver was run and no numerical result was fabricated."],
        )
    raise RuntimeError("Internal availability error: unverified solver execution cannot proceed")

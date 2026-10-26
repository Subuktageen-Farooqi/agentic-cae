"""Fixed, parameterized linear-static setup boundary.

LLM output may populate a validated AnalysisSpec. It never writes solver code.
Actual face resolution, named selections, meshing, solve and extraction must be
implemented inside the version-compatible Mechanical session adapter.
"""

from __future__ import annotations

import hashlib
from pathlib import Path

from analysis.selectors import validate_distinct_regions
from schemas import AnalysisSpec, AnalysisType


def validate_static_setup(spec: AnalysisSpec, accepted_step: Path) -> None:
    if spec.analysis_type != AnalysisType.LINEAR_STATIC:
        raise ValueError("Only linear static structural analysis is executable")
    issues = spec.execution_issues()
    if issues:
        raise ValueError("Analysis setup is incomplete: " + "; ".join(issues))
    if not accepted_step.is_file():
        raise FileNotFoundError(accepted_step)
    digest = hashlib.sha256(accepted_step.read_bytes()).hexdigest()
    if digest != spec.geometry_hash:
        raise ValueError("Accepted STEP hash differs from AnalysisSpec geometry hash")
    selectors = {item.selector_id: item for item in spec.selectors}
    validate_distinct_regions([selectors[item.selector_id] for item in spec.supports],
                              [selectors[item.selector_id] for item in spec.loads])

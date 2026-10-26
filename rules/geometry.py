from __future__ import annotations

from collections.abc import Mapping

from schemas import GeometryMetrics, RuleResult, RuleStatus


def _boolean(rule_id: str, actual: bool, message: str) -> RuleResult:
    return RuleResult(rule_id=rule_id, status=RuleStatus.PASS if actual else RuleStatus.FAIL,
                      mandatory=True, measured_value=actual, expected_value=True,
                      message=message, evidence_path=None)


def core_geometry_rules(metrics: GeometryMetrics) -> list[RuleResult]:
    return [
        _boolean("geometry.step_import", metrics.step_import_succeeded, "STEP import succeeded" if metrics.step_import_succeeded else "STEP import failed"),
        _boolean("geometry.nonempty", metrics.shape_nonempty, "Imported shape is nonempty" if metrics.shape_nonempty else "Imported shape is empty"),
        _boolean("geometry.valid", metrics.shape_valid, "FreeCAD reports a valid shape" if metrics.shape_valid else "FreeCAD reports an invalid shape"),
        RuleResult(rule_id="geometry.one_solid", status=RuleStatus.PASS if metrics.solid_count == 1 else RuleStatus.FAIL,
                   mandatory=True, measured_value=metrics.solid_count, expected_value=1,
                   message=f"Supported scope requires exactly one solid; measured {metrics.solid_count}",
                   evidence_path=metrics.evidence_path),
        RuleResult(rule_id="geometry.positive_volume", status=RuleStatus.PASS if metrics.volume_mm3 > 0 else RuleStatus.FAIL,
                   mandatory=True, measured_value=metrics.volume_mm3, expected_value="> 0", unit="mm^3",
                   message=f"Volume is {metrics.volume_mm3:.6g} mm^3", evidence_path=metrics.evidence_path),
    ]


def bounding_dimension_rules(metrics: GeometryMetrics, expected_mm: Mapping[str, tuple[float, float]]) -> list[RuleResult]:
    if metrics.bounding_box is None:
        return [RuleResult(rule_id=f"geometry.bounding_box:{axis}", status=RuleStatus.FAIL,
                           mandatory=True, expected_value=value[0], tolerance=value[1], unit="mm",
                           message="Bounding box unavailable", evidence_path=metrics.evidence_path)
                for axis, value in expected_mm.items()]
    minimum, maximum = metrics.bounding_box.minimum, metrics.bounding_box.maximum
    actual = {"x": maximum[0] - minimum[0], "y": maximum[1] - minimum[1], "z": maximum[2] - minimum[2]}
    results = []
    for axis, (expected, tolerance) in expected_mm.items():
        difference = abs(actual[axis] - expected)
        results.append(RuleResult(rule_id=f"geometry.bounding_box:{axis}",
                                  status=RuleStatus.PASS if difference <= tolerance else RuleStatus.FAIL,
                                  mandatory=True, measured_value=actual[axis], expected_value=expected,
                                  tolerance=tolerance, unit="mm",
                                  message=f"Bounding {axis.upper()} is {actual[axis]:.6g} mm; expected {expected:.6g} ± {tolerance:.6g} mm",
                                  evidence_path=metrics.evidence_path))
    return results


def mandatory_geometry_passes(results: list[RuleResult]) -> bool:
    return not any(result.mandatory and result.status != RuleStatus.PASS for result in results)

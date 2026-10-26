import pytest

from rules.geometry import bounding_dimension_rules, core_geometry_rules, mandatory_geometry_passes
from rules.manufacturing import scaffolded_rules
from rules.registry import RuleRegistry
from schemas import BoundingBox, GeometryMetrics, RuleStatus


def metrics(**updates):
    values = dict(revision_id="r", geometry_hash="a" * 64, step_import_succeeded=True,
                  shape_nonempty=True, shape_valid=True, solid_count=1, volume_mm3=20000,
                  bounding_box=BoundingBox(minimum=(0, -10, -5), maximum=(100, 10, 5)),
                  evidence_path="projects/p/freecad_metrics.json")
    values.update(updates)
    return GeometryMetrics(**values)


def test_real_core_and_bounding_rules_pass_expected_cantilever():
    results = core_geometry_rules(metrics()) + bounding_dimension_rules(
        metrics(), {"x": (100, 0.01), "y": (20, 0.01), "z": (10, 0.01)})
    assert len(results) == 8
    assert all(result.status == RuleStatus.PASS for result in results)
    assert mandatory_geometry_passes(results)


@pytest.mark.parametrize("updates,failed", [
    ({"step_import_succeeded": False}, "geometry.step_import"),
    ({"shape_nonempty": False}, "geometry.nonempty"),
    ({"shape_valid": False}, "geometry.valid"),
    ({"solid_count": 2}, "geometry.one_solid"),
    ({"volume_mm3": 0}, "geometry.positive_volume"),
])
def test_mandatory_geometry_failure_blocks_acceptance(updates, failed):
    results = core_geometry_rules(metrics(**updates))
    assert next(item for item in results if item.rule_id == failed).status == RuleStatus.FAIL
    assert not mandatory_geometry_passes(results)


def test_out_of_tolerance_and_missing_bbox_fail():
    bad = bounding_dimension_rules(metrics(), {"x": (101, 0.01)})
    missing = bounding_dimension_rules(metrics(bounding_box=None), {"x": (100, 0.01)})
    assert bad[0].status == RuleStatus.FAIL and missing[0].status == RuleStatus.FAIL
    assert not mandatory_geometry_passes(bad + missing)


def test_scaffolded_rules_never_pass():
    results = scaffolded_rules(metrics())
    assert len(results) == 4
    assert all(result.status == RuleStatus.NOT_IMPLEMENTED and not result.mandatory for result in results)


def test_registry_is_extensible_and_rejects_duplicate_or_mismatched_ids():
    registry = RuleRegistry()
    registry.register("geometry", core_geometry_rules)
    assert len(registry.evaluate(metrics())) == 5
    with pytest.raises(ValueError, match="Duplicate"):
        registry.register("geometry", core_geometry_rules)
    broken = RuleRegistry()
    broken.register("expected", lambda _: core_geometry_rules(metrics())[0])
    with pytest.raises(ValueError, match="mismatched"):
        broken.evaluate(metrics())

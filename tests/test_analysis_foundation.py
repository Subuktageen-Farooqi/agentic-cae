import hashlib

import pytest
from pydantic import ValidationError

from analysis.sanity import (cantilever_tip_displacement_mm, reaction_imbalance_n,
                             rectangular_second_moment_mm4, relative_difference, vector_magnitude)
from analysis.selectors import selector_intent, validate_distinct_regions
from analysis.static_structural_template import validate_static_setup
from reporting import NO_CRITERION, render_report, results_json
from schemas import (AcceptanceLimit, AnalysisResults, AnalysisSpec, BoundingBox, GeometryMetrics,
                     Load, Material, MeshInformation, MeshSettings, RegionSelector, Support)
from workers.fem_worker import availability, execute_static_or_block


def test_existing_executable_without_fem_dependencies_is_blocked():
    import sys
    assert availability(sys.executable, None, None)[0] is False


def geometry():
    return GeometryMetrics(revision_id="revision", geometry_hash="a" * 64, step_import_succeeded=True,
                           shape_nonempty=True, shape_valid=True, solid_count=1, volume_mm3=20000,
                           bounding_box=BoundingBox(minimum=(0, -10, -5), maximum=(100, 10, 5)),
                           evidence_path="metrics.json")


def spec(step, *, supported=True):
    digest = hashlib.sha256(step.read_bytes()).hexdigest()
    return AnalysisSpec(analysis_id="analysis", accepted_revision_id="revision", geometry_hash=digest,
                        analysis_type="linear_static_structural", engineering_question="Tip deflection?",
                        material=Material(material_id="fixture", name="Fixture material",
                                          property_source="Test fixture; not execution allowlist",
                                          youngs_modulus_mpa=200000, poissons_ratio=0.3, density_kg_m3=7850),
                        selectors=[RegionSelector(selector_id="fixed", kind="planar_min_x",
                                                  position_tolerance_mm=.01, normal_tolerance_degrees=1),
                                   RegionSelector(selector_id="load", kind="planar_max_x",
                                                  position_tolerance_mm=.01, normal_tolerance_degrees=1)],
                        supports=[Support(selector_id="fixed")], loads=[Load(selector_id="load", force_n=(0, -100, 0))],
                        mesh=MeshSettings(element_size_mm=2),
                        requested_outputs=["displacement", "von_mises", "reaction_forces"],
                        assumptions=["Linear elastic small-deflection model"], execution_supported=supported)


def test_selector_intents_are_explicitly_unresolved_and_unit_aware():
    minimum = selector_intent(RegionSelector(selector_id="fixed", kind="planar_min_x",
                                             position_tolerance_mm=.01, normal_tolerance_degrees=1), geometry())
    maximum = selector_intent(RegionSelector(selector_id="load", kind="planar_max_x",
                                             position_tolerance_mm=.01, normal_tolerance_degrees=1), geometry())
    assert (minimum.expected_x_mm, minimum.outward_normal) == (0, (-1, 0, 0))
    assert (maximum.expected_x_mm, maximum.outward_normal) == (100, (1, 0, 0))
    assert minimum.verification_status == "UNRESOLVED_IN_FREECAD_FEM"


def test_invalid_or_overlapping_selector_intent_rejected():
    selector = RegionSelector(selector_id="same", kind="planar_min_x",
                              position_tolerance_mm=.01, normal_tolerance_degrees=1)
    with pytest.raises(ValueError, match="overlap"):
        validate_distinct_regions([selector], [selector])
    with pytest.raises(ValueError, match="valid imported"):
        selector_intent(selector, geometry().model_copy(update={"shape_valid": False}))


def test_static_setup_hash_and_missing_inputs_gate(tmp_path):
    step = tmp_path / "model.step"
    step.write_bytes(b"accepted geometry fixture")
    validate_static_setup(spec(step), step)
    with pytest.raises(ValueError, match="hash"):
        validate_static_setup(spec(step).model_copy(update={"geometry_hash": "b" * 64}), step)
    with pytest.raises(ValueError, match="incomplete"):
        validate_static_setup(spec(step).model_copy(update={"material": None}), step)


def test_absent_freecad_fem_returns_blocked_with_no_numbers(tmp_path):
    step = tmp_path / "model.step"
    step.write_bytes(b"accepted geometry fixture")
    value = execute_static_or_block(spec=spec(step), accepted_step=step, freecad_cmd=None)
    assert value.status == "blocked" and value.provenance == "unavailable"
    assert value.maximum_displacement_mm is None and value.maximum_von_mises_mpa is None
    assert "not configured" in value.error.lower()


def test_beam_theory_and_reaction_sanity_under_matching_assumptions():
    inertia = rectangular_second_moment_mm4(20, 10)
    estimate = cantilever_tip_displacement_mm(force_n=100, length_mm=100,
                                              youngs_modulus_mpa=200000, second_moment_mm4=inertia)
    assert inertia == pytest.approx(1666.6666667)
    assert estimate == pytest.approx(0.1)
    assert relative_difference(0.101, estimate) == pytest.approx(0.01)
    imbalance = reaction_imbalance_n((0, -100, 0), (0, 100, 0))
    assert vector_magnitude(imbalance) == 0


def test_blocked_report_is_failure_report_without_fake_values(tmp_path):
    step = tmp_path / "model.step"
    step.write_bytes(b"accepted geometry fixture")
    setup = spec(step)
    blocked = execute_static_or_block(spec=setup, accepted_step=step, freecad_cmd=None)
    report = render_report(setup, blocked)
    assert "BLOCKED" in report and "No numerical solver results" in report
    assert "Maximum total displacement" not in report
    assert '"maximum_displacement_mm": null' in results_json(blocked)


def test_success_report_uses_exact_no_criterion_phrase_and_supplied_limits(tmp_path):
    step = tmp_path / "model.step"
    step.write_bytes(b"accepted geometry fixture")
    setup = spec(step).model_copy(update={"acceptance_limits": [
        AcceptanceLimit(quantity="maximum_displacement_mm", maximum=0.2)]})
    result = AnalysisResults(analysis_id=setup.analysis_id, analysis_spec_version=setup.version,
                             accepted_revision_id=setup.accepted_revision_id, geometry_hash=setup.geometry_hash,
                             status="succeeded", provenance="test_fixture", solver_version="fixture-only",
                             maximum_displacement_mm=.1, maximum_von_mises_mpa=12,
                             reaction_force_n=(0, 100, 0), mesh=MeshInformation(nodes=100, elements=20))
    report = render_report(setup, result)
    assert "≤ 0.2 mm: PASS" in report and NO_CRITERION in report
    assert "Preliminary single-mesh" in report and "idealized constraints" in report


def test_blocked_results_require_reason():
    with pytest.raises(ValidationError, match="explicit reason"):
        AnalysisResults(analysis_id="a", analysis_spec_version=1, accepted_revision_id="r",
                        geometry_hash="a" * 64, status="blocked", provenance="unavailable")

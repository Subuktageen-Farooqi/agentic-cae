import pytest
from pydantic import ValidationError

from schemas import (
    AnalysisRecommendation, AnalysisResults, AnalysisSpec, AnalysisType, Artifact,
    ArtifactManifest, BoundingBox, CADGeneration, DesignBrief, DesignFeedback,
    DesignSpec, Dimension, Feature, GeometryMetrics, Intake, Load, Material,
    MeshInformation, MeshSettings, RegionSelector, Requirement, RuleResult,
    RuleStatus, SourceReference, Support, ValueOrigin, WorkflowState,
)


HASH = "a" * 64


def minimal_spec():
    return DesignSpec(brief_id="brief", brief_version=1, design_name="Cantilever",
                      purpose="Test fixed-end loading", units="mm",
                      dimensions=[Dimension(name="length", value=100, unit="mm", origin="user_provided")],
                      features=[Feature(feature_id="beam", kind="extrusion", description="Solid beam",
                                        parameter_names=["length"])])


def analysis_spec():
    return AnalysisSpec(analysis_id="analysis", accepted_revision_id="revision", geometry_hash=HASH,
                        analysis_type=AnalysisType.LINEAR_STATIC, engineering_question="Displacement?",
                        selectors=[RegionSelector(selector_id="fixed", kind="planar_min_x",
                                                  position_tolerance_mm=0.01, normal_tolerance_degrees=1),
                                   RegionSelector(selector_id="loaded", kind="planar_max_x",
                                                  position_tolerance_mm=0.01, normal_tolerance_degrees=1)],
                        supports=[Support(selector_id="fixed")],
                        loads=[Load(selector_id="loaded", force_n=(0, -10, 0))],
                        material=Material(material_id="test-only", name="Test fixture, not verified material",
                                          property_source="Test fixture only", youngs_modulus_mpa=100,
                                          poissons_ratio=0.3, density_kg_m3=1000),
                        mesh=MeshSettings(element_size_mm=2), requested_outputs=["displacement"],
                        execution_supported=True)


def results():
    # Contract fixture, explicitly not an actual Mechanical solve.
    return AnalysisResults(analysis_id="analysis", analysis_spec_version=1,
                           accepted_revision_id="revision", geometry_hash=HASH,
                           status="succeeded", provenance="test_fixture", solver_version="fixture",
                           maximum_displacement_mm=1, maximum_von_mises_mpa=2,
                           reaction_force_n=(0, 10, 0), mesh=MeshInformation(nodes=20, elements=4))


def test_all_required_contracts_roundtrip():
    spec = minimal_spec()
    values = [
        Intake(idea="Incomplete idea"), DesignBrief(design_name="Arm"), spec,
        CADGeneration(attempt_id="a", revision_id="r", spec_id=spec.spec_id, spec_version=1,
                      code="def build(params): return None", parameters={"length": 100}, explanation="Fixture only"),
        GeometryMetrics(revision_id="r", geometry_hash=HASH, step_import_succeeded=False,
                        shape_nonempty=False, shape_valid=False, solid_count=0, volume_mm3=0,
                        evidence_path="error.log"),
        RuleResult(rule_id="wall", status="NOT_IMPLEMENTED", message="No wall thickness algorithm yet"),
        DesignFeedback(attempt_id="a", revision_id="r", action="revise", thumbs="down"),
        AnalysisRecommendation(analysis_type="linear_static_structural", name="Static",
                               engineering_question="Deflection?", why_relevant="Loading", required_inputs=["load"],
                               execution_supported=True),
        analysis_spec(), results(),
        ArtifactManifest(project_id="p", job_id="j", stage="failed", completed=False, artifacts=[]),
    ]
    for value in values:
        assert type(value).model_validate_json(value.model_dump_json()) == value
    assert len(WorkflowState) == 17


def test_unknown_fields_rejected_and_objects_frozen():
    with pytest.raises(ValidationError):
        Intake(idea="Arm", secretly_overwrite_intake=True)
    intake = Intake(idea="Arm")
    with pytest.raises(ValidationError):
        intake.idea = "Replacement"


@pytest.mark.parametrize("value", [0, -1, float("nan"), float("inf")])
def test_dimensions_require_finite_positive_values(value):
    with pytest.raises(ValidationError):
        Dimension(name="length", value=value, unit="mm", origin="inferred")


def test_dimensions_require_explicit_provenance_and_preserve_acceptance_origin():
    with pytest.raises(ValidationError):
        Dimension(name="length", value=10, unit="mm")
    with pytest.raises(ValidationError):
        Dimension(name="length", value=10, unit="mm", origin="accepted")
    value = Dimension(name="length", value=10, unit="mm", origin="accepted", accepted_from="inferred")
    assert value.origin == ValueOrigin.ACCEPTED and value.accepted_from == "inferred"


def test_requirement_ids_and_feature_references_are_checked():
    requirement = Requirement(requirement_id="R1", text="Fit available space")
    with pytest.raises(ValidationError, match="unique"):
        DesignBrief(design_name="Arm", hard_requirements=[requirement], soft_requirements=[requirement])
    spec = minimal_spec()
    with pytest.raises(ValidationError, match="declared dimensions"):
        DesignSpec.model_validate({**spec.model_dump(), "dimensions": []})
    with pytest.raises(ValidationError, match="unique"):
        DesignSpec.model_validate({**spec.model_dump(), "dimensions": spec.dimensions * 2})


def test_bad_bbox_rejected():
    with pytest.raises(ValidationError):
        BoundingBox(minimum=(10, 0, 0), maximum=(0, 5, 5))


@pytest.mark.parametrize("status", list(RuleStatus))
def test_rule_statuses_are_explicit(status):
    rule = RuleResult(rule_id="wall", status=status, message="Fixture")
    assert rule.status == status
    with pytest.raises(ValidationError):
        RuleResult(rule_id="wall", message="Cannot silently pass")


@pytest.mark.parametrize("fields", [
    {"thumbs": "down"}, {"text": "Make it shorter"},
    {"text": "Match this", "reference_image_ids": ["image"]},
    {"reference_image_ids": ["image"]},
])
def test_all_feedback_modes_validate(fields):
    assert DesignFeedback(attempt_id="a", revision_id="r", action="revise", **fields).action == "revise"


def test_conflicting_thumbs_rejected():
    with pytest.raises(ValidationError):
        DesignFeedback(attempt_id="a", revision_id="r", action="accept", thumbs="down")


@pytest.mark.parametrize("kind", ["modal", "fatigue", "random_vibration", "transient_structural", "other"])
def test_unsupported_analyses_cannot_claim_supported_execution(kind):
    with pytest.raises(ValidationError):
        AnalysisRecommendation(analysis_type=kind, name=kind, engineering_question="Question",
                               why_relevant="Context", required_inputs=[], execution_supported=True)
    with pytest.raises(ValidationError):
        AnalysisSpec.model_validate({**analysis_spec().model_dump(), "analysis_type": kind})


def test_draft_analysis_is_allowed_but_missing_inputs_block_execution():
    draft = AnalysisSpec(accepted_revision_id="r", geometry_hash=HASH,
                         analysis_type="linear_static_structural", engineering_question="Deflection?")
    issues = draft.execution_issues()
    assert {"Missing material", "Missing supports", "Missing loads", "Missing mesh settings"}.issubset(issues)
    assert analysis_spec().execution_issues() == []


def test_selector_contract_rejects_unknown_and_detects_overlap():
    spec = analysis_spec()
    with pytest.raises(ValidationError):
        AnalysisSpec.model_validate({**spec.model_dump(), "supports": [{"selector_id": "missing"}]})
    overlapping = AnalysisSpec.model_validate({**spec.model_dump(), "supports": [{"selector_id": "loaded"}]})
    assert "Support and load selectors overlap" in overlapping.execution_issues()
    with pytest.raises(ValidationError):
        RegionSelector(selector_id="s", kind="raw_face_id", position_tolerance_mm=1, normal_tolerance_degrees=1)
    with pytest.raises(ValidationError):
        Load(selector_id="s", force_n=(0, 0, 0))


def test_unavailable_solver_cannot_fabricate_values_or_success():
    payload = results().model_dump()
    with pytest.raises(ValidationError):
        AnalysisResults.model_validate({**payload, "provenance": "unavailable"})
    with pytest.raises(ValidationError):
        AnalysisResults.model_validate({**payload, "status": "blocked", "provenance": "unavailable"})
    with pytest.raises(ValidationError):
        AnalysisResults.model_validate({**payload, "maximum_displacement_mm": None})


@pytest.mark.parametrize("field,value", [
    ("geometry_hash", "b" * 64), ("version", 2),
    ("accepted_revision_id", "new-revision"), ("analysis_id", "new-analysis"),
])
def test_stale_results_rejected_at_contract_boundary(field, value):
    spec = analysis_spec()
    results().assert_matches(spec)
    with pytest.raises(ValueError, match="Stale"):
        results().assert_matches(spec.model_copy(update={field: value}))


def test_manifest_completion_cannot_be_empty_or_duplicate_paths():
    with pytest.raises(ValidationError):
        ArtifactManifest(project_id="p", job_id="j", stage="CAD", completed=True, artifacts=[])
    artifact = Artifact(relative_path="projects/p/model.step", sha256=HASH, size_bytes=1,
                        media_type="application/step", role="geometry")
    with pytest.raises(ValidationError):
        ArtifactManifest(project_id="p", job_id="j", stage="CAD", completed=True, artifacts=[artifact, artifact])


def test_source_provenance_must_identify_real_reference_kind():
    with pytest.raises(ValidationError):
        SourceReference(source_id="s", title="Unknown", chunk_id="c", reference="local.md")
    source = SourceReference(source_id="s", title="Seed", chunk_id="c", reference="local.md",
                             source_kind="authored_seed_note", equipment_context="Supplier dependent")
    assert source.source_kind == "authored_seed_note"

"""Validated, versioned contracts shared across UI, orchestration and workers.

These contracts describe integrations, not evidence that those integrations ran.
All dimensions and API-boundary quantities carry explicit units and provenance.
"""

from __future__ import annotations

from datetime import datetime, timezone
from enum import StrEnum
from typing import Annotated, Literal
from uuid import uuid4

from pydantic import BaseModel, ConfigDict, Field, model_validator


def new_id() -> str:
    return uuid4().hex


def utc_now() -> datetime:
    return datetime.now(timezone.utc)


Nonempty = Annotated[str, Field(min_length=1)]
Positive = Annotated[float, Field(gt=0)]
Nonnegative = Annotated[float, Field(ge=0)]
Digest = Annotated[str, Field(pattern=r"^[0-9a-f]{64}$")]


class Contract(BaseModel):
    model_config = ConfigDict(extra="forbid", frozen=True, allow_inf_nan=False)
    schema_version: Literal["1.0"] = "1.0"


class WorkflowState(StrEnum):
    INTAKE = "INTAKE"
    ROUTE_SELECTION = "ROUTE_SELECTION"
    ADVISOR_CHAT = "ADVISOR_CHAT"
    BRIEF_READY = "BRIEF_READY"
    SPEC_GENERATION = "SPEC_GENERATION"
    CAD_GENERATION = "CAD_GENERATION"
    CAD_EXECUTION = "CAD_EXECUTION"
    FREECAD_VALIDATION = "FREECAD_VALIDATION"
    RULE_CHECKS = "RULE_CHECKS"
    DESIGN_REVIEW = "DESIGN_REVIEW"
    RESTART_OFFER = "RESTART_OFFER"
    ANALYSIS_INTAKE = "ANALYSIS_INTAKE"
    ANALYSIS_SPEC_REVIEW = "ANALYSIS_SPEC_REVIEW"
    ANALYSIS_EXECUTION = "ANALYSIS_EXECUTION"
    REPORT_READY = "REPORT_READY"
    BLOCKED = "BLOCKED"
    ERROR = "ERROR"


class ValueOrigin(StrEnum):
    USER_PROVIDED = "user_provided"
    INFERRED = "inferred"
    ACCEPTED = "accepted"


class Dimension(Contract):
    name: Nonempty
    value: Positive
    unit: Literal["mm", "m", "in", "deg"]
    origin: ValueOrigin
    tolerance: Nonnegative | None = None
    accepted_from: Literal["user_provided", "inferred"] | None = None

    @model_validator(mode="after")
    def acceptance_provenance(self) -> Dimension:
        if (self.origin == ValueOrigin.ACCEPTED) != (self.accepted_from is not None):
            raise ValueError("Accepted values require accepted_from; other origins cannot set it")
        return self


class Requirement(Contract):
    requirement_id: Nonempty
    text: Nonempty
    verification_method: str | None = None
    confirmed: bool = False


class SourceReference(Contract):
    source_id: Nonempty
    title: Nonempty
    reference: Nonempty
    chunk_id: Nonempty
    source_kind: Literal["authored_seed_note", "manufacturer", "reference", "user_document"]
    section_or_page: str | None = None
    version_or_date: str | None = None
    topic: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    processes: list[str] = Field(default_factory=list)
    equipment_context: str | None = None
    supplier_context: str | None = None


class ImageReference(Contract):
    image_id: str = Field(default_factory=new_id)
    filename: Nonempty
    media_type: Literal["image/png", "image/jpeg", "image/webp"]
    role: Literal["desired_reference", "generated_model_screenshot"] = "desired_reference"
    sha256: Digest
    size_bytes: Annotated[int, Field(gt=0)]
    relative_path: Nonempty
    created_at: datetime = Field(default_factory=utc_now)


class VisualObservation(Contract):
    image_id: Nonempty
    text: Nonempty
    basis: Literal["observed_visual_feature", "inference", "user_confirmed"]


class Intake(Contract):
    idea: Nonempty
    purpose: str = ""
    hard_requirements: list[Requirement] = Field(default_factory=list)
    soft_requirements: list[Requirement] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)
    units: Literal["mm", "m", "in"] | None = None
    material_preferences: list[str] = Field(default_factory=list)
    manufacturing_preferences: list[str] = Field(default_factory=list)
    reference_image_ids: list[str] = Field(default_factory=list)


class Decision(Contract):
    decision_id: str = Field(default_factory=new_id)
    text: Nonempty
    status: Literal["proposed", "accepted"]
    sources: list[SourceReference] = Field(default_factory=list)


class DesignBrief(Contract):
    brief_id: str = Field(default_factory=new_id)
    version: Annotated[int, Field(ge=1)] = 1
    design_name: Nonempty
    description: str = ""
    purpose: str = ""
    hard_requirements: list[Requirement] = Field(default_factory=list)
    soft_requirements: list[Requirement] = Field(default_factory=list)
    dimensions: list[Dimension] = Field(default_factory=list)
    interfaces: list[str] = Field(default_factory=list)
    mechanisms_and_joints: list[str] = Field(default_factory=list)
    materials: list[str] = Field(default_factory=list)
    manufacturing: list[str] = Field(default_factory=list)
    assembly: list[str] = Field(default_factory=list)
    loads: list[str] = Field(default_factory=list)
    operating_environment: list[str] = Field(default_factory=list)
    accepted_decisions: list[Decision] = Field(default_factory=list)
    proposed_choices: list[Decision] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    reference_image_ids: list[str] = Field(default_factory=list)
    supporting_sources: list[SourceReference] = Field(default_factory=list)
    visual_observations: list[VisualObservation] = Field(default_factory=list)

    @model_validator(mode="after")
    def distinct_requirements_and_decisions(self) -> DesignBrief:
        ids = [r.requirement_id for r in self.hard_requirements + self.soft_requirements]
        if len(ids) != len(set(ids)):
            raise ValueError("Requirement IDs must be unique across hard and soft requirements")
        if any(d.status != "accepted" for d in self.accepted_decisions):
            raise ValueError("Accepted decisions must be explicitly accepted")
        if any(d.status != "proposed" for d in self.proposed_choices):
            raise ValueError("Proposed choices must remain proposed")
        return self


class Feature(Contract):
    feature_id: Nonempty
    kind: Literal["extrusion", "hole", "cut", "union", "fillet"]
    description: Nonempty
    parameter_names: list[str] = Field(default_factory=list)


class DesignSpec(Contract):
    spec_id: str = Field(default_factory=new_id)
    version: Annotated[int, Field(ge=1)] = 1
    brief_id: Nonempty
    brief_version: Annotated[int, Field(ge=1)]
    design_name: Nonempty
    purpose: Nonempty
    units: Literal["mm", "m", "in"]
    coordinate_system: Literal["right_handed_XYZ"] = "right_handed_XYZ"
    dimensions: list[Dimension]
    features: list[Feature]
    hard_requirements: list[Requirement] = Field(default_factory=list)
    soft_requirements: list[Requirement] = Field(default_factory=list)
    material_intent: str | None = None
    manufacturing_intent: list[str] = Field(default_factory=list)
    reference_image_ids: list[str] = Field(default_factory=list)
    accepted_decisions: list[Decision] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    unresolved_questions: list[str] = Field(default_factory=list)
    bounding_dimensions: dict[Literal["x", "y", "z"], str] = Field(default_factory=dict)

    @model_validator(mode="after")
    def unique_ids_and_parameters(self) -> DesignSpec:
        ids = [r.requirement_id for r in self.hard_requirements + self.soft_requirements]
        names = [d.name for d in self.dimensions]
        feature_ids = [f.feature_id for f in self.features]
        if len(ids) != len(set(ids)) or len(names) != len(set(names)) or len(feature_ids) != len(set(feature_ids)):
            raise ValueError("Requirement IDs, feature IDs and dimension names must be unique")
        if any(name not in names for feature in self.features for name in feature.parameter_names):
            raise ValueError("Features may only reference declared dimensions")
        if any(name not in names for name in self.bounding_dimensions.values()):
            raise ValueError("Bounding dimensions must reference declared dimensions")
        if any(d.unit == "deg" for d in self.dimensions if d.name in self.bounding_dimensions.values()):
            raise ValueError("Bounding dimensions must be lengths, not angles")
        return self


class CADGeneration(Contract):
    generation_id: str = Field(default_factory=new_id)
    attempt_id: Nonempty
    revision_id: Nonempty
    spec_id: Nonempty
    spec_version: Annotated[int, Field(ge=1)]
    code: Nonempty
    parameters: dict[str, float]
    technical_repair_count: Annotated[int, Field(ge=0, le=1)] = 0
    explanation: Nonempty
    provider_model: str | None = None
    previous_generation_id: str | None = None


class BoundingBox(Contract):
    minimum: tuple[float, float, float]
    maximum: tuple[float, float, float]
    unit: Literal["mm"] = "mm"

    @model_validator(mode="after")
    def ordered_extents(self) -> BoundingBox:
        if any(a > b for a, b in zip(self.minimum, self.maximum)):
            raise ValueError("Bounding box maximum must not be below minimum")
        return self


class GeometryMetrics(Contract):
    revision_id: Nonempty
    geometry_hash: Digest
    step_import_succeeded: bool
    shape_nonempty: bool
    shape_valid: bool
    solid_count: Annotated[int, Field(ge=0)]
    volume_mm3: Nonnegative
    bounding_box: BoundingBox | None = None
    surface_area_mm2: Nonnegative | None = None
    evidence_path: Nonempty


class RuleStatus(StrEnum):
    PASS = "PASS"
    FAIL = "FAIL"
    NOT_IMPLEMENTED = "NOT_IMPLEMENTED"
    NOT_APPLICABLE = "NOT_APPLICABLE"


class RuleResult(Contract):
    rule_id: Nonempty
    requirement_id: str | None = None
    status: RuleStatus
    mandatory: bool = False
    measured_value: float | str | bool | None = None
    expected_value: float | str | bool | None = None
    tolerance: Nonnegative | None = None
    unit: str | None = None
    message: Nonempty
    evidence_path: str | None = None


class DesignFeedback(Contract):
    feedback_id: str = Field(default_factory=new_id)
    attempt_id: Nonempty
    revision_id: Nonempty
    action: Literal["accept", "revise"]
    thumbs: Literal["up", "down"] | None = None
    text: str = ""
    reference_image_ids: list[str] = Field(default_factory=list)
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def consistent_action(self) -> DesignFeedback:
        if self.thumbs == "up" and self.action != "accept":
            raise ValueError("Thumbs up means accept")
        if self.thumbs == "down" and self.action != "revise":
            raise ValueError("Thumbs down means revise")
        # The explicit revise action is sufficient, including thumbs-only or images-only.
        return self


class DesignReview(Contract):
    attempt_id: Nonempty
    revision_id: Nonempty
    brief_version: Annotated[int, Field(ge=1)]
    spec_id: Nonempty
    spec_version: Annotated[int, Field(ge=1)]
    cad_manifest_id: Nonempty
    freecad_manifest_id: Nonempty
    geometry_hash: Digest
    checks: list[RuleResult]
    source: Literal["generated_container", "trusted_reference"] = "generated_container"


class DesignAcceptance(Contract):
    acceptance_id: str = Field(default_factory=new_id)
    attempt_id: Nonempty
    revision_id: Nonempty
    geometry_hash: Digest
    step_relative_path: Nonempty
    cad_manifest_id: Nonempty
    created_at: datetime = Field(default_factory=utc_now)


class RestartDecision(Contract):
    decision_id: str = Field(default_factory=new_id)
    previous_attempt_id: Nonempty
    new_attempt_id: Nonempty
    choice: Literal["approved_brief", "brainstorm", "original_idea"]
    brief_version: Annotated[int, Field(ge=1)]


class AnalysisType(StrEnum):
    LINEAR_STATIC = "linear_static_structural"
    MODAL = "modal"
    RANDOM_VIBRATION = "random_vibration"
    FATIGUE = "fatigue"
    TRANSIENT = "transient_structural"
    OTHER = "other"


class AnalysisRecommendation(Contract):
    analysis_type: AnalysisType
    name: Nonempty
    engineering_question: Nonempty
    why_relevant: Nonempty
    required_inputs: list[str]
    execution_supported: bool

    @model_validator(mode="after")
    def supported_type(self) -> AnalysisRecommendation:
        if self.execution_supported and self.analysis_type != AnalysisType.LINEAR_STATIC:
            raise ValueError("Only linear static structural execution is initially supported")
        return self


class Material(Contract):
    material_id: Nonempty
    name: Nonempty
    property_source: Nonempty
    youngs_modulus_mpa: Positive
    poissons_ratio: Annotated[float, Field(gt=-1, lt=0.5)]
    density_kg_m3: Positive


class RegionSelector(Contract):
    selector_id: Nonempty
    kind: Literal["planar_min_x", "planar_max_x"]
    position_tolerance_mm: Positive
    normal_tolerance_degrees: Annotated[float, Field(gt=0, lt=90)]


class Support(Contract):
    selector_id: Nonempty
    kind: Literal["fixed"] = "fixed"


class Load(Contract):
    selector_id: Nonempty
    force_n: tuple[float, float, float]

    @model_validator(mode="after")
    def nonzero_force(self) -> Load:
        if not any(self.force_n):
            raise ValueError("A force must have a nonzero component")
        return self


class MeshSettings(Contract):
    element_size_mm: Positive
    order: Literal["linear", "quadratic"] = "quadratic"


class AcceptanceLimit(Contract):
    quantity: Literal["maximum_displacement_mm", "maximum_von_mises_mpa"]
    maximum: Positive


class AnalysisSpec(Contract):
    analysis_id: str = Field(default_factory=new_id)
    version: Annotated[int, Field(ge=1)] = 1
    accepted_revision_id: Nonempty
    geometry_hash: Digest
    analysis_type: AnalysisType
    engineering_question: Nonempty
    material: Material | None = None
    unit_system: Literal["N_mm_MPa"] = "N_mm_MPa"
    selectors: list[RegionSelector] = Field(default_factory=list)
    supports: list[Support] = Field(default_factory=list)
    loads: list[Load] = Field(default_factory=list)
    mesh: MeshSettings | None = None
    requested_outputs: list[Literal["displacement", "von_mises", "reaction_forces"]] = Field(default_factory=list)
    acceptance_limits: list[AcceptanceLimit] = Field(default_factory=list)
    assumptions: list[str] = Field(default_factory=list)
    missing_inputs: list[str] = Field(default_factory=list)
    execution_supported: bool = False
    expected_bounds_mm: BoundingBox | None = None

    @model_validator(mode="after")
    def coherent_selectors(self) -> AnalysisSpec:
        ids = [s.selector_id for s in self.selectors]
        if len(ids) != len(set(ids)):
            raise ValueError("Selector IDs must be unique")
        if any(s.selector_id not in ids for s in self.supports + self.loads):
            raise ValueError("Supports and loads must reference declared selectors")
        if self.execution_supported and self.analysis_type != AnalysisType.LINEAR_STATIC:
            raise ValueError("Unsupported analysis cannot be marked executable")
        return self

    def execution_issues(self) -> list[str]:
        issues = list(self.missing_inputs)
        for value, label in [(self.material, "material"), (self.supports, "supports"),
                             (self.loads, "loads"), (self.mesh, "mesh settings"),
                             (self.requested_outputs, "requested outputs")]:
            if not value:
                issues.append(f"Missing {label}")
        if not self.execution_supported:
            issues.append("Execution is not supported for this setup")
        support_ids = {s.selector_id for s in self.supports}
        if support_ids.intersection(load.selector_id for load in self.loads):
            issues.append("Support and load selectors overlap")
        return issues


class MeshInformation(Contract):
    nodes: Annotated[int, Field(gt=0)]
    elements: Annotated[int, Field(gt=0)]


class ResolvedRegion(Contract):
    selector_id: Nonempty
    face_name: Nonempty
    center_mm: tuple[float, float, float]
    normal: tuple[float, float, float]
    area_mm2: Positive


class FEMPreparation(Contract):
    analysis_id: Nonempty
    analysis_spec_version: Annotated[int, Field(ge=1)]
    accepted_revision_id: Nonempty
    geometry_hash: Digest
    spec_hash: Digest
    regions_hash: Digest
    setup_hash: Digest
    confirmation_hash: Digest
    regions: list[ResolvedRegion]
    directory: Nonempty


class AnalysisResults(Contract):
    run_id: str = Field(default_factory=new_id)
    analysis_id: Nonempty
    analysis_spec_version: Annotated[int, Field(ge=1)]
    accepted_revision_id: Nonempty
    geometry_hash: Digest
    status: Literal["succeeded", "failed", "incomplete", "blocked"]
    provenance: Literal["actual_solver", "test_fixture", "unavailable"]
    solver_version: str | None = None
    maximum_displacement_mm: Nonnegative | None = None
    maximum_von_mises_mpa: Nonnegative | None = None
    reaction_force_n: tuple[float, float, float] | None = None
    mesh: MeshInformation | None = None
    image_paths: list[str] = Field(default_factory=list)
    log_paths: list[str] = Field(default_factory=list)
    error: str | None = None
    limitations: list[str] = Field(default_factory=lambda: ["Preliminary single-mesh results; mesh convergence not established."])

    @model_validator(mode="after")
    def success_requires_results(self) -> AnalysisResults:
        if self.status == "succeeded":
            if self.provenance == "unavailable" or not self.solver_version or self.error:
                raise ValueError("A successful solve requires identified solver evidence")
            if any(value is None for value in [self.maximum_displacement_mm,
                    self.maximum_von_mises_mpa, self.reaction_force_n, self.mesh]):
                raise ValueError("A successful solve requires all initial numerical outputs")
        if self.provenance == "unavailable" and any(value is not None for value in [
                self.maximum_displacement_mm, self.maximum_von_mises_mpa,
                self.reaction_force_n, self.mesh]):
            raise ValueError("Unavailable solvers cannot supply numerical results")
        if self.status in ("failed", "incomplete", "blocked") and not self.error:
            raise ValueError("Failed, incomplete and blocked solves require an explicit reason")
        return self

    def assert_matches(self, spec: AnalysisSpec) -> None:
        if (self.analysis_id, self.analysis_spec_version, self.accepted_revision_id,
                self.geometry_hash) != (spec.analysis_id, spec.version,
                spec.accepted_revision_id, spec.geometry_hash):
            raise ValueError("Stale analysis results do not match the accepted geometry/specification")


class Artifact(Contract):
    relative_path: Nonempty
    sha256: Digest
    size_bytes: Annotated[int, Field(ge=0)]
    media_type: Nonempty
    role: Nonempty


class ArtifactManifest(Contract):
    manifest_id: str = Field(default_factory=new_id)
    project_id: Nonempty
    attempt_id: str | None = None
    revision_id: str | None = None
    analysis_id: str | None = None
    job_id: Nonempty
    stage: Nonempty
    completed: bool
    artifacts: list[Artifact]
    created_at: datetime = Field(default_factory=utc_now)

    @model_validator(mode="after")
    def unique_artifacts(self) -> ArtifactManifest:
        paths = [a.relative_path for a in self.artifacts]
        if len(paths) != len(set(paths)):
            raise ValueError("Manifest paths must be unique")
        if self.completed and not self.artifacts:
            raise ValueError("Completion requires actual artifacts")
        return self


class ChatMessage(Contract):
    message_id: str = Field(default_factory=new_id)
    role: Literal["user", "assistant"]
    text: str = ""
    image_ids: list[str] = Field(default_factory=list)
    sources: list[SourceReference] = Field(default_factory=list)
    brief_version: Annotated[int, Field(ge=1)] | None = None
    created_at: datetime = Field(default_factory=utc_now)


class JobStatus(StrEnum):
    PENDING = "pending"
    RUNNING = "running"
    SUCCEEDED = "succeeded"
    FAILED = "failed"
    BLOCKED = "blocked"
    INTERRUPTED = "interrupted"


class Job(Contract):
    job_id: Nonempty
    project_id: Nonempty
    idempotency_key: Nonempty
    kind: Nonempty
    payload: dict
    status: JobStatus
    owner_id: str | None = None
    error: str | None = None
    result: dict | None = None
    created_at: datetime
    updated_at: datetime

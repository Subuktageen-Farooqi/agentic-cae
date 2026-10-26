"""M6 regression tests. Provider/container doubles are not live integration evidence."""
import json
from pathlib import Path

import pytest

from agents.cad_creator import cad_parameters, create_cad
from agents.spec_writer import SpecificationError, validate_against_brief, write_spec
from config import Config
from generation import enqueue_generation, run_generation_job, start_generation, retry_generation
from providers.vertex import ImagePayload
from reporting import render_design_spec
from schemas import DesignSpec, Dimension, Feature, JobStatus, Requirement, WorkflowState as S
from workers.code_validation import CodeRejected, validate_code
from workers.runtime import CADBuildError, SandboxUnavailable, container_command, execute_generated
from workflow import Workflow


CODE = "def build(params):\n    return cq.Workplane('XY').box(params['length'], params['width'], params['height'])\n"


def concept(brief):
    return DesignSpec(brief_id=brief.brief_id, brief_version=brief.version, design_name=brief.design_name,
        purpose="Support a small device", units="mm", dimensions=[
            Dimension(name=name, value=value, unit="mm", origin="inferred")
            for name, value in [("length", 100), ("width", 20), ("height", 10)]],
        features=[Feature(feature_id="beam", kind="extrusion", description="Rectangular beam", parameter_names=["length", "width", "height"])],
        hard_requirements=brief.hard_requirements, soft_requirements=brief.soft_requirements,
        accepted_decisions=brief.accepted_decisions, reference_image_ids=brief.reference_image_ids,
        assumptions=["Initial concept dimensions are inferred"], bounding_dimensions={"x": "length", "y": "width", "z": "height"})


class ProviderDouble:
    def __init__(self, spec): self.spec, self.calls = spec, []
    def generate(self, **kwargs):
        self.calls.append(kwargs)
        if "frozen_brief" in json.loads(kwargs["prompt"]):
            return self.spec.model_dump_json()
        return json.dumps({"code": CODE, "explanation": "Test provider double; no live Gemini call"})


def frozen(store, project):
    flow = Workflow(store)
    for target, route in [(S.ROUTE_SELECTION, None), (S.BRIEF_READY, "automatic"), (S.SPEC_GENERATION, None)]:
        flow.transition(project, target, expected_version=store.project(project)["row_version"], reason="test", route=route)


def test_spec_role_uses_images_and_markdown_preserves_validated_values(brief):
    spec = concept(brief)
    image = ImagePayload(data=b"fixture", media_type="image/png", role="desired_reference", image_id="fixture")
    provider = ProviderDouble(spec)
    actual = write_spec(brief=brief, provider=provider, images=[image])
    assert actual == spec and provider.calls[0]["images"] == [image]
    markdown = render_design_spec(actual)
    assert f"`{brief.brief_id}` v{brief.version}" in markdown
    assert "| length | 100 | mm | inferred |" in markdown
    assert "Initial concept dimensions are inferred" in markdown
    assert render_design_spec(DesignSpec.model_validate_json(spec.model_dump_json())) == markdown


def test_spec_cannot_drop_requirements_or_change_user_dimensions(brief):
    brief = brief.model_copy(update={"hard_requirements": [Requirement(requirement_id="H1", text="Keep interface")],
        "dimensions": [Dimension(name="length", value=120, unit="mm", origin="user_provided")]})
    spec = concept(brief)
    with pytest.raises(SpecificationError, match="known dimension"):
        validate_against_brief(spec, brief)
    with pytest.raises(SpecificationError, match="hard_requirements"):
        validate_against_brief(spec.model_copy(update={"hard_requirements": []}), brief)
    with pytest.raises(SpecificationError, match="frozen"):
        validate_against_brief(spec.model_copy(update={"brief_version": 99}), brief)


def test_cad_parameters_convert_units_and_creator_includes_actual_repair_evidence(brief):
    spec = concept(brief).model_copy(update={"dimensions": [Dimension(name="length", value=1, unit="in", origin="user_provided")]})
    assert cad_parameters(spec) == {"length": 25.4}
    provider = ProviderDouble(spec)
    first = create_cad(spec=spec, attempt_id="a", revision_id="r", provider=provider)
    repaired = create_cad(spec=spec, attempt_id="a", revision_id="r", provider=provider,
                          previous=first, technical_error="Actual fixture failure")
    assert repaired.technical_repair_count == 1 and repaired.previous_generation_id == first.generation_id
    assert json.loads(provider.calls[-1]["prompt"])["technical_error"] == "Actual fixture failure"
    with pytest.raises(ValueError, match="One technical repair"):
        create_cad(spec=spec, attempt_id="a", revision_id="r", provider=provider,
                   previous=repaired, technical_error="second failure")


@pytest.mark.parametrize("source", [
    "import os\ndef build(params): return None",
    "def build(params):\n return __import__('os').system('whoami')",
    "def build(params):\n return cq.__class__",
    "def build(params):\n return open('/secret').read()",
    "def build(params):\n return cq.exporters.export(params, '/tmp/file')",
    "@print\ndef build(params): return None",
    "def build(params=print('oops')): return None",
    "def build(params):\n cq = 42\n return cq",
    "def build(params):\n def nested(): pass\n return nested()",
    "def build(params):\n return getattr(cq, params['name'])()",
])
def test_restricted_source_rejects_infrastructure_and_escape_syntax(source):
    with pytest.raises(CodeRejected): validate_code(source)


def test_approved_source_is_validated_but_missing_runtime_never_executes_it(brief, tmp_path, monkeypatch):
    validate_code(CODE)
    spec = concept(brief)
    generation = create_cad(spec=spec, attempt_id="a", revision_id="r", provider=ProviderDouble(spec))
    monkeypatch.setattr("workers.runtime.shutil.which", lambda value: None)
    with pytest.raises(SandboxUnavailable, match="not executed"):
        execute_generated(generation=generation, project_id="p", job_id="j", output_dir=tmp_path / "job",
                          project_root=tmp_path, config=Config.from_env({}))
    assert not (tmp_path / "job").exists()
    command = container_command(Config.from_env({}), tmp_path, "test")
    assert {"--network=none", "--read-only", "--user=65532:65532", "--memory=2g", "--cpus=2", "--cap-drop=ALL"} <= set(command)
    assert not any("docker.sock" in argument for argument in command)


def test_generation_runs_at_most_one_repair_and_never_counts_user_rejection(store, project, brief, monkeypatch):
    frozen(store, project)
    provider = ProviderDouble(concept(brief))
    calls = []
    def failure(**kwargs):
        calls.append(kwargs)
        raise CADBuildError("Actual test-double build failure")
    monkeypatch.setattr("generation.execute_generated", failure)
    job = enqueue_generation(store, project)
    assert enqueue_generation(store, project).job_id == job.job_id
    result = run_generation_job(store=store, job_id=job.job_id, provider=provider, config=Config.from_env({}))
    assert result.status == JobStatus.FAILED and len(calls) == 2
    assert store.attempt(result.result["attempt_id"])["user_rejections"] == 0
    assert len(store.records(project, "CADGeneration")) == 2
    with pytest.raises(Exception, match="budget exhausted"):
        store.consume_technical_repair(result.result["revision_id"])
    run_generation_job(store=store, job_id=job.job_id, provider=provider, config=Config.from_env({}))
    assert len(calls) == 2


def test_dependency_block_consumes_no_repair_and_explicit_retry_preserves_attempt(store, project, brief, monkeypatch):
    frozen(store, project)
    provider = ProviderDouble(concept(brief))
    def blocked(**kwargs): raise SandboxUnavailable("No container engine")
    monkeypatch.setattr("generation.execute_generated", blocked)
    first = run_generation_job(store=store, job_id=enqueue_generation(store, project).job_id,
                               provider=provider, config=Config.from_env({}))
    assert first.status == JobStatus.BLOCKED
    assert not any(e["kind"] == "technical_repair_consumed" for e in store.events(project))
    old_path = store.path(first.result["artifact_directory"] + "/design_spec.json")
    original = old_path.read_bytes()
    class Immediate:
        def submit(self, function, **kwargs): return function(**kwargs)
    second = retry_generation(store=store, project_id=project, provider=provider,
                               config=Config.from_env({}), executor=Immediate())
    second = store.job(second.job_id)
    assert second.result["attempt_id"] != first.result["attempt_id"] and old_path.read_bytes() == original


def test_live_mode_failure_never_requests_a_technical_repair(store,project,brief,monkeypatch):
    frozen(store,project)
    provider=ProviderDouble(concept(brief))
    def failure(**kwargs): raise CADBuildError("Mocked worker failure")
    monkeypatch.setattr("generation.execute_generated",failure)
    result=run_generation_job(store=store,job_id=enqueue_generation(store,project).job_id,
        provider=provider,config=Config.from_env({}),allow_technical_repair=False)
    assert result.status==JobStatus.FAILED and len(provider.calls)==2
    assert len(store.records(project,"CADGeneration"))==1
    assert not any(e["kind"]=="technical_repair_consumed" for e in store.events(project))


def test_existing_pending_generation_is_not_restarted_when_ui_reopens(store, project, brief):
    frozen(store, project)
    pending = enqueue_generation(store, project)
    class Never:
        def submit(self, *args, **kwargs): raise AssertionError("Reopening must not execute existing jobs")
    assert start_generation(store=store, project_id=project, provider=ProviderDouble(concept(brief)),
                            config=Config.from_env({}), executor=Never()).job_id == pending.job_id


def test_complete_pipeline_with_explicit_container_double_validates_real_geometry(store, project, brief, monkeypatch):
    """Only the container boundary is doubled; this is NOT sandbox execution evidence."""
    from workers.cad_worker import run_trusted_build
    config = Config.from_env()
    if not config.freecad_cmd:
        pytest.skip("Real FreeCADCmd is required for this pipeline integration test")
    frozen(store, project)
    provider = ProviderDouble(concept(brief))
    def trusted_fixture(**kwargs):
        generation = kwargs["generation"]
        return run_trusted_build(project_id=kwargs["project_id"], job_id=kwargs["job_id"],
            model_source=Path("examples/cantilever_model.py"),
            params={"length_mm": generation.parameters["length"], "width_mm": generation.parameters["width"],
                    "height_mm": generation.parameters["height"]},
            output_dir=kwargs["output_dir"], project_root=kwargs["project_root"])
    monkeypatch.setattr("generation.execute_generated", trusted_fixture)
    result = run_generation_job(store=store, job_id=enqueue_generation(store, project).job_id,
                                provider=provider, config=config)
    assert result.status == JobStatus.SUCCEEDED, result.error
    assert store.project(project)["state"] == S.DESIGN_REVIEW
    assert all(r.status.value == "PASS" for r in store.records(project, "RuleResult") if r.mandatory)
    assert store.records(project, "GeometryMetrics")[-1].solid_count == 1

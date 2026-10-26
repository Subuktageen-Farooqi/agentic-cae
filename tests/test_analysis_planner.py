"""Mocked M8 dialogue tests; synthetic review artifacts are not solver evidence."""
import json
import pytest

from agents.analysis_planner import plan_analysis
from fem_workflow import enqueue_prepare
from providers.vertex import ProviderUnavailable
from review import accept_design
from schemas import AnalysisInputs, AnalysisPlan, AnalysisType, WorkflowState
from storage import ConflictError, Store
from test_review import checked_fixture


@pytest.fixture
def accepted(store, project, brief):
    review = checked_fixture(store, project, brief)
    accept_design(store, project, expected_version=store.project(project)["row_version"],
                  revision_id=review.revision_id, geometry_hash=review.geometry_hash)
    return review


class PlannerDouble:
    def __init__(self, change=None): self.calls=[]; self.change=change
    def generate(self, **kwargs):
        self.calls.append(kwargs)
        c = json.loads(kwargs["prompt"])["context"]
        result = dict(accepted_revision_id=c["accepted_revision_id"], geometry_hash=c["geometry_hash"],
            inputs=c["inputs"], user_message=c["user_message"], text="Preliminary single-mesh analysis recommendation.",
            recommendations=[dict(analysis_type="linear_static_structural", name="Linear static",
                engineering_question="How much does it deflect?", why_relevant="Known cantilever loading",
                required_inputs=["material", "force", "supports", "mesh"], execution_supported=True),
                dict(analysis_type="fatigue",name="Fatigue",engineering_question="What is the cyclic life?",
                    why_relevant="Only if cyclic loading is established",required_inputs=["load history", "fatigue curves"],execution_supported=False)],
            missing_inputs=c["missing_inputs"], questions=["Please supply the missing material and force."] if c["missing_inputs"] else [],
            specification=c["executable_candidate"])
        if self.change: self.change(result)
        return json.dumps(result)


def complete_inputs():
    return AnalysisInputs(engineering_question="What displacement and stress result from 100 N?",
        analysis_type="linear_static_structural",material_id="freecad-generic-steel",force_n=(0,0,-100),
        support_kind="planar_min_x",load_kind="planar_max_x",mesh_mm=3)


def call(store, project, inputs, provider):
    return plan_analysis(store=store,project_id=project,inputs=inputs,message="Advise on this setup",
                         provider=provider,expected_version=store.project(project)["row_version"])


def test_missing_inputs_conversation_persists_and_never_starts_execution(store, project, accepted):
    provider=PlannerDouble()
    first=call(store,project,AnalysisInputs(engineering_question="Which analysis is relevant?"),provider)
    assert first.specification is None and "force_n" in first.missing_inputs and first.questions
    assert store.jobs(project)==[] and store.project(project)["state"]==WorkflowState.ANALYSIS_INTAKE
    second=call(store,project,complete_inputs(),provider)
    assert second.specification is not None and second.specification.execution_issues()==[]
    context=json.loads(provider.calls[-1]["prompt"])["context"]
    assert len(context["prior_conversation"])==1
    assert context["metrics"]["geometry_hash"]==accepted.geometry_hash
    assert context["verified_material"]["property_source"].startswith("https://github.com/FreeCAD/")
    reopened=Store(store.root)
    assert reopened.records(project,"AnalysisPlan")==[first,second]
    assert len(provider.calls)==2 and reopened.jobs(project)==[]
    job=enqueue_prepare(store,project,second.specification,expected_version=store.project(project)["row_version"])
    assert job.kind=="FEM_PREPARE" and all(j.kind!="FEM_SOLVE" for j in store.jobs(project))


@pytest.mark.parametrize("kind", ["modal","random_vibration","fatigue","transient_structural","other"])
def test_unsupported_requests_cannot_create_executable_spec(store,project,accepted,kind):
    plan=call(store,project,complete_inputs().model_copy(update={"analysis_type":AnalysisType(kind)}),PlannerDouble())
    assert plan.specification is None and not store.jobs(project)


@pytest.mark.parametrize("field,value",[("force_n",None),("force_n",(0,0,0)),("material_id",None),
                                      ("support_kind",None),("load_kind",None),("mesh_mm",None)])
def test_missing_or_zero_inputs_never_generate_executable_candidate(store,project,accepted,field,value):
    plan=call(store,project,complete_inputs().model_copy(update={field:value}),PlannerDouble())
    assert plan.missing_inputs and plan.specification is None


@pytest.mark.parametrize("change", [
    lambda r:r.update(geometry_hash="f"*64),
    lambda r:r["specification"]["loads"][0].update(force_n=[0,0,-999]),
    lambda r:r["specification"]["material"].update(youngs_modulus_mpa=123),
    lambda r:r.update(missing_inputs=["invented"]),
])
def test_ai_cannot_change_authoritative_fields(store,project,accepted,change):
    with pytest.raises(ValueError,match="authoritative"):
        call(store,project,complete_inputs(),PlannerDouble(change))
    assert store.records(project,"AnalysisPlan")==[] and not store.jobs(project)


def test_contradictory_material_blocked_before_provider_call(store,project,brief):
    steel_conflict=brief.model_copy(update={"version":brief.version+1,"materials":["Aluminum"]})
    updated=store.save_brief(project,steel_conflict,expected_version=brief.version,actor="test",reason="Material conflict")
    review=checked_fixture(store,project,updated)
    accept_design(store,project,expected_version=store.project(project)["row_version"],revision_id=review.revision_id,geometry_hash=review.geometry_hash)
    provider=PlannerDouble()
    with pytest.raises(ValueError,match="conflicts"):
        call(store,project,complete_inputs(),provider)
    assert provider.calls==[]


def test_stale_response_does_not_replace_newer_plan(store,project,accepted):
    def concurrent(_):
        with store._connection(write=True) as db:
            db.execute("UPDATE projects SET row_version=row_version+1 WHERE project_id=?",(project,))
    with pytest.raises(ConflictError,match="changed"):
        call(store,project,complete_inputs(),PlannerDouble(concurrent))
    assert store.records(project,"AnalysisPlan")==[]

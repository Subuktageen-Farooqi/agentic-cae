"""Synthetic values and provider doubles, never real solver/live evidence."""
import json
import pytest
from agents.report_explainer import explain_report
from fem_workflow import propose_static, numerical_checks
from review import accept_design, review_artifacts
from schemas import AnalysisResults, MeshInformation
from reporting import render_report
from storage import Store
from test_review import checked_fixture


@pytest.fixture
def setup(store,project,brief):
    review=checked_fixture(store,project,brief)
    accept_design(store,project,expected_version=store.project(project)["row_version"],
                  revision_id=review.revision_id,geometry_hash=review.geometry_hash)
    spec=propose_static(store,project,question="Unit test",force_n=(0,0,-100),mesh_mm=3)
    result=AnalysisResults(analysis_id=spec.analysis_id,analysis_spec_version=1,
        accepted_revision_id=spec.accepted_revision_id,geometry_hash=spec.geometry_hash,
        status="succeeded",provenance="actual_solver",solver_version="SYNTHETIC UNIT FIXTURE",
        maximum_displacement_mm=.09964792921575177,maximum_von_mises_mpa=29.885778687934497,
        reaction_force_n=(0,0,100),mesh=MeshInformation(nodes=10,elements=4))
    return review,spec,result


class Double:
    calls=0
    def generate(self,**kwargs):
        self.calls+=1
        c=json.loads(kwargs["prompt"])
        spec=c["analysis_specification"]; result=c["actual_solver_results"]
        return json.dumps(dict(analysis_id=spec["analysis_id"],run_id=result["run_id"],
            accepted_revision_id=spec["accepted_revision_id"],geometry_hash=spec["geometry_hash"],
            text="Preliminary single-mesh displacement and stress; no durability conclusion."))


def test_explanation_is_persisted_sidecar_without_rewriting_report(store,project,setup):
    _,spec,result=setup
    report=render_report(spec,result)
    assert str(result.maximum_displacement_mm) in report and str(result.maximum_von_mises_mpa) in report
    provider=Double()
    first=explain_report(store=store,project_id=project,spec=spec,result=result,provider=provider)
    reopened=Store(store.root)
    again=explain_report(store=reopened,project_id=project,spec=spec,result=result,provider=provider)
    assert first==again and provider.calls==1
    assert render_report(spec,result)==report


def test_generated_rectangular_beam_check_requires_real_full_box_volume(store,project,setup):
    review,spec,result=setup
    artifacts=review_artifacts(store,project,review)
    design=artifacts["spec"].model_copy(update={"bounding_dimensions":{"x":"length","y":"width","z":"height"}})
    good=numerical_checks(spec,result,review,design,artifacts["metrics"])
    assert good["beam_applicable"] and good["displacement_relative_difference"] < .12
    cut=artifacts["metrics"].model_copy(update={"volume_mm3":19000})
    assert not numerical_checks(spec,result,review,design,cut)["beam_applicable"]
    assert not numerical_checks(spec,result,review,design)["beam_applicable"]

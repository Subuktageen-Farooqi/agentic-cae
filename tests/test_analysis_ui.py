"""M8 app interaction with a mocked advisor and synthetic review fixture."""
from pathlib import Path
from streamlit.testing.v1 import AppTest
from review import accept_design
from test_review import checked_fixture
from test_analysis_planner import PlannerDouble


def test_missing_input_dialogue_complete_proposal_and_reopen_without_llm(store,project,brief,monkeypatch):
    review=checked_fixture(store,project,brief)
    accept_design(store,project,expected_version=store.project(project)["row_version"],
                  revision_id=review.revision_id,geometry_hash=review.geometry_hash)
    class Provider(PlannerDouble):
        def availability_issues(self): return []
    provider=Provider()
    monkeypatch.setattr("providers.factory.make_provider",lambda config:provider)
    monkeypatch.setenv("CAE_DATA_DIR",str(store.root))
    def reopen():
        app=AppTest.from_file(Path(__file__).parents[1]/"app.py")
        app.session_state["project_id"]=project
        app.run(timeout=20)
        assert not app.exception
        return app
    app=reopen()
    next(t for t in app.text_area if t.label.startswith("Ask about analyses")).input("Which analysis and inputs do I need?")
    next(b for b in app.button if b.label=="Ask analysis advisor").click().run(timeout=20)
    assert not app.exception and len(provider.calls)==1
    assert any("Still needed:" in w.value for w in app.warning)
    assert not store.jobs(project)
    next(t for t in app.text_input if t.label=="Analysis question to answer").input("How much does the beam deflect?")
    next(s for s in app.selectbox if s.label=="Analysis type").select("linear_static_structural")
    for label in ("Select sourced generic reference steel for this analysis",
        "Fix the minimum-X face and apply the resultant to the maximum-X face",
        "I have specified the force components below","Use the specified quadratic mesh size below"):
        next(c for c in app.checkbox if c.label==label).check()
    next(n for n in app.number_input if n.label=="Specified force Z (N)").set_value(-100.)
    next(b for b in app.button if b.label=="Ask analysis advisor").click().run(timeout=20)
    assert not app.exception and len(provider.calls)==2
    assert any(b.label=="Prepare advisor's proposed regions" for b in app.button)
    assert not any(b.label=="Confirm setup and run FreeCAD FEM" for b in app.button)
    assert len(store.records(project,"AnalysisPlan"))==2 and not store.jobs(project)
    reopen()
    assert len(provider.calls)==2 and not store.jobs(project)

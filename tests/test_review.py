"""Review/persistence unit tests with explicitly synthetic artifact fixtures.

These fixtures are NOT real CAD/solver evidence. See test_app_fem_e2e.py for
the actual app → generated reference CAD → FreeCAD FEM / CalculiX run.
"""
import hashlib
import json
import sqlite3

import pytest

from review import accept_design, reject_design, restart_attempt, current_review
from rules.geometry import core_geometry_rules
from schemas import (Artifact, ArtifactManifest, BoundingBox, DesignBrief, DesignFeedback,
                     DesignReview, DesignSpec, Dimension, Feature, GeometryMetrics, RuleResult, RuleStatus, WorkflowState as S)
from storage import ConflictError, IntegrityError, Store


def checked_fixture(store, project, brief, *, attempt_id=None, fail_check=False):
    attempt = store.attempt(attempt_id) if attempt_id else store.create_attempt(project, brief.version)
    revision = store.create_revision(attempt["attempt_id"])
    prefix = revision["relative_path"]
    contents = {"step": ("model.step", b"UNIT TEST: not a real STEP file"),
        "preview": ("preview.stl", b"UNIT TEST: not a real STL file"),
        "model_source": ("model.py", b"def build(params):\n return cq.Workplane('XY').box(100,20,10)\n"),
        "parameters": ("parameters.json", b'{"length":100,"width":20,"height":10}'),
        "fcstd": ("model.FCStd", b"UNIT TEST: not a real FreeCAD document"),
        "freecad_metrics": ("metrics.json", b'{"unit_fixture":true}')}
    artifacts = {}
    for role,(name,data) in contents.items():
        store.write_once(prefix + "/" + name, data)
        artifacts[role] = Artifact(relative_path=prefix + "/" + name, sha256=hashlib.sha256(data).hexdigest(),
                                   size_bytes=len(data), role=role, media_type="application/octet-stream")
    cad = ArtifactManifest(manifest_id="cad-" + revision["revision_id"], project_id=project, job_id="unit",
        stage="CAD_EXECUTION", completed=True, artifacts=[artifacts[k] for k in ("step","preview","model_source","parameters")])
    imported = ArtifactManifest(manifest_id="fc-" + revision["revision_id"], project_id=project, job_id="unit",
        stage="FREECAD_VALIDATION", completed=True, artifacts=[artifacts[k] for k in ("fcstd","freecad_metrics")])
    for manifest in (cad,imported): store.save_record(project,manifest.manifest_id,1,manifest)
    metrics = GeometryMetrics(revision_id=revision["revision_id"], geometry_hash=artifacts["step"].sha256,
        step_import_succeeded=True,shape_nonempty=True,shape_valid=True,solid_count=1,volume_mm3=20000,
        bounding_box=BoundingBox(minimum=(0,-10,-5),maximum=(100,10,5)),evidence_path=prefix+"/metrics.json")
    store.save_record(project,revision["revision_id"],1,metrics)
    spec = DesignSpec(brief_id=brief.brief_id,brief_version=brief.version,design_name=brief.design_name,
        purpose=brief.purpose or "Unit fixture",units="mm",dimensions=brief.dimensions or [
            Dimension(name=n,value=v,unit="mm",origin="inferred") for n,v in [("length",100),("width",20),("height",10)]],
        features=[Feature(feature_id="unit",kind="extrusion",description="Synthetic unit fixture")],
        hard_requirements=brief.hard_requirements,soft_requirements=brief.soft_requirements,
        accepted_decisions=brief.accepted_decisions,reference_image_ids=brief.reference_image_ids,
        assumptions=["Synthetic unit fixture; not CAD integration evidence"])
    store.save_record(project,spec.spec_id,1,spec)
    checks=core_geometry_rules(metrics)
    if fail_check: checks.append(RuleResult(rule_id="unit.mandatory",status=RuleStatus.FAIL,mandatory=True,message="Unit fixture failed"))
    review=DesignReview(attempt_id=attempt["attempt_id"],revision_id=revision["revision_id"],brief_version=brief.version,
        spec_id=spec.spec_id,spec_version=1,cad_manifest_id=cad.manifest_id,freecad_manifest_id=imported.manifest_id,
        geometry_hash=metrics.geometry_hash,checks=checks)
    store.save_record(project,revision["revision_id"],1,review)
    with store._connection(write=True) as db:
        db.execute("UPDATE projects SET state=?,row_version=row_version+1 WHERE project_id=?",(S.DESIGN_REVIEW,project))
    return review


def feedback(review, **kwargs):
    return DesignFeedback(attempt_id=review.attempt_id, revision_id=review.revision_id, action="revise", **kwargs)


def failed_attempt(store,project,brief):
    first=checked_fixture(store,project,brief)
    old_step=store.path(store.revision(first.revision_id)["relative_path"]+"/model.step").read_bytes()
    job=reject_design(store,project,feedback(first,thumbs="down"),expected_version=store.project(project)["row_version"])
    store.claim(job.job_id,"unit"); store.finish(job.job_id,"unit", "succeeded",result={"unit_fixture":True})
    updated=brief.model_copy(update={"version":brief.version+1,"purpose":"Refined user purpose"})
    updated=store.save_brief(project,updated,expected_version=brief.version,actor="unit",reason="Simulated user intent change")
    second=checked_fixture(store,project,updated,attempt_id=first.attempt_id)
    assert reject_design(store,project,feedback(second,text="Keep it serviceable"),expected_version=store.project(project)["row_version"]) is None
    assert store.path(store.revision(first.revision_id)["relative_path"]+"/model.step").read_bytes()==old_step
    return first,second


def test_acceptance_binds_exact_artifact_and_survives_reopen(store,project,brief):
    review=checked_fixture(store,project,brief)
    before=store.original_intake(project)
    with pytest.raises(ConflictError,match="exact"):
        accept_design(store,project,expected_version=store.project(project)["row_version"],revision_id=review.revision_id,geometry_hash="a"*64)
    acceptance=accept_design(store,project,expected_version=store.project(project)["row_version"],revision_id=review.revision_id,geometry_hash=review.geometry_hash)
    restored=Store(store.root)
    assert restored.project(project)["state"]==S.ANALYSIS_INTAKE
    assert restored.project(project)["accepted_geometry_hash"]==review.geometry_hash
    assert restored.record(project,"DesignAcceptance",acceptance.acceptance_id,1)==acceptance
    assert restored.original_intake(project)==before
    assert restored.attempt(review.attempt_id)["user_rejections"]==0


def test_altered_artifact_or_failed_mandatory_check_cannot_be_accepted(store,project,brief):
    review=checked_fixture(store,project,brief)
    manifest=store.record(project,"ArtifactManifest",review.cad_manifest_id,1)
    store.path(manifest.artifacts[0].relative_path).write_bytes(b"tampered unit fixture")
    with pytest.raises(IntegrityError):
        accept_design(store,project,expected_version=store.project(project)["row_version"],revision_id=review.revision_id,geometry_hash=review.geometry_hash)
    assert store.project(project)["accepted_revision_id"] is None


def test_failed_mandatory_rules_block_acceptance(store,project,brief):
    review=checked_fixture(store,project,brief,fail_check=True)
    with pytest.raises(ValueError,match="mandatory"):
        accept_design(store,project,expected_version=store.project(project)["row_version"],revision_id=review.revision_id,geometry_hash=review.geometry_hash)


@pytest.mark.parametrize("text,thumbs,images",[("", "down",False),("Move the hole",None,False),("Match this",None,True),("",None,True)])
def test_all_feedback_modes_enqueue_once_without_consuming_technical_repair(store,project,brief,text,thumbs,images):
    review=checked_fixture(store,project,brief)
    image_ids=brief.reference_image_ids if images else []
    item=feedback(review,text=text,thumbs=thumbs,reference_image_ids=image_ids)
    version=store.project(project)["row_version"]
    job=reject_design(store,project,item,expected_version=version)
    assert job.payload["attempt_id"]==review.attempt_id and job.payload["feedback_id"]==item.feedback_id
    assert store.attempt(review.attempt_id)["user_rejections"]==1
    assert store.revision(review.revision_id)["technical_repairs"]==0
    with pytest.raises(ConflictError): reject_design(store,project,item,expected_version=version)
    assert len(store.jobs(project))==1


@pytest.mark.parametrize("choice,state",[("approved_brief",S.SPEC_GENERATION),("brainstorm",S.ADVISOR_CHAT),("original_idea",S.ROUTE_SELECTION)])
def test_two_rejections_and_all_restart_choices_preserve_correct_snapshots(store,project,brief,choice,state):
    original=store.original_intake(project)
    first,second=failed_attempt(store,project,brief)
    assert store.project(project)["state"]==S.RESTART_OFFER
    assert store.attempt(first.attempt_id)["user_rejections"]==2
    assert len(store.records(project,"DesignReview"))==2
    with pytest.raises(ConflictError): store.create_revision(first.attempt_id)
    decision=restart_attempt(store,project,choice,expected_version=store.project(project)["row_version"])
    assert decision.new_attempt_id!=first.attempt_id
    assert store.attempt(decision.new_attempt_id)["user_rejections"]==0
    assert store.project(project)["state"]==state and store.original_intake(project)==original
    current=store.brief(project)
    if choice=="original_idea":
        assert current.description==original.idea and current.reference_image_ids==original.reference_image_ids
    else:
        assert current.purpose=="Refined user purpose"
    if choice=="brainstorm":
        assert "Keep it serviceable" in store.records(project,"ChatMessage")[-1].text
    assert store.attempt(first.attempt_id)["status"]=="failed"


def test_v1_database_migrates_additively_without_losing_intake_or_images(tmp_path,png_bytes):
    from schemas import Intake
    from storage import Upload
    root=tmp_path/"migration"
    original=Store(root)
    project=original.create_project(Intake(idea="Preserve my design"),[Upload("ref.png","image/png",png_bytes)])
    intake=original.original_intake(project)
    image=original.images(project)[0]
    with sqlite3.connect(original.database) as db:
        for column in ("active_attempt_id","accepted_revision_id","accepted_geometry_hash"):
            db.execute("ALTER TABLE projects DROP COLUMN "+column)
        db.execute("PRAGMA user_version=1")
    migrated=Store(root)
    assert migrated.original_intake(project)==intake and migrated.read_image(project,image.image_id)==png_bytes
    with migrated._connection() as db: assert db.execute("PRAGMA user_version").fetchone()[0]==2


def test_user_dimension_revision_updates_brief_and_preserves_same_attempt(store,project,brief,monkeypatch):
    from generation import run_generation_job
    from config import Config
    from workers.runtime import SandboxUnavailable
    review=checked_fixture(store,project,brief)
    item=feedback(review,text="Change length to 120 mm")
    job=reject_design(store,project,item,expected_version=store.project(project)["row_version"])
    calls=[]
    class Provider:
        def generate(self,**kwargs):
            payload=json.loads(kwargs["prompt"]); calls.append(payload)
            if "frozen_brief" in payload:
                current=DesignBrief.model_validate(payload["frozen_brief"])
                return DesignSpec(brief_id=current.brief_id,brief_version=current.version,design_name=current.design_name,
                    purpose="Revised fixture",units="mm",dimensions=current.dimensions,
                    features=[Feature(feature_id="new",kind="extrusion",description="Unit revision")],
                    hard_requirements=current.hard_requirements,soft_requirements=current.soft_requirements,
                    reference_image_ids=current.reference_image_ids,accepted_decisions=current.accepted_decisions).model_dump_json()
            return json.dumps({"code":"def build(params):\n return cq.Workplane('XY').box(params['length'],20,10)","explanation":"Length changed from saved feedback"})
    def blocked(**kwargs): raise SandboxUnavailable("Unit test: no container run")
    monkeypatch.setattr("generation.execute_generated",blocked)
    result=run_generation_job(store=store,job_id=job.job_id,provider=Provider(),config=Config.from_env({}))
    assert result.status.value=="blocked"
    assert result.result["attempt_id"]==review.attempt_id
    assert next(d for d in store.brief(project).dimensions if d.name=="length").value==120
    assert calls[-1]["design_feedback"]["text"]==item.text and calls[-1]["previous_revision_code"]
    assert store.attempt(review.attempt_id)["user_rejections"]==1


@pytest.mark.parametrize("label,choice,heading",[
    ("Retry from approved brief","approved_brief","Specification generation"),
    ("Return to brainstorming with feedback","brainstorm","Engineering advisor"),
    ("Start from original idea","original_idea","Choose how to continue")])
def test_restart_ui_uses_preserved_snapshots_and_original_answers(store,project,brief,monkeypatch,label,choice,heading):
    """AppTest + synthetic review fixtures; no CAD or solver execution evidence."""
    import shutil
    from pathlib import Path
    from streamlit.testing.v1 import AppTest
    failed_attempt(store,project,brief)
    shutil.copytree(Path(__file__).parents[1]/"data"/"knowledge",store.root/"knowledge")
    monkeypatch.setenv("CAE_DATA_DIR",str(store.root))
    app=AppTest.from_file(Path(__file__).parents[1]/"app.py")
    app.session_state["project_id"]=project
    app.run(timeout=20)
    assert not app.exception
    next(b for b in app.button if b.label==label).click().run(timeout=20)
    assert not app.exception
    assert heading in [h.value for h in [*app.header,*app.subheader]]
    if choice=="original_idea":
        assert next(t for t in app.text_area if t.label=="Idea").value==store.original_intake(project).idea
        next(b for b in app.button if b.label=="Open engineering advisor").click().run(timeout=20)
        assert not app.exception and store.project(project)["state"]==S.ADVISOR_CHAT


@pytest.mark.parametrize("quote,identifier,valid",[("H1 change finish to brushed","H1",True),
                                                  ("invented user instruction","H1",False),
                                                  ("H1 change finish to brushed","H99",False)])
def test_requirement_changes_need_explicit_user_evidence_and_preserve_other_requirements(brief,quote,identifier,valid):
    from agents.revision_writer import revise_brief
    from schemas import Requirement
    updated=brief.model_copy(update={"hard_requirements":[Requirement(requirement_id="H1",text="Polished finish"),
        Requirement(requirement_id="H2",text="Keep the mounting interface")]})
    spec=DesignSpec(brief_id=updated.brief_id,brief_version=updated.version,design_name=updated.design_name,
        purpose="Unit fixture",units="mm",dimensions=[],features=[],hard_requirements=updated.hard_requirements)
    request=DesignFeedback(attempt_id="unit",revision_id="unit",action="revise",text="H1 change finish to brushed")
    class Provider:
        def generate(self,**kwargs): return json.dumps({"explanation":"Apply explicit requirement edit",
            "hard_requirement_updates":[{"requirement_id":identifier,"text":"Brushed finish","evidence_quote":quote}]})
    if not valid:
        with pytest.raises(ValueError,match="evidence"):
            revise_brief(brief=updated,previous_spec=spec,feedback=request,provider=Provider(),images=[])
    else:
        revised=revise_brief(brief=updated,previous_spec=spec,feedback=request,provider=Provider(),images=[])
        assert revised.hard_requirements[0].text=="Brushed finish"
        assert revised.hard_requirements[1]==updated.hard_requirements[1]


def test_restart_generation_key_stays_idempotent_after_worker_allocates_revision(store,project,brief):
    from generation import enqueue_generation
    first,second=failed_attempt(store,project,brief)
    decision=restart_attempt(store,project,"approved_brief",expected_version=store.project(project)["row_version"])
    original=enqueue_generation(store,project)
    assert original.payload["attempt_id"]==decision.new_attempt_id
    store.create_revision(decision.new_attempt_id)
    assert enqueue_generation(store,project).job_id==original.job_id
    assert len([j for j in store.jobs(project) if j.job_id==original.job_id])==1

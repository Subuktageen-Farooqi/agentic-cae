"""Smoke-driver negative gates with no live transport or generated-code execution."""
import subprocess
import sys
import pytest
from examples.container_check import assert_rectangular_metrics
from examples.live_smoke import preflight, sketch
from config import Config
from schemas import BoundingBox, GeometryMetrics


def test_live_driver_requires_explicit_opt_in():
    process=subprocess.run([sys.executable,"-m","examples.live_smoke","prepare"],capture_output=True,text=True)
    assert process.returncode==2 and "--live is required" in process.stderr


def test_missing_config_blocks_before_any_sdk_construction():
    with pytest.raises(RuntimeError,match="no live request sent"):
        preflight(Config.from_env({}),"does-not-exist.json")


def test_reference_is_actual_readable_sketch():
    from PIL import Image
    import io
    image=Image.open(io.BytesIO(sketch()))
    assert image.format=="PNG" and image.size==(640,240)
    assert len(image.getcolors()) > 1


def test_cantilever_comparison_rejects_wrong_volume_or_dimensions():
    metrics=GeometryMetrics(revision_id="unit",geometry_hash="a"*64,step_import_succeeded=True,
        shape_nonempty=True,shape_valid=True,solid_count=1,volume_mm3=20000,
        bounding_box=BoundingBox(minimum=(0,-10,-5),maximum=(100,10,5)),evidence_path="unit")
    assert_rectangular_metrics(metrics)
    with pytest.raises(ValueError): assert_rectangular_metrics(metrics.model_copy(update={"volume_mm3":19000}))


def test_recovery_keeps_original_ledger_and_project_when_preflight_blocks(monkeypatch,tmp_path):
    """Local state only; no model response, transport or generated-code execution."""
    import json
    from examples import live_smoke
    from providers.budget import LiveBudget
    from storage import Store
    from schemas import Intake, ChatMessage, WorkflowState as S
    from app_logic import draft_brief
    from workflow import Workflow
    control=tmp_path/"control"; control.mkdir()
    monkeypatch.setattr(live_smoke,"CONTROL",control)
    store=Store(tmp_path/"data")
    project_id=store.create_project(Intake(idea="Local recovery gate"))
    flow=Workflow(store)
    flow.transition(project_id,S.ROUTE_SELECTION,expected_version=store.project(project_id)["row_version"],reason="test")
    brief=store.save_brief(project_id,draft_brief(store.original_intake(project_id),automatic=False),
        expected_version=0,actor="test",reason="test")
    flow.transition(project_id,S.ADVISOR_CHAT,route="advisor",expected_version=store.project(project_id)["row_version"],reason="test")
    user=ChatMessage(role="user",text="Explain the material choice",brief_version=brief.version)
    store.save_record(project_id,user.message_id,1,user)
    live_smoke.write_once(control/"project.json",{"project_id":project_id,"data_dir":str(store.root)})
    original=LiveBudget.create(control/"requests.sqlite3")
    with original.connection() as db:
        db.execute("INSERT INTO requests VALUES (1,'advisor','returned','{}')")
    original.stop()
    before=original.snapshot()
    with pytest.raises(RuntimeError,match="Configure Developer API"):
        live_smoke.recover(Config.from_env({}),"missing-evidence.json")
    assert original.snapshot()==before and not (control/"recovery-requests.sqlite3").exists()
    assert Store(store.root).record(project_id,"ChatMessage",user.message_id,1)==user

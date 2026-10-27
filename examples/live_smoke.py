"""One explicitly opted-in live journey, at most five requests, no retries.

Prepare stops AFTER real face resolution. Solve requires the displayed exact
confirmation hash, supplied only after the user reviews and confirms the setup.
Never delete/reset its ledger to retry a failed test; obtain a new user budget.
"""
from __future__ import annotations
import argparse
from contextlib import contextmanager
import io
import json
import os
from pathlib import Path

from agents.advisor import advise, apply_reply_to_brief
from agents.analysis_planner import plan_analysis
from agents.report_explainer import explain_report
from app_logic import draft_brief
from config import Config
from examples.container_check import assert_rectangular_metrics, image_id
from fem_workflow import accepted_artifacts, enqueue_prepare, enqueue_solve, run_fem_job
from generation import brief_images, enqueue_generation, run_generation_job
from providers.budget import LiveBudget, ROLES
from providers.factory import make_provider
from rag.retriever import LocalHybridRetriever
from review import accept_design, current_review, review_artifacts
from schemas import AnalysisInputs, ArtifactManifest, ChatMessage, Dimension, Intake, JobStatus, WorkflowState as S
from storage import Store, Upload
from workflow import Workflow
from workers.fem_worker import availability, parse_reaction_totals
from workers.runtime import check_runtime


ROOT = Path(__file__).resolve().parents[1]
CONTROL = ROOT / ".tools" / "live-smoke"


def write_once(path, value):
    path.parent.mkdir(parents=True,exist_ok=True)
    with path.open("x",encoding="utf-8") as file:
        json.dump(value,file,indent=2)


@contextmanager
def app_environment(data_dir):
    previous=os.environ.get("CAE_DATA_DIR")
    os.environ["CAE_DATA_DIR"]=str(data_dir)
    try: yield
    finally:
        if previous is None: os.environ.pop("CAE_DATA_DIR",None)
        else: os.environ["CAE_DATA_DIR"]=previous


def display_project(store, project_id, title):
    from streamlit.testing.v1 import AppTest
    before=[j.model_dump(mode="json") for j in store.jobs(project_id)]
    with app_environment(store.root):
        app=AppTest.from_file(ROOT/"app.py")
        app.session_state["project_id"]=project_id
        app.run(timeout=40)
        if app.exception or title not in [h.value for h in app.header]:
            raise AssertionError("Saved project did not render the expected app stage")
    if [j.model_dump(mode="json") for j in store.jobs(project_id)] != before:
        raise AssertionError("Opening the saved project changed durable jobs")
    return app


def sketch():
    from PIL import Image, ImageDraw
    image=Image.new("RGB",(640,240),"white")
    draw=ImageDraw.Draw(image)
    draw.rectangle((100,95,550,145),outline="black",width=3)
    draw.line((100,65,100,175),fill="black",width=4)
    for y in range(65,175,12): draw.line((80,y+12,100,y),fill="black",width=2)
    draw.line((550,145,550,205),fill="red",width=3)
    draw.polygon([(550,210),(543,195),(557,195)],fill="red")
    draw.text((220,70),"X: length 100 mm",fill="black")
    draw.text((200,155),"Y width 20 mm; Z thickness 10 mm",fill="black")
    draw.text((105,30),"Rectangular steel cantilever - reference sketch",fill="black")
    draw.text((555,185),"-Z",fill="red")
    output=io.BytesIO(); image.save(output,format="PNG")
    return output.getvalue()


def checked_job(job):
    if job.status != JobStatus.SUCCEEDED:
        raise RuntimeError("A production pipeline stage failed; inspect its persisted job/artifacts offline")
    return job


def preflight(config, evidence_path):
    provider=make_provider(config)
    if config.llm_provider != "gemini_developer" or provider.availability_issues():
        raise RuntimeError("Configure Developer API key/model locally first; no live request sent")
    check_runtime(config)
    if not availability(config.freecad_cmd,config.calculix_exe,config.gmsh_exe)[0]:
        raise RuntimeError("Real FreeCAD FEM dependencies are missing; no live request sent")
    evidence=json.loads(Path(evidence_path).read_text(encoding="utf-8"))
    if evidence.get("completed") is not True or evidence.get("mocked_components") != [] or evidence.get("live_requests") != 0:
        raise ValueError("Supply successful real deterministic container-check evidence")
    if evidence["image_id"] != image_id(config):
        raise ValueError("Container image changed since deterministic verification")
    verification=Store(evidence["root"])
    for key in ("cad_manifest","freecad_manifest"):
        verification.verify_manifest(ArtifactManifest.model_validate(evidence[key]))
    return provider


def continue_journey(*, config, store, project_id, provider, ledger, prior_requests=0, ledger_name="requests.sqlite3"):
    """Resume the saved advisor-stage project without replaying its intake."""
    pid=project_id
    if store.project(pid)["state"] != S.ADVISOR_CHAT:
        raise RuntimeError("The saved project is not awaiting the advisor")
    brief=store.brief(pid)
    history=store.records(pid,"ChatMessage")
    if len(history)!=1 or history[0].role!="user" or history[0].brief_version!=brief.version:
        raise RuntimeError("Expected exactly one preserved advisor question before continuation")
    user=history[0]; message=user.text
    flow=Workflow(store)
    def transition(target):
        return flow.transition(pid,target,expected_version=store.project(pid)["row_version"],reason="Authorized single live smoke journey")
    reply=advise(provider=provider,retriever=LocalHybridRetriever(ROOT/"data/knowledge/index.json"),
        brief=brief,history=[user],message=message,images=brief_images(store,pid,brief))
    if not reply.sources or not reply.visual_observations:
        raise AssertionError("Live advisor must cite retrieved evidence and interpret the actual sketch")
    if any(o.image_id not in brief.reference_image_ids for o in reply.visual_observations):
        raise AssertionError("Advisor referenced an unknown image")
    updated=apply_reply_to_brief(brief,reply)
    if updated.dimensions != brief.dimensions or updated.materials != brief.materials:
        raise AssertionError("Advisor changed fixed live-test inputs")
    if not updated.loads:
        raise AssertionError("Advisor did not update the brief's loading")
    brief=store.save_brief(pid,updated,expected_version=brief.version,actor="advisor",reason="Live image and retrieved-source advisor response")
    assistant=ChatMessage(role="assistant",text=reply.text,sources=reply.sources,brief_version=brief.version)
    store.save_record(pid,assistant.message_id,1,assistant)
    transition(S.BRIEF_READY); transition(S.SPEC_GENERATION)
    job=enqueue_generation(store,pid)
    checked_job(run_generation_job(store=store,job_id=job.job_id,provider=provider,config=config,allow_technical_repair=False))
    review=current_review(store,pid); artifacts=review_artifacts(store,pid,review)
    assert_rectangular_metrics(artifacts["metrics"])
    app=display_project(store,pid,"Review your design")
    if len(app.get("plotly_chart")) < 1: raise AssertionError("Actual generated STL was not displayed")
    accept_design(store,pid,expected_version=store.project(pid)["row_version"],revision_id=review.revision_id,geometry_hash=review.geometry_hash)
    inputs=AnalysisInputs(engineering_question="What are displacement, stress and reaction balance under the 100 N negative-Z tip force?",
        analysis_type="linear_static_structural",material_id="freecad-generic-steel",force_n=(0,0,-100),
        support_kind="planar_min_x",load_kind="planar_max_x",mesh_mm=3)
    plan=plan_analysis(store=store,project_id=pid,inputs=inputs,message="Prepare the specified preliminary steel cantilever linear-static analysis.",
                       provider=provider,expected_version=store.project(pid)["row_version"])
    if plan.specification is None: raise AssertionError("Complete user inputs did not yield an analysis specification")
    spec=plan.specification
    job=enqueue_prepare(store,pid,spec,expected_version=store.project(pid)["row_version"])
    checked_job(run_fem_job(store=store,job_id=job.job_id,config=config))
    preparation=store.record(pid,"FEMPreparation",spec.analysis_id,spec.version)
    app=display_project(store,pid,"Review the actual analysis setup")
    if len(app.get("plotly_chart")) < 1: raise AssertionError("Actual selected regions were not displayed")
    state={"project_id":pid,"analysis_id":spec.analysis_id,"spec_version":spec.version,"data_dir":str(store.root),
        "confirmation_hash":preparation.confirmation_hash,"regions":[r.model_dump(mode="json") for r in preparation.regions],
        "specification":spec.model_dump(mode="json"),"directory":preparation.directory,"budget":ledger.snapshot(),
        "ledger":ledger_name,"prior_live_requests":prior_requests,"cumulative_live_requests":prior_requests+ledger.snapshot()["count"]}
    if state["budget"]["count"] != 4: raise AssertionError("Unexpected live request allocation")
    write_once(CONTROL/"prepared.json",state)
    return state


def prepare(config, evidence_path):
    if (CONTROL/"prepared.json").exists() or (CONTROL/"requests.sqlite3").exists():
        raise RuntimeError("This smoke run already exists; preserve it and inspect status, never restart automatically")
    provider=preflight(config,evidence_path)
    ledger=LiveBudget.create(CONTROL/"requests.sqlite3")
    provider=ledger.wrap(provider)
    store=Store(config.data_dir)
    try:
        intake=Intake(idea="Rectangular steel cantilever, 100 mm X by 20 mm Y by 10 mm Z, without holes or fillets.",
            purpose="Measure tip displacement and stress under a static end force.",units="mm",
            dimensions=[Dimension(name=n,value=v,unit="mm",origin="user_provided") for n,v in (
                ("length",100),("width",20),("height",10))],material_preferences=["Generic reference steel"])
        pid=store.create_project(intake,[Upload("cantilever-sketch.png","image/png",sketch())])
        write_once(CONTROL/"project.json",{"project_id":pid,"data_dir":str(store.root),"allocation":ROLES})
        flow=Workflow(store)
        def transition(target,**kwargs):
            return flow.transition(pid,target,expected_version=store.project(pid)["row_version"],reason="Authorized single live smoke journey",**kwargs)
        transition(S.ROUTE_SELECTION)
        brief=store.save_brief(pid,draft_brief(store.original_intake(pid),automatic=False),expected_version=0,
                               actor="user",reason="Explicit live cantilever inputs")
        transition(S.ADVISOR_CHAT,route="advisor")
        message=("Use the actual reference sketch and retrieved knowledge to explain the steel cantilever load path, "
            "support and material limitations, citing supplied chunk IDs. Record the visible sketch features separately "
            "from inference and update the brief's loads to a 100 N negative-Z end force. Preserve the explicit dimensions "
            "and rectangular geometry. No additional conversation is requested; this is a preliminary static reference demonstration.")
        user=ChatMessage(role="user",text=message,image_ids=brief.reference_image_ids,brief_version=brief.version)
        store.save_record(pid,user.message_id,1,user)
        return continue_journey(config=config,store=store,project_id=pid,provider=provider,ledger=ledger)
    except BaseException:
        ledger.stop()
        raise


def recover(config, evidence_path):
    """Explicit one-time continuation of the preserved first-attempt project.

    This function is callable only after the user grants a new four-request
    allowance. The original stopped ledger is never cleared or rewritten.
    """
    original=LiveBudget(CONTROL/"requests.sqlite3").snapshot()
    if (original["count"] != 1 or not original["stopped"]
            or original["requests"][0]["role"] != "advisor"
            or original["requests"][0]["status"] != "returned"):
        raise RuntimeError("The preserved first attempt is not eligible for this one-time continuation")
    if (CONTROL/"recovery-requests.sqlite3").exists() or (CONTROL/"prepared.json").exists():
        raise RuntimeError("Recovery already exists; never reset or replay its allowance")
    checkpoint=json.loads((CONTROL/"project.json").read_text(encoding="utf-8"))
    store=Store(checkpoint["data_dir"])
    pid=checkpoint["project_id"]
    if store.project(pid)["state"] != S.ADVISOR_CHAT or store.records(pid,"DesignSpec"):
        raise RuntimeError("Saved advisor-stage project has changed; inspect before continuing")
    for image in store.images(pid):
        store.read_image(pid,image.image_id)
    provider=preflight(config,evidence_path)
    ledger=LiveBudget.create(CONTROL/"recovery-requests.sqlite3",max_requests=4)
    try:
        return continue_journey(config=config,store=store,project_id=pid,provider=ledger.wrap(provider),
            ledger=ledger,prior_requests=original["count"],ledger_name="recovery-requests.sqlite3")
    except BaseException:
        ledger.stop()
        raise


def solve(config, confirmation):
    state=json.loads((CONTROL/"prepared.json").read_text(encoding="utf-8"))
    ledger=LiveBudget(CONTROL/state.get("ledger","requests.sqlite3"))
    prior_requests=state.get("prior_live_requests",0)
    if confirmation != state["confirmation_hash"]:
        raise ValueError("Explicit confirmation of the displayed actual setup is required")
    if (CONTROL/"solved.json").exists() or ledger.snapshot()["stopped"]:
        raise RuntimeError("Run already finished or stopped; do not replay")
    if prior_requests+ledger.snapshot()["count"] > 5:
        raise RuntimeError("Combined live request budget was exceeded; do not solve")
    store=Store(state["data_dir"]); pid=state["project_id"]
    try:
        spec=store.record(pid,"AnalysisSpec",state["analysis_id"],state["spec_version"])
        prepared=store.record(pid,"FEMPreparation",spec.analysis_id,spec.version)
        job=enqueue_solve(store,pid,spec,prepared,expected_version=store.project(pid)["row_version"],confirmation_hash=confirmation)
        job=checked_job(run_fem_job(store=store,job_id=job.job_id,config=config))
        result=store.record(pid,"AnalysisResults",job.result["run_id"],1)
        directory=store.path(job.result["artifact_directory"])
        store.verify_manifest(store.record(pid,"ArtifactManifest",job.result["manifest_id"],1))
        raw=json.loads((directory/"solver_results.json").read_text(encoding="utf-8"))
        report=(directory/"integration_report.md").read_text(encoding="utf-8")
        for field in ("maximum_displacement_mm","maximum_von_mises_mpa"):
            if getattr(result,field) != raw[field] or str(raw[field]) not in report:
                raise AssertionError("Numerical report differs from actual solver extraction")
        if result.reaction_force_n != parse_reaction_totals((directory/"solver/Mesh.dat").read_text(encoding="utf-8")):
            raise AssertionError("Reaction values differ from solver DAT totals")
        checks=json.loads((directory/"verification.json").read_text(encoding="utf-8"))
        if not checks["beam_applicable"] or checks["displacement_relative_difference"] >= .12 or checks["reaction_relative_residual"] >= 1e-4:
            raise AssertionError("Beam theory or reaction balance is outside existing integration tolerances")
        explanation_exercised=False
        if prior_requests+ledger.snapshot()["count"] == 4:
            explain_report(store=store,project_id=pid,spec=spec,result=result,provider=ledger.wrap(make_provider(config)))
            explanation_exercised=True
        count=ledger.snapshot()["count"]
        app=display_project(store,pid,"FreeCAD FEM results")
        if len(app.get("plotly_chart")) < 2: raise AssertionError("Actual result charts were not displayed")
        metrics={m.label:m.value for m in app.metric}
        if metrics["Maximum displacement (mm)"] != f"{result.maximum_displacement_mm:.8f}" or metrics["Maximum von Mises stress (MPa)"] != f"{result.maximum_von_mises_mpa:.6f}":
            raise AssertionError("App metrics differ from actual solver fields")
        display_project(Store(store.root),pid,"FreeCAD FEM results")
        if ledger.snapshot()["count"] != count: raise AssertionError("Reopening consumed a live request")
        evidence={"project_id":pid,"analysis_id":spec.analysis_id,"checks":checks,"app_metrics":metrics,
            "result":result.model_dump(mode="json"),"budget":ledger.snapshot(),"explanation_exercised":explanation_exercised,
            "prior_live_requests":prior_requests,"cumulative_live_requests":prior_requests+ledger.snapshot()["count"],
            "directory":str(directory),"mocked_components":[],"reopened_without_execution":True}
        write_once(CONTROL/"solved.json",evidence)
        ledger.stop()
        return evidence
    except BaseException:
        ledger.stop()
        raise


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=["prepare","recover","solve","status"])
    parser.add_argument("--live",action="store_true",help="Explicit opt-in to the single five-request live budget")
    parser.add_argument("--container-evidence")
    parser.add_argument("--confirm")
    args=parser.parse_args()
    if args.phase == "status":
        initial=LiveBudget(CONTROL/"requests.sqlite3").snapshot() if (CONTROL/"requests.sqlite3").exists() else {"count":0,"maximum":5,"started":False}
        recovery=LiveBudget(CONTROL/"recovery-requests.sqlite3").snapshot() if (CONTROL/"recovery-requests.sqlite3").exists() else None
        continuation=LiveBudget(CONTROL/"second-recovery-requests.sqlite3").snapshot() if (CONTROL/"second-recovery-requests.sqlite3").exists() else None
        bracket=LiveBudget(CONTROL/"bracket-requests.sqlite3").snapshot() if (CONTROL/"bracket-requests.sqlite3").exists() else None
        value={"initial":initial,"recovery":recovery,"continuation":continuation,"bracket":bracket,
               "cumulative_count":sum(item["count"] for item in (initial,recovery,continuation,bracket) if item),
               "cumulative_maximum":5}
    else:
        if not args.live: parser.error("--live is required; no requests sent")
        if args.phase in ("prepare","recover") and not args.container_evidence: parser.error("--container-evidence is required")
        if args.phase == "solve" and not args.confirm: parser.error("--confirm is required after actual-region user review")
        config=Config.from_env()
        value=(prepare(config,args.container_evidence) if args.phase == "prepare"
               else recover(config,args.container_evidence) if args.phase == "recover"
               else solve(config,args.confirm))
    print(json.dumps(value,indent=2))


if __name__ == "__main__": main()

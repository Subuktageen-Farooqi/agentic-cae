"""One real AppTest-controlled intake-to-report journey with no AI doubles.

The first failed advisor request remains in its own stopped ledger/project.
This frontend journey uses a separate four-request allowance. It pauses after
the real FEM faces are displayed; solve requires the user's exact confirmation.
"""
from __future__ import annotations

import argparse
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

from examples import live_smoke
from examples.live_smoke import ROOT, CONTROL, preflight, sketch, write_once
from config import Config
from providers.budget import LiveBudget
from schemas import JobStatus, WorkflowState as S
from storage import Store
from workers.fem_worker import parse_reaction_totals


EVIDENCE = ROOT / ".tools/container-verification/projects/36c4925539524d06bb361ffdc74fb528/evidence.json"


def healthy(app, label):
    if app.exception:
        raise RuntimeError(label + " raised a frontend exception; inspect the saved project offline")


def click(app, label, actions, *, timeout=40):
    next(button for button in app.button if button.label == label).click().run(timeout=timeout)
    healthy(app, label)
    actions.append(label)


def wait_job(app, store, pid, kind, config):
    deadline=time.monotonic()+config.worker_timeout_seconds+60
    while time.monotonic()<deadline:
        jobs=[job for job in store.jobs(pid) if job.kind==kind]
        if jobs and jobs[-1].status not in (JobStatus.PENDING,JobStatus.RUNNING):
            if jobs[-1].status != JobStatus.SUCCEEDED:
                raise RuntimeError(kind+" failed; inspect the persisted job and artifacts offline")
            app.run(timeout=40); healthy(app,kind)
            return jobs[-1]
        time.sleep(.5)
        app.run(timeout=40); healthy(app,kind)
    raise TimeoutError(kind+" did not finish within the configured worker timeout")


def initial_allowance():
    old=LiveBudget(CONTROL/"requests.sqlite3").snapshot()
    if old["count"] != 1 or not old["stopped"] or old["requests"][0]["role"]!="advisor":
        raise RuntimeError("The preserved first-request ledger has an unexpected state")
    if (CONTROL/"recovery-requests.sqlite3").exists() or (CONTROL/"ui-prepared.json").exists():
        raise RuntimeError("A live continuation already exists; never replay or reset it")
    return old


def prepare(config):
    from streamlit.testing.v1 import AppTest
    from providers import factory
    import generation

    old=initial_allowance()
    preflight(config,EVIDENCE)
    store=Store(config.data_dir)
    actions=[]
    with patch.dict(os.environ,{"CAE_DATA_DIR":str(store.root)}):
        app=AppTest.from_file(ROOT/"app.py").run(timeout=30)
        healthy(app,"initial intake")
        if "Tell us what you want to design" not in [h.value for h in app.header]:
            raise AssertionError("Actual intake form did not render")
        app.text_area[0].input("A single rectangular steel cantilever, length 100 mm X, width 20 mm Y, thickness 10 mm Z; no holes or fillets.")
        next(t for t in app.text_area if t.label.startswith("Purpose and intended use")).input(
            "Measure tip displacement, stress and support reactions under a static end force.")
        next(t for t in app.text_area if t.label.startswith("Known hard requirements")).input(
            "One connected, full rectangular-prism solid with the specified X/Y/Z extents and no holes or fillets")
        next(s for s in app.selectbox if s.label.startswith("Known dimension units")).select("mm")
        next(t for t in app.text_area if t.label.startswith("Known dimensions")).input(
            "length = 100 mm\nwidth = 20 mm\nheight = 10 mm")
        next(t for t in app.text_input if t.label.startswith("Material preference")).input("Generic reference steel")
        next(u for u in app.file_uploader if u.label.startswith("Reference images")).upload(
            "cantilever-sketch.png",sketch(),"image/png")
        app.button(key="FormSubmitter:intake-Save idea and continue").click().run(timeout=30)
        healthy(app,"intake submission")
        actions.append("Save idea and continue")
        if "Choose how to continue" not in [h.value for h in app.header]:
            raise AssertionError("Route selection did not render")
        routes=[s.value for s in app.subheader]
        if not any("Brainstorm with our AI" in route for route in routes) or not any("trust your judgment" in route for route in routes):
            raise AssertionError("Both real application routes were not presented")
        pid=app.session_state["project_id"]
        write_once(CONTROL/"ui-project.json",{"project_id":pid,"data_dir":str(store.root),
            "first_attempt_project_id":json.loads((CONTROL/"project.json").read_text(encoding="utf-8"))["project_id"]})
        click(app,"Open engineering advisor",actions)
        if store.project(pid)["state"]!=S.ADVISOR_CHAT or len(store.images(pid))!=1:
            raise AssertionError("Brainstorm route or actual uploaded sketch did not persist")
        before=store.brief(pid)
        print(json.dumps({"stage":"frontend_intake_and_routes","project_id":pid,
            "uploaded_image_count":len(store.images(pid)),"live_requests":old["count"]}),flush=True)

        # The wrapper sends every UI role to the real Developer API, while the
        # separate SQLite ledger enforces exactly four more generation calls.
        ledger=LiveBudget.create(CONTROL/"recovery-requests.sqlite3",max_requests=4)
        real_factory=factory.make_provider
        real_generation=generation.run_generation_job
        def guarded_provider(selected_config):
            return ledger.wrap(real_factory(selected_config))
        def no_repair(**kwargs):
            return real_generation(**kwargs,allow_technical_repair=False)
        try:
            with patch.object(factory,"make_provider",guarded_provider), patch.object(generation,"run_generation_job",no_repair):
                question=("Use the actual reference sketch and retrieved knowledge to explain the steel cantilever load path, "
                    "support and material limitations, citing supplied chunk IDs. Record visible sketch features separately "
                    "from inference and update the brief's loads to a 100 N negative-Z end force. Preserve the explicit "
                    "dimensions and rectangular geometry. No additional conversation is requested.")
                app.chat_input[0].set_value(question).run(timeout=config.worker_timeout_seconds+30)
                healthy(app,"live engineering advisor")
                replies=[m for m in store.records(pid,"ChatMessage") if m.role=="assistant"]
                refined=store.brief(pid)
                if (len(replies)!=1 or replies[0].text.startswith("Gemini is BLOCKED") or not replies[0].sources
                        or not refined.visual_observations or not refined.loads
                        or refined.dimensions!=before.dimensions or refined.materials!=before.materials
                        or any(o.image_id not in refined.reference_image_ids for o in refined.visual_observations)):
                    raise AssertionError("Live advisor response was not cited, visual, or faithful to fixed inputs")
                actions.append("Advisor answered with actual image and retrieved sources")
                print(json.dumps({"stage":"live_advisor","cited_sources":len(replies[0].sources),
                    "visual_observations":len(refined.visual_observations),"budget":ledger.snapshot()}),flush=True)

                click(app,"Generate this design",actions)
                wait_job(app,store,pid,"DESIGN_GENERATION",config)
                if store.project(pid)["state"]!=S.DESIGN_REVIEW or len(app.get("plotly_chart"))<1:
                    raise AssertionError("Generated CAD was not displayed for exact-artifact review")
                from review import current_review, review_artifacts
                from examples.container_check import assert_rectangular_metrics
                review=current_review(store,pid)
                assert_rectangular_metrics(review_artifacts(store,pid,review)["metrics"])
                actions.append("Displayed real generated STL and geometry checks")
                print(json.dumps({"stage":"real_generated_cad","revision_id":review.revision_id,
                    "geometry_hash":review.geometry_hash,"budget":ledger.snapshot()}),flush=True)

                click(app,"Accept design",actions)
                if store.project(pid)["state"]!=S.ANALYSIS_INTAKE:
                    raise AssertionError("Exact checked CAD was not accepted into analysis intake")
                next(t for t in app.text_area if t.label.startswith("Ask about analyses")).input(
                    "Recommend an analysis for this beam, then prepare my stated static steel setup.")
                next(t for t in app.text_input if t.label=="Analysis question to answer").input(
                    "What are displacement, stress and reaction balance under a 100 N negative-Z end force?")
                next(s for s in app.selectbox if s.label=="Analysis type").select("linear_static_structural")
                for label in ("Select sourced generic reference steel for this analysis",
                              "Fix the minimum-X face and apply the resultant to the maximum-X face",
                              "I have specified the force components below",
                              "Use the specified quadratic mesh size below"):
                    next(c for c in app.checkbox if c.label==label).check()
                next(n for n in app.number_input if n.label=="Specified force Z (N)").set_value(-100.)
                click(app,"Ask analysis advisor",actions,timeout=config.worker_timeout_seconds+30)
                plans=store.records(pid,"AnalysisPlan")
                if len(plans)!=1 or plans[0].specification is None:
                    raise AssertionError("Live analysis recommendations/specification did not validate")
                if ledger.snapshot()["count"]!=4 or old["count"]+ledger.snapshot()["count"]!=5:
                    raise AssertionError("Live generation allocation differed from the cumulative five-request plan")
                print(json.dumps({"stage":"analysis_specification","recommendations":len(plans[0].recommendations),
                    "cumulative_live_requests":5,"budget":ledger.snapshot()}),flush=True)

                click(app,"Prepare advisor's proposed regions",actions)
                wait_job(app,store,pid,"FEM_PREPARE",config)
                if "Review the actual analysis setup" not in [h.value for h in app.header] or len(app.get("plotly_chart"))<1:
                    raise AssertionError("Actual imported support/load regions were not displayed")
                spec=plans[0].specification
                preparation=store.record(pid,"FEMPreparation",spec.analysis_id,spec.version)
                state={"project_id":pid,"analysis_id":spec.analysis_id,"spec_version":spec.version,
                    "data_dir":str(store.root),"confirmation_hash":preparation.confirmation_hash,
                    "regions":[r.model_dump(mode="json") for r in preparation.regions],
                    "specification":spec.model_dump(mode="json"),"directory":preparation.directory,
                    "app_actions":actions,"budget":ledger.snapshot(),"cumulative_live_requests":5,
                    "ledger":"recovery-requests.sqlite3"}
                write_once(CONTROL/"ui-prepared.json",state)
                return state
        except BaseException:
            ledger.stop()
            raise


def continue_saved_frontend(config):
    """One user-authorized three-call continuation after the saved API failure.

    The two prior stopped ledgers remain untouched. The manual validated
    analysis form uses no model request, keeping the cumulative cap at five.
    """
    from streamlit.testing.v1 import AppTest
    from providers import factory
    import generation

    first=LiveBudget(CONTROL/"requests.sqlite3").snapshot()
    second=LiveBudget(CONTROL/"recovery-requests.sqlite3").snapshot()
    if (first["count"],second["count"])!=(1,1) or not first["stopped"] or not second["stopped"]:
        raise RuntimeError("The preserved two-call history is not eligible for this continuation")
    if second["requests"][0]["status"]!="failed" or (CONTROL/"second-recovery-requests.sqlite3").exists() or (CONTROL/"ui-prepared.json").exists():
        raise RuntimeError("A continuation already exists or the failed request history changed")
    saved=json.loads((CONTROL/"ui-project.json").read_text(encoding="utf-8"))
    store=Store(saved["data_dir"]);pid=saved["project_id"]
    if store.project(pid)["state"]!=S.ADVISOR_CHAT or len(store.images(pid))!=1 or store.records(pid,"DesignSpec"):
        raise RuntimeError("The saved frontend project is not at the advisor stage")
    store.read_image(pid,store.images(pid)[0].image_id)
    preflight(config,EVIDENCE)
    actions=["Save idea and continue","Presented both routes","Open engineering advisor"]
    ledger=LiveBudget.create(CONTROL/"second-recovery-requests.sqlite3",max_requests=3)
    real_factory=factory.make_provider
    real_generation=generation.run_generation_job
    def guarded_provider(selected_config):
        return ledger.wrap(real_factory(selected_config))
    def no_repair(**kwargs):
        return real_generation(**kwargs,allow_technical_repair=False)
    try:
        with patch.dict(os.environ,{"CAE_DATA_DIR":str(store.root)}), patch.object(factory,"make_provider",guarded_provider), patch.object(generation,"run_generation_job",no_repair):
            app=AppTest.from_file(ROOT/"app.py")
            app.session_state["project_id"]=pid
            app.run(timeout=40);healthy(app,"reopened advisor frontend")
            if "Engineering advisor" not in [h.value for h in app.subheader]:
                raise AssertionError("Persisted advisor frontend did not render")
            before=store.brief(pid)
            previous_assistants=len([m for m in store.records(pid,"ChatMessage") if m.role=="assistant"])
            message=("Using the saved reference sketch and retrieved engineering knowledge, cite actual source chunk IDs "
                "and separate visible features from inference. Update brief_updates.loads to record the stated "
                "100 N negative-Z force at the maximum-X end with the minimum-X end fixed. Preserve the known "
                "length/width/height and generic reference steel. Provide a concise source-supported explanation.")
            app.chat_input[0].set_value(message).run(timeout=config.worker_timeout_seconds+30)
            healthy(app,"real advisor continuation")
            assistants=[m for m in store.records(pid,"ChatMessage") if m.role=="assistant"]
            refined=store.brief(pid)
            if (len(assistants)!=previous_assistants+1 or assistants[-1].text.startswith("Gemini is BLOCKED")
                    or not assistants[-1].sources or not refined.visual_observations or not refined.loads
                    or refined.dimensions!=before.dimensions or refined.materials!=before.materials
                    or any(o.image_id not in refined.reference_image_ids for o in refined.visual_observations)):
                raise AssertionError("Real advisor reply did not validate image, sources and fixed brief inputs")
            actions.append("Advisor answered with the saved real sketch and retrieved sources")
            print(json.dumps({"stage":"real_advisor","project_id":pid,
                "cited_sources":len(assistants[-1].sources),"visual_observations":len(refined.visual_observations),
                "new_budget":ledger.snapshot()}),flush=True)

            click(app,"Generate this design",actions)
            wait_job(app,store,pid,"DESIGN_GENERATION",config)
            from review import current_review, review_artifacts
            from examples.container_check import assert_rectangular_metrics
            review=current_review(store,pid)
            assert_rectangular_metrics(review_artifacts(store,pid,review)["metrics"])
            if store.project(pid)["state"]!=S.DESIGN_REVIEW or len(app.get("plotly_chart"))<1:
                raise AssertionError("Real generated STL was not displayed for review")
            actions.append("Displayed real generated STL and geometry checks")
            if ledger.snapshot()["count"]!=3 or first["count"]+second["count"]+ledger.snapshot()["count"]!=5:
                raise AssertionError("The cumulative five-request generation cap was not respected")
            print(json.dumps({"stage":"real_generated_cad","revision_id":review.revision_id,
                "geometry_hash":review.geometry_hash,"cumulative_live_requests":5}),flush=True)

            click(app,"Accept design",actions)
            if store.project(pid)["state"]!=S.ANALYSIS_INTAKE:
                raise AssertionError("Exact checked design was not accepted")
            next(t for t in app.text_input if t.label=="Engineering question").input(
                "What are displacement, stress and reaction balance under a 100 N negative-Z end force?")
            next(n for n in app.number_input if n.label=="Force Z (N)").set_value(-100.)
            next(c for c in app.checkbox if c.label=="Use the displayed sourced reference-steel properties").check()
            click(app,"Prepare actual analysis regions",actions)
            wait_job(app,store,pid,"FEM_PREPARE",config)
            if "Review the actual analysis setup" not in [h.value for h in app.header] or len(app.get("plotly_chart"))<1:
                raise AssertionError("Real selected support/load faces were not displayed")
            spec=store.records(pid,"AnalysisSpec")[-1]
            if (spec.loads[0].force_n!=(0,0,-100) or spec.mesh.element_size_mm!=3
                    or spec.material.material_id!="freecad-generic-steel"):
                raise AssertionError("Validated manual FEM inputs differ from the specified setup")
            preparation=store.record(pid,"FEMPreparation",spec.analysis_id,spec.version)
            state={"project_id":pid,"analysis_id":spec.analysis_id,"spec_version":spec.version,
                "data_dir":str(store.root),"confirmation_hash":preparation.confirmation_hash,
                "regions":[r.model_dump(mode="json") for r in preparation.regions],
                "specification":spec.model_dump(mode="json"),"directory":preparation.directory,
                "app_actions":actions,"budget":ledger.snapshot(),"cumulative_live_requests":5,
                "ledger":"second-recovery-requests.sqlite3","analysis_specification_source":"validated_manual_frontend"}
            write_once(CONTROL/"ui-prepared.json",state)
            return state
    except BaseException:
        ledger.stop()
        raise


def solve(config, confirmation):
    from streamlit.testing.v1 import AppTest
    from schemas import ArtifactManifest
    state=json.loads((CONTROL/"ui-prepared.json").read_text(encoding="utf-8"))
    if confirmation!=state["confirmation_hash"]:
        raise ValueError("Explicit confirmation of the displayed actual-region setup is required")
    if (CONTROL/"ui-solved.json").exists():
        raise RuntimeError("This solve was already verified; never replay it")
    ledger=LiveBudget(CONTROL/state["ledger"])
    if ledger.snapshot()["count"]!=state["budget"]["count"] or ledger.snapshot()["stopped"]:
        raise RuntimeError("The bounded live preparation was not successful")
    store=Store(state["data_dir"]); pid=state["project_id"]
    spec=store.record(pid,"AnalysisSpec",state["analysis_id"],state["spec_version"])
    prepared=store.record(pid,"FEMPreparation",spec.analysis_id,spec.version)
    if prepared.confirmation_hash!=confirmation:
        raise ValueError("The saved FEM setup changed after review")
    actions=list(state["app_actions"])
    with patch.dict(os.environ,{"CAE_DATA_DIR":str(store.root)}):
        app=AppTest.from_file(ROOT/"app.py")
        app.session_state["project_id"]=pid
        app.run(timeout=40); healthy(app,"reopen analysis setup")
        if "Review the actual analysis setup" not in [h.value for h in app.header] or len(app.get("plotly_chart"))<1:
            raise AssertionError("Confirmed faces were not displayed in the reopened app")
        next(c for c in app.checkbox if c.label.startswith("I confirm this material")).check().run(timeout=40)
        healthy(app,"actual-region confirmation")
        click(app,"Confirm setup and run FreeCAD FEM",actions)
        job=wait_job(app,store,pid,"FEM_SOLVE",config)
        result=store.record(pid,"AnalysisResults",job.result["run_id"],1)
        if result.status!="succeeded" or result.provenance!="actual_solver":
            raise AssertionError("No real successful FreeCAD FEM result was saved")
        directory=store.path(job.result["artifact_directory"])
        store.verify_manifest(store.record(pid,"ArtifactManifest",job.result["manifest_id"],1))
        raw=json.loads((directory/"solver_results.json").read_text(encoding="utf-8"))
        report=(directory/"integration_report.md").read_text(encoding="utf-8")
        for field in ("maximum_displacement_mm","maximum_von_mises_mpa"):
            if getattr(result,field)!=raw[field] or str(raw[field]) not in report:
                raise AssertionError("Numerical report fields differ from extracted solver results")
        if result.reaction_force_n!=parse_reaction_totals((directory/"solver/Mesh.dat").read_text(encoding="utf-8")):
            raise AssertionError("Reaction totals differ from CalculiX DAT output")
        checks=json.loads((directory/"verification.json").read_text(encoding="utf-8"))
        if not checks["beam_applicable"] or checks["displacement_relative_difference"]>=.12 or checks["reaction_relative_residual"]>=1e-4:
            raise AssertionError("Beam-theory or force-balance check failed")
        metrics={m.label:m.value for m in app.metric}
        if metrics["Maximum displacement (mm)"]!=f"{result.maximum_displacement_mm:.8f}" or metrics["Maximum von Mises stress (MPa)"]!=f"{result.maximum_von_mises_mpa:.6f}":
            raise AssertionError("Displayed app metrics differ from extracted solver results")
        if len(app.get("plotly_chart"))<2 or not any("# Engineering analysis report" in m.value for m in app.markdown):
            raise AssertionError("App did not display actual result plots and numerical report")
        before_jobs=len(store.jobs(pid)); before_calls=ledger.snapshot()["count"]
        reopened=AppTest.from_file(ROOT/"app.py")
        reopened.session_state["project_id"]=pid
        reopened.run(timeout=40); healthy(reopened,"reopened final report")
        if len(store.jobs(pid))!=before_jobs or ledger.snapshot()["count"]!=before_calls:
            raise AssertionError("Reopening repeated an LLM/CAD/FEA job")
        evidence={"project_id":pid,"analysis_id":spec.analysis_id,"app_actions":actions,
            "result":result.model_dump(mode="json"),"checks":checks,"app_metrics":metrics,
            "directory":str(directory),"budget":ledger.snapshot(),"cumulative_live_requests":5,
            "explanation_exercised":False,"mocked_ai_responses":False,"reopened_without_execution":True}
        write_once(CONTROL/"ui-solved.json",evidence)
        ledger.stop()
        return evidence


def main():
    parser=argparse.ArgumentParser(description=__doc__)
    parser.add_argument("phase",choices=("prepare","continue","solve","status"))
    parser.add_argument("--live",action="store_true",help="Explicit opt-in to the bounded live allowance")
    parser.add_argument("--confirm",help="Exact user-reviewed FEM confirmation hash")
    args=parser.parse_args()
    if args.phase=="status":
        summary=live_smoke.LiveBudget(CONTROL/"recovery-requests.sqlite3").snapshot() if (CONTROL/"recovery-requests.sqlite3").exists() else None
        latest=live_smoke.LiveBudget(CONTROL/"second-recovery-requests.sqlite3").snapshot() if (CONTROL/"second-recovery-requests.sqlite3").exists() else None
        print(json.dumps({"first_allowance":summary,"continuation_allowance":latest,"saved_ui_project":(CONTROL/"ui-project.json").exists(),
                          "prepared":(CONTROL/"ui-prepared.json").exists(),"solved":(CONTROL/"ui-solved.json").exists()},indent=2))
        return
    if not args.live: parser.error("--live is required for this authorized one-time frontend journey")
    config=Config.from_env()
    if args.phase=="prepare":
        result=prepare(config)
    elif args.phase=="continue":
        result=continue_saved_frontend(config)
    else:
        if not args.confirm: parser.error("--confirm is required after the user's exact face review")
        result=solve(config,args.confirm)
    print(json.dumps(result,indent=2))


if __name__=="__main__": main()

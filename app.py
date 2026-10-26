"""Streamlit application shell for persistent intake and route selection."""

from __future__ import annotations

import json
from concurrent.futures import ThreadPoolExecutor

import streamlit as st

from agents.advisor import (accept_choice, advise, apply_reply_to_brief,
                            explicit_dimension_edit, grounded_local_fallback, should_retrieve)
from app_logic import dimensions_from_lines, draft_brief, requirements_from_lines
from config import Config
from providers.vertex import ImagePayload, ProviderUnavailable
from providers.factory import make_provider
from rag.retriever import LocalHybridRetriever
from schemas import ChatMessage, DesignBrief, Intake, WorkflowState
from storage import ConflictError, Store, Upload
from workflow import Workflow
from generation import GENERATION_STATES, latest_generation, retry_generation, start_generation
from schemas import JobStatus
from app_views import render_design_review, render_restart, render_analysis


st.set_page_config(page_title="Agentic CAE", layout="wide")
config = Config.from_env()
store = Store(config.data_dir)
flow = Workflow(store)


def rerun() -> None:
    st.rerun()


def route_to(target: WorkflowState, **kwargs) -> None:
    project = store.project(st.session_state.project_id)
    flow.transition(project["project_id"], target, expected_version=project["row_version"],
                    reason=kwargs.pop("reason"), **kwargs)


st.title("Agentic CAE")
st.caption("Persistent mechanical design workflow prototype")


@st.cache_resource
def generation_executor():
    return ThreadPoolExecutor(max_workers=2, thread_name_prefix="cae-generation")

projects = store.projects()
with st.sidebar:
    st.subheader("Sessions")
    labels = {item["project_id"]: f"{item['project_id'][:8]} · {item['state']}" for item in projects}
    choices = ["New project", *labels]
    selected = st.selectbox("Open a persisted session", choices,
                            format_func=lambda value: labels.get(value, value))
    if selected == "New project":
        if st.button("Start new intake"):
            st.session_state.pop("project_id", None)
            rerun()
    elif st.button("Open selected session"):
        st.session_state.project_id = selected
        rerun()
    with st.expander("Real integration example"):
        st.caption("Generate actual reference cantilever CAD with the repository-authored CadQuery model. No LLM, mocked geometry or solver values.")
        if st.button("Generate reference cantilever", disabled=not bool(config.freecad_cmd)):
            try:
                from examples.deterministic_demo import run
                with st.spinner("Generating STEP/STL, importing with FreeCAD and checking real geometry…"):
                    result = run(config.data_dir)
                st.session_state.project_id = result["project_id"]
                rerun()
            except (RuntimeError, OSError, ImportError) as error:
                st.error(str(error))

project_id = st.session_state.get("project_id")
if not project_id:
    st.header("Tell us what you want to design")
    st.write("An incomplete idea is welcome. The engineering advisor is intended to help discover missing choices.")
    with st.form("intake", clear_on_submit=False):
        idea = st.text_area("What do you want to design?", placeholder="A small support bracket for…")
        purpose = st.text_area("Purpose and intended use (optional)")
        hard = st.text_area("Known hard requirements — one per line (optional)")
        soft = st.text_area("Known preferences — one per line (optional)")
        units = st.selectbox("Known dimension units (optional)", ["Not specified", "mm", "m", "in"])
        dimensions = st.text_area("Known dimensions — one per line, for example: length = 100 mm (optional)")
        material = st.text_input("Material preference (optional)")
        manufacturing = st.text_input("Manufacturing preference (optional)")
        files = st.file_uploader("Reference images (optional, multiple)",
                                 type=["png", "jpg", "jpeg", "webp"], accept_multiple_files=True)
        submitted = st.form_submit_button("Save idea and continue", type="primary")
    if submitted:
        if not idea.strip():
            st.error("Describe the idea in at least a few words.")
        else:
            try:
                selected_units = None if units == "Not specified" else units
                intake = Intake(
                    idea=idea.strip(), purpose=purpose.strip(),
                    hard_requirements=requirements_from_lines(hard, "HARD"),
                    soft_requirements=requirements_from_lines(soft, "SOFT"),
                    dimensions=dimensions_from_lines(dimensions, selected_units), units=selected_units,
                    material_preferences=[material.strip()] if material.strip() else [],
                    manufacturing_preferences=[manufacturing.strip()] if manufacturing.strip() else [],
                )
                uploads = [Upload(file.name, file.type, file.getvalue()) for file in files]
                project_id = store.create_project(intake, uploads)
                project = store.project(project_id)
                flow.transition(project_id, WorkflowState.ROUTE_SELECTION,
                                expected_version=project["row_version"], reason="Intake saved")
                st.session_state.project_id = project_id
                rerun()
            except ValueError as error:
                st.error(str(error))
    st.stop()

project = store.project(project_id)
intake = store.original_intake(project_id)
st.caption(f"Session `{project_id}` · state **{project['state'].value}**")

if project["state"] == WorkflowState.ROUTE_SELECTION:
    st.header("Choose how to continue")
    if project["brief_version"]:
        working = store.brief(project_id)
        with st.expander("Original idea — prepopulated working copy", expanded=True):
            st.caption("The original intake and failed attempts remain unchanged. Edit this working copy to start again.")
            for image in store.images(project_id):
                if image.image_id in working.reference_image_ids:
                    st.image(store.read_image(project_id, image.image_id), width=180, alt="Original persisted reference image")
            with st.form("restart-working-intake"):
                description = st.text_area("Idea", working.description)
                purpose = st.text_area("Purpose", working.purpose)
                hard = st.text_area("Hard requirements", "\n".join(r.text for r in working.hard_requirements))
                soft = st.text_area("Preferences", "\n".join(r.text for r in working.soft_requirements))
                dimensions = st.text_area("Dimensions", "\n".join(f"{d.name} = {d.value:g} {d.unit}" for d in working.dimensions))
                material = st.text_input("Materials", ", ".join(working.materials))
                manufacturing = st.text_input("Manufacturing", ", ".join(working.manufacturing))
                changed = st.form_submit_button("Update working idea")
            if changed:
                if not description.strip():
                    st.error("Describe the working idea before saving.")
                    st.stop()
                updated = DesignBrief.model_validate({**working.model_dump(), "version": working.version + 1,
                    "description": description, "design_name": description.strip().splitlines()[0][:80], "purpose": purpose,
                    "hard_requirements": requirements_from_lines(hard,"HARD"), "soft_requirements":requirements_from_lines(soft,"SOFT"),
                    "dimensions": dimensions_from_lines(dimensions, intake.units),
                    "materials": [material] if material.strip() else [], "manufacturing":[manufacturing] if manufacturing.strip() else []})
                store.save_brief(project_id, updated, expected_version=working.version, actor="user", reason="Edit original-idea restart working copy")
                rerun()
    left, right = st.columns(2)
    with left:
        st.subheader("Brainstorm with our AI Mechanical Engineering Maestro")
        st.write("Explore mechanisms, joints, materials, manufacturing methods, and design trade-offs with an AI advisor supported by a mechanical engineering knowledge base. Together, refine your idea into a clearer design brief.")
        if st.button("Open engineering advisor", width="stretch"):
            previous_version = project["brief_version"]
            brief = (store.brief(project_id).model_copy(update={"version": previous_version + 1}) if previous_version else draft_brief(intake, automatic=False))
            store.save_brief(project_id, brief, expected_version=previous_version, actor="user_route",
                             reason="Initialize shared advisor brief")
            route_to(WorkflowState.ADVISOR_CHAT, route="advisor", reason="User selected advisor route")
            rerun()
    with right:
        st.subheader("Design it for me—I trust your judgment")
        st.write("Start from your description. The AI will choose reasonable defaults and clearly record its assumptions.")
        if st.button("Draft automatically", type="primary", width="stretch"):
            previous_version = project["brief_version"]
            brief = (store.brief(project_id).model_copy(update={"version": previous_version + 1}) if previous_version else draft_brief(intake, automatic=True))
            store.save_brief(project_id, brief, expected_version=previous_version, actor="automatic_route",
                             reason="Create automatic-route brief with visible assumptions")
            route_to(WorkflowState.BRIEF_READY, route="automatic", reason="User selected automatic route")
            route_to(WorkflowState.SPEC_GENERATION, reason="Automatic route enters specification generation")
            rerun()
    st.stop()

if project["state"] == WorkflowState.ADVISOR_CHAT:
    index_path = config.data_dir / "knowledge" / "index.json"
    if not index_path.is_file():
        st.error("The knowledge index is missing. Run: python -m cli knowledge-update")
        st.stop()
    retriever = LocalHybridRetriever(index_path)
    provider = make_provider(config)
    provider_issues = provider.availability_issues()
    if provider_issues:
        st.warning("Gemini is blocked: " + "; ".join(provider_issues) +
                   ". The workspace will show clearly labeled local retrieval evidence only.")
    else:
        st.info("Gemini is configured. Sending a message makes a live request to the selected provider.")
    chat, brief_column = st.columns([1, 1])
    with chat:
        st.subheader("Engineering advisor")
        history = list(store.records(project_id, "ChatMessage"))
        for message in history:
            with st.chat_message(message.role):
                st.write(message.text)
                if message.sources:
                    with st.expander("Sources"):
                        for source in message.sources:
                            st.markdown(f"- `{source.chunk_id}` — {source.title}, {source.section_or_page or 'section unavailable'} ({source.source_kind})")
        message_images = st.file_uploader("Images for the next advisor message (optional)",
                                          type=["png", "jpg", "jpeg", "webp"],
                                          accept_multiple_files=True, key="advisor-images")
        question = st.chat_input("Ask about mechanisms, joints, materials, manufacture, or trade-offs")
        if question:
            saved_images = [store.save_image(project_id, Upload(file.name, file.type, file.getvalue()))
                            for file in message_images]
            current = store.brief(project_id)
            if saved_images:
                current = current.model_copy(update={"version": current.version + 1,
                                                     "reference_image_ids": current.reference_image_ids +
                                                     [image.image_id for image in saved_images]})
                store.save_brief(project_id, current, expected_version=current.version - 1,
                                 actor="user", reason="Attach advisor reference images")
            user_message = ChatMessage(role="user", text=question,
                                       image_ids=[image.image_id for image in saved_images],
                                       brief_version=current.version)
            store.save_record(project_id, user_message.message_id, 1, user_message)
            image_payloads = [ImagePayload(data=store.read_image(project_id, image.image_id),
                                           media_type=image.media_type, role=image.role,
                                           image_id=image.image_id) for image in store.images(project_id)
                              if image.image_id in current.reference_image_ids]
            hits = retriever.search(question) if should_retrieve(question) else []
            try:
                direct = explicit_dimension_edit(current, question)
                if direct:
                    reply = direct
                elif provider_issues:
                    reply = grounded_local_fallback(question, hits)
                else:
                    reply = advise(provider=provider, retriever=retriever, brief=current,
                                   history=[*history, user_message], message=question, images=image_payloads)
            except ProviderUnavailable as error:
                local = grounded_local_fallback(question, hits)
                reply = local.model_copy(update={"text": f"Gemini is BLOCKED: {error}\n\n{local.text}"})
            updated = apply_reply_to_brief(current, reply)
            store.save_brief(project_id, updated, expected_version=current.version,
                             actor="advisor", reason=f"Advisor response in {reply.mode} mode")
            assistant = ChatMessage(role="assistant", text=reply.text, sources=reply.sources,
                                    brief_version=updated.version)
            store.save_record(project_id, assistant.message_id, 1, assistant)
            rerun()
    with brief_column:
        current = store.brief(project_id)
        st.subheader("Living design brief")
        with st.form(f"brief-{current.version}"):
            name = st.text_input("Design name", current.design_name)
            description = st.text_area("Description", current.description)
            purpose = st.text_area("Purpose", current.purpose)
            assumptions = st.text_area("Assumptions", "\n".join(current.assumptions))
            questions = st.text_area("Unresolved questions", "\n".join(current.unresolved_questions))
            save = st.form_submit_button("Save brief changes")
        if save:
            updated = DesignBrief.model_validate({**current.model_dump(), "version": current.version + 1,
                                                  "design_name": name.strip(), "description": description.strip(),
                                                  "purpose": purpose.strip(),
                                                  "assumptions": [line for line in assumptions.splitlines() if line.strip()],
                                                  "unresolved_questions": [line for line in questions.splitlines() if line.strip()]})
            try:
                store.save_brief(project_id, updated, expected_version=current.version,
                                 actor="user", reason="Direct living-brief edit")
                rerun()
            except ConflictError:
                st.error("The brief changed in another action. Reload and reconcile your edit.")
        if current.proposed_choices:
            st.subheader("Proposed choices")
            for decision in current.proposed_choices:
                if st.button(f"Accept: {decision.text}", key=f"accept-{decision.decision_id}"):
                    accepted = accept_choice(current, decision.decision_id)
                    store.save_brief(project_id, accepted, expected_version=current.version,
                                     actor="user", reason=f"Accept proposed choice {decision.decision_id}")
                    rerun()
    st.button("Continue brainstorming", disabled=True,
              help="Send another message in the advisor input to continue")
    if st.button("Generate this design", type="primary"):
        route_to(WorkflowState.BRIEF_READY, reason="User froze the current brief")
        route_to(WorkflowState.SPEC_GENERATION, reason="Frozen brief enters specification generation")
        rerun()
    if st.button("Switch to automatic design"):
        current = store.brief(project_id)
        updated = current.model_copy(update={"version": current.version + 1,
                                             "assumptions": current.assumptions + ["Automatic design may choose supported defaults and will record them."]})
        store.save_brief(project_id, updated, expected_version=current.version,
                         actor="user", reason="Switch advisor workspace to automatic design")
        route_to(WorkflowState.BRIEF_READY, reason="Switch to automatic generation")
        route_to(WorkflowState.SPEC_GENERATION, reason="Automatic design enters specification generation")
        rerun()
    st.stop()

if project["state"] in (WorkflowState.DESIGN_REVIEW, WorkflowState.RESTART_OFFER):
    try:
        if project["state"] == WorkflowState.DESIGN_REVIEW:
            render_design_review(store, project_id, project, config, generation_executor())
        else:
            render_restart(store, project_id, project)
    except (ValueError, RuntimeError, OSError) as error:
        st.error(str(error))
    st.stop()

analysis_states = {WorkflowState.ANALYSIS_INTAKE, WorkflowState.ANALYSIS_SPEC_REVIEW, WorkflowState.ANALYSIS_EXECUTION, WorkflowState.REPORT_READY}
if project["state"] in analysis_states or (project["state"] in (WorkflowState.BLOCKED, WorkflowState.ERROR) and project["resume_state"] in analysis_states):
    try:
        render_analysis(store, project_id, project, config, generation_executor())
    except (ValueError, RuntimeError, OSError) as error:
        st.error(str(error))
    st.stop()

generation_blocked = project["state"] in (WorkflowState.BLOCKED, WorkflowState.ERROR) and project["resume_state"] in GENERATION_STATES
if project["state"] in GENERATION_STATES or generation_blocked:
    brief = store.brief(project_id)
    st.header("Specification generation")
    st.caption(f"Frozen brief v{brief.version}. Generated code runs only inside the configured restricted container.")
    provider = make_provider(config)
    issues = provider.availability_issues()
    job = latest_generation(store, project_id)
    if job is None and issues:
        st.warning("Specification generation is blocked: " + "; ".join(issues))
    elif job is None and project["state"] == WorkflowState.SPEC_GENERATION:
        job = start_generation(store=store, project_id=project_id, provider=provider,
                               config=config, executor=generation_executor())
    if job is not None:
        @st.fragment(run_every=2 if job.status in (JobStatus.PENDING, JobStatus.RUNNING) else None)
        def generation_progress():
            current_job = store.job(job.job_id)
            current_project = store.project(project_id)
            st.write(f"Generation job: **{current_job.status.value}** · stage **{current_project['state'].value}**")
            if current_job.error:
                st.error(current_job.error)
            if current_job.status == JobStatus.SUCCEEDED:
                st.success("The generated solid passed FreeCAD geometry checks. Engineering analysis has not run.")
            if current_job.result and current_job.result.get("artifact_directory"):
                relative = current_job.result["artifact_directory"]
                for name in ("design_spec.json", "design_spec.md", "generation-0.json", "generation-1.json"):
                    path = store.path(relative + "/" + name)
                    if path.is_file():
                        st.download_button("Download " + name, path.read_bytes(), file_name=name, key="download-" + name)
            if current_project["state"] != project["state"]:
                st.rerun()
        generation_progress()
        if generation_blocked and st.button("Retry generation with a new attempt", disabled=bool(issues)):
            retry_generation(store=store, project_id=project_id, provider=provider,
                             config=config, executor=generation_executor())
            rerun()
    with st.expander("Frozen design brief", expanded=job is None):
        st.json(json.loads(brief.model_dump_json()))
    st.stop()

st.info("This persisted state is implemented by a later milestone. No expensive job was started automatically.")

"""Actual geometry/result views; no synthetic meshes or solver numbers."""
import io
import json
import plotly.graph_objects as go
import trimesh


def stl_figure(data):
    mesh = trimesh.load(io.BytesIO(data), file_type="stl", force="mesh")
    x, y, z = mesh.vertices.T
    i, j, k = mesh.faces.T
    figure = go.Figure(go.Mesh3d(x=x, y=y, z=z, i=i, j=j, k=k, color="steelblue", flatshading=True))
    figure.update_layout(scene={"aspectmode": "data", "xaxis_title": "X (mm)", "yaxis_title": "Y (mm)", "zaxis_title": "Z (mm)"}, margin=dict(l=0,r=0,t=20,b=0))
    return figure


def regions_figure(raw):
    figure = go.Figure()
    for label, mesh, color, opacity in [("Accepted solid", raw["model"], "lightgray", .25), *[
            (region["selector_id"] + " / " + region["face_name"], region["mesh"], color, 1)
            for region, color in zip(raw["regions"], ["royalblue", "orangered"])]]:
        x,y,z = zip(*mesh["vertices"]); i,j,k = zip(*mesh["triangles"])
        figure.add_trace(go.Mesh3d(x=x,y=y,z=z,i=i,j=j,k=k,color=color,opacity=opacity,name=label,showlegend=True))
    figure.update_layout(scene={"aspectmode":"data","xaxis_title":"X (mm)","yaxis_title":"Y (mm)","zaxis_title":"Z (mm)"})
    return figure


def nodal_figure(raw, quantity):
    points = [raw["coordinates"][str(n)] for n in raw["node_numbers"]]
    x,y,z = zip(*points)
    label = "Displacement (mm)" if quantity == "displacements_mm" else "von Mises (MPa)"
    figure = go.Figure(go.Scatter3d(x=x,y=y,z=z,mode="markers",marker={"size":2,"color":raw[quantity],"colorscale":"Viridis","colorbar":{"title":label}},name=label))
    figure.update_layout(scene={"aspectmode":"data","xaxis_title":"X (mm)","yaxis_title":"Y (mm)","zaxis_title":"Z (mm)"})
    return figure


def render_design_review(store, project_id, project, config, executor):
    import streamlit as st
    from review import current_review, review_artifacts, accept_design, reject_design
    from generation import run_generation_job
    from providers.vertex import VertexGeminiProvider
    from schemas import DesignFeedback
    from storage import Upload
    review = current_review(store, project_id)
    artifacts = review_artifacts(store, project_id, review)
    st.header("Review your design")
    st.caption("Repository-authored reference geometry" if review.source == "trusted_reference" else "Generated geometry; engineering analysis has not run")
    files = {a.role: a for a in artifacts["cad"].artifacts + artifacts["freecad"].artifacts}
    st.plotly_chart(stl_figure(store.path(files["preview"].relative_path).read_bytes()), key="design-" + review.revision_id,
                    alt="Actual STL geometry of the current checked revision", width="stretch")
    st.write(f"Revision `{review.revision_id}` · STEP SHA-256 `{review.geometry_hash}`")
    st.dataframe([{"Dimension": d.name,"Value": d.value,"Unit":d.unit,"Origin":d.origin.value} for d in artifacts["spec"].dimensions],
                 hide_index=True, alt="Current design dimensions and provenance")
    st.markdown("**Assumptions**\n\n" + "\n".join("- " + a for a in artifacts["spec"].assumptions))
    st.dataframe([{"Rule": c.rule_id,"Status":c.status.value,"Measured":str(c.measured_value),"Message":c.message} for c in review.checks],
                 hide_index=True, alt="Geometry check results and unimplemented checks")
    st.caption("NOT_IMPLEMENTED means unchecked; geometry acceptance is not engineering approval.")
    for role in ("step", "preview", "fcstd", "model_source", "parameters"):
        artifact = files[role]
        st.download_button("Download " + role, store.path(artifact.relative_path).read_bytes(),
                           file_name=artifact.relative_path.split("/")[-1], key="cad-download-" + role)
    with st.expander("Current specification"):
        st.json(artifacts["spec"].model_dump(mode="json"))
    if st.button("Accept design", type="primary"):
        accept_design(store, project_id, expected_version=project["row_version"], revision_id=review.revision_id,
                      geometry_hash=review.geometry_hash)
        st.rerun()
    with st.form("revision-feedback-" + review.revision_id):
        text = st.text_area("Revision feedback (optional)")
        rating = st.selectbox("Optional rating", ["No rating", "Thumbs down"])
        images = st.file_uploader("Desired revision reference images (optional)", type=["png","jpg","jpeg","webp"], accept_multiple_files=True)
        submit = st.form_submit_button("Submit revision")
        st.caption("A revision request without details is valid. Each attempt allows two rejections and one regenerated candidate.")
    if submit:
        saved = [store.save_image(project_id, Upload(f.name, f.type, f.getvalue())) for f in images]
        feedback = DesignFeedback(attempt_id=review.attempt_id, revision_id=review.revision_id, action="revise",
            thumbs="down" if rating == "Thumbs down" else None, text=text, reference_image_ids=[i.image_id for i in saved])
        job = reject_design(store, project_id, feedback, expected_version=project["row_version"])
        if job:
            executor.submit(run_generation_job, store=store, job_id=job.job_id,
                            provider=VertexGeminiProvider(config), config=config)
        st.rerun()


def render_restart(store, project_id, project):
    import streamlit as st
    from review import restart_attempt
    st.header("This design attempt was rejected twice")
    st.write("Both revisions, their artifacts and feedback are preserved.")
    for label, choice in [("Retry from approved brief", "approved_brief"),
                          ("Return to brainstorming with feedback", "brainstorm"),
                          ("Start from original idea", "original_idea")]:
        if st.button(label):
            restart_attempt(store, project_id, choice, expected_version=project["row_version"])
            st.rerun()


def render_analysis(store, project_id, project, config, executor):
    import hashlib
    import streamlit as st
    from schemas import WorkflowState as S, JobStatus
    from fem_workflow import accepted_artifacts, propose_static, enqueue_prepare, enqueue_solve, run_fem_job, edit_analysis_inputs
    review, artifacts = accepted_artifacts(store, project_id)
    jobs = [j for j in store.jobs(project_id) if j.kind in ("FEM_PREPARE", "FEM_SOLVE")]
    if jobs and jobs[-1].status in (JobStatus.PENDING, JobStatus.RUNNING):
        st.header("FreeCAD FEM progress")
        job = jobs[-1]
        @st.fragment(run_every=2)
        def progress():
            latest = store.job(job.job_id)
            st.write(f"{latest.kind}: **{latest.status.value}**")
            st.caption("The owned worker is generating real artifacts; reopening does not restart the job.")
            if latest.status not in (JobStatus.PENDING, JobStatus.RUNNING):
                st.rerun()
        progress()
        st.button("Refresh progress")
        return
    if project["state"] == S.ANALYSIS_INTAKE:
        st.header("What do you want to learn about this design?")
        st.info("Executable: linear static structural. Modal, vibration, fatigue and transient execution are not yet supported.")
        st.write("Supported setup: fixed minimum-X face, resultant force on maximum-X face, quadratic tetrahedral mesh.")
        st.write("Reference steel: E = 200000 MPa, Poisson ratio = 0.3, density = 7900 kg/m³.")
        from analysis.materials import STEEL_SOURCE
        st.markdown(f"[Material property source]({STEEL_SOURCE})")
        keys = {name: "fem-" + review.revision_id + "-" + name for name in ("fx","fy","fz","mesh","material","question")}
        for name,value in {"fx":0.,"fy":0.,"fz":0.,"mesh":3.,"material":False,"question":""}.items():
            st.session_state.setdefault(keys[name],value)
        if review.source == "trusted_reference" and st.button("Use the reference cantilever setup"):
            for name,value in {"fx":0.,"fy":0.,"fz":-100.,"mesh":3.,"material":True,
                               "question":"What is the displacement and stress under the reference 100 N tip force?"}.items():
                st.session_state[keys[name]]=value
        with st.form("analysis-inputs-" + review.revision_id):
            question = st.text_input("Engineering question", key=keys["question"])
            fx = st.number_input("Force X (N)", value=None, step=1., key=keys["fx"])
            fy = st.number_input("Force Y (N)", value=None, step=1., key=keys["fy"])
            fz = st.number_input("Force Z (N)", value=None, step=1., key=keys["fz"])
            size = st.number_input("Mesh element size (mm)", min_value=.1, value=None, step=1., key=keys["mesh"])
            material = st.checkbox("Use the displayed sourced reference-steel properties", key=keys["material"])
            submitted = st.form_submit_button("Prepare actual analysis regions")
        if submitted:
            if not material:
                st.error("Explicitly select the sourced material before preparation.")
                return
            spec = propose_static(store, project_id, question=question, force_n=(fx,fy,fz), mesh_mm=size)
            job = enqueue_prepare(store, project_id, spec, expected_version=project["row_version"])
            executor.submit(run_fem_job, store=store, job_id=job.job_id, config=config)
            st.rerun()
        return
    spec = store.records(project_id, "AnalysisSpec")[-1]
    if (spec.accepted_revision_id,spec.geometry_hash) != (review.revision_id,review.geometry_hash):
        raise ValueError("Analysis is stale for the accepted geometry")
    relative = f"projects/{project_id}/analyses/{spec.analysis_id}"
    directory = store.path(relative)
    if project["state"] == S.ANALYSIS_SPEC_REVIEW:
        st.header("Review the actual analysis setup")
        preparation = store.record(project_id, "FEMPreparation", spec.analysis_id, spec.version)
        data = (directory / "regions.json").read_bytes()
        if hashlib.sha256(data).hexdigest() != preparation.regions_hash:
            raise ValueError("Selected region geometry was altered; prepare again")
        st.plotly_chart(regions_figure(json.loads(data)), key="regions-" + spec.analysis_id,
                        alt="Actual imported support and load faces selected inside FreeCAD FEM")
        st.json(spec.model_dump(mode="json"))
        if st.button("Change analysis inputs"):
            edit_analysis_inputs(store,project_id,expected_version=project["row_version"])
            st.rerun()
        confirmed = st.checkbox("I confirm this material, load, supports, mesh and highlighted faces", key="confirm-" + preparation.confirmation_hash)
        if st.button("Confirm setup and run FreeCAD FEM", disabled=not confirmed, type="primary"):
            job = enqueue_solve(store, project_id, spec, preparation, expected_version=project["row_version"],
                                confirmation_hash=preparation.confirmation_hash)
            executor.submit(run_fem_job, store=store, job_id=job.job_id, config=config)
            st.rerun()
        return
    if project["state"] == S.REPORT_READY:
        st.header("FreeCAD FEM results")
        result = [r for r in store.records(project_id, "AnalysisResults") if r.analysis_id == spec.analysis_id][-1]
        result.assert_matches(spec)
        job = next(j for j in reversed(jobs) if j.kind == "FEM_SOLVE" and j.payload["analysis_id"] == spec.analysis_id)
        manifest = store.record(project_id, "ArtifactManifest", job.result["manifest_id"], 1)
        if result.status != "succeeded":
            st.error(result.error)
        else:
            store.verify_manifest(manifest)
            st.success("Actual FreeCAD FEM / CalculiX solve completed")
            st.caption(result.solver_version + " · actual_solver · preliminary single-mesh results")
            st.metric("Maximum displacement (mm)", f"{result.maximum_displacement_mm:.8f}")
            st.metric("Maximum von Mises stress (MPa)", f"{result.maximum_von_mises_mpa:.6f}")
            st.write(f"Mesh: {result.mesh.nodes:,} nodes / {result.mesh.elements:,} elements")
            raw = json.loads((directory / "solver_results.json").read_text(encoding="utf-8"))
            for quantity in ("displacements_mm", "von_mises_mpa"):
                st.plotly_chart(nodal_figure(raw, quantity), key=quantity + spec.analysis_id,
                                alt="Actual solver nodal " + quantity)
            checks = json.loads((directory / "verification.json").read_text(encoding="utf-8"))
            if checks["beam_applicable"]:
                st.metric("Beam-theory displacement (mm)", f"{checks['beam_estimate_mm']:.8f}")
                st.metric("Displacement difference", f"{100 * checks['displacement_relative_difference']:.4f}%")
            st.metric("Reaction-force residual (N)", f"{checks['reaction_residual_magnitude_n']:.8g}")
        report = (directory / "integration_report.md").read_text(encoding="utf-8")
        import re
        displayed = re.sub(r"!\[[^\]]*\]\([^)]+\)", "", report)
        displayed = re.sub(r"\[([^\]]+)\]\((?!https?://)[^)]+\)", r"`\1`", displayed)
        st.markdown(displayed)
        for filename in ("integration_report.md", "report.md", "results.json", "analysis.FCStd", "verification.json", "execution.json",
                         "gmsh.log", "calculix.log", "solver/Mesh.inp", "solver/Mesh.frd", "solver/Mesh.dat", *result.image_paths):
            path = directory / filename
            if path.is_file():
                st.download_button("Download " + filename, path.read_bytes(), file_name=filename, key="fem-download-" + filename)
        with st.expander("Solver logs"):
            for filename in ("gmsh.log", "calculix.log"):
                path = directory / filename
                if path.is_file(): st.code(path.read_text(encoding="utf-8"))
        if st.button("Prepare another analysis"):
            from workflow import Workflow
            Workflow(store).transition(project_id, S.ANALYSIS_INTAKE, expected_version=project["row_version"], reason="User requested a new analysis setup")
            st.rerun()
        return
    if jobs and jobs[-1].error:
        st.error(jobs[-1].error)
        if st.button("Review analysis inputs again"):
            edit_analysis_inputs(store,project_id,expected_version=project["row_version"])
            st.rerun()

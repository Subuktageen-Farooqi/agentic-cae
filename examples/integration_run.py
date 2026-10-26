"""Real end-to-end Streamlit/CadQuery/FreeCAD/Gmsh/CalculiX verification.

AppTest drives actual app controls. No provider, mesher, worker or solver is
patched. Only the data directory is scoped; this uses trusted reference CAD,
not an LLM-generated script or a generated-code sandbox test.
"""
from __future__ import annotations
import json
import os
from pathlib import Path
import time
from unittest.mock import patch

from config import Config
from schemas import JobStatus, WorkflowState as S
from storage import Store
from workers.fem_worker import availability


def run(data_dir):
    from streamlit.testing.v1 import AppTest
    config = Config.from_env()
    present, reason = availability(config.freecad_cmd, config.calculix_exe, config.gmsh_exe)
    if not present:
        raise RuntimeError("Real integration is BLOCKED: " + reason)
    root = Path(data_dir).resolve()
    with patch.dict(os.environ, {"CAE_DATA_DIR": str(root)}):
        app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=30)
        actions = []
        def healthy():
            if app.exception:
                raise AssertionError("App exception: " + str([e.message for e in app.exception]))
        def click(label, timeout=30):
            button = next(b for b in app.button if b.label == label)
            button.click().run(timeout=timeout)
            actions.append(label)
            healthy()
        healthy()
        click("Generate reference cantilever", 60)
        project_id = app.session_state["project_id"]
        store = Store(root)
        assert store.project(project_id)["state"] == S.DESIGN_REVIEW
        assert len(app.get("plotly_chart")) >= 1, "Actual STL must be displayed"
        click("Accept design")
        click("Use the reference cantilever setup")
        click("Prepare actual analysis regions")
        def wait_for_job(kind):
            deadline = time.monotonic() + config.worker_timeout_seconds + 60
            while time.monotonic() < deadline:
                jobs = [j for j in store.jobs(project_id) if j.kind == kind]
                if jobs and jobs[-1].status not in (JobStatus.PENDING, JobStatus.RUNNING):
                    assert jobs[-1].status == JobStatus.SUCCEEDED, jobs[-1].error
                    app.run(timeout=30); healthy()
                    return jobs[-1]
                time.sleep(.2)
                app.run(timeout=30); healthy()
            raise TimeoutError("Real integration timed out waiting for " + kind)
        prepare_job = wait_for_job("FEM_PREPARE")
        assert any(h.value == "Review the actual analysis setup" for h in app.header)
        assert len(app.get("plotly_chart")) >= 1, "Actual selected faces must be displayed"
        next(c for c in app.checkbox if c.label.startswith("I confirm this material")).check().run(timeout=30)
        click("Confirm setup and run FreeCAD FEM")
        solve_job = wait_for_job("FEM_SOLVE")
        assert store.project(project_id)["state"] == S.REPORT_READY
        result = store.record(project_id, "AnalysisResults", solve_job.result["run_id"], 1)
        manifest = store.record(project_id, "ArtifactManifest", solve_job.result["manifest_id"], 1)
        assert manifest.job_id == solve_job.job_id
        assert result.provenance == "actual_solver" and result.status == "succeeded"
        directory = store.path(solve_job.result["artifact_directory"])
        checks = json.loads((directory / "verification.json").read_text(encoding="utf-8"))
        assert checks["beam_applicable"] and checks["displacement_relative_difference"] < .12
        assert checks["reaction_relative_residual"] < 1e-4
        metrics = {m.label: m.value for m in app.metric}
        assert metrics["Maximum displacement (mm)"] == f"{result.maximum_displacement_mm:.8f}"
        assert metrics["Maximum von Mises stress (MPa)"] == f"{result.maximum_von_mises_mpa:.6f}"
        assert len(app.get("plotly_chart")) >= 2
        assert any("# Engineering analysis report" in m.value for m in app.markdown)
        evidence = {"project_id": project_id, "analysis_id": result.analysis_id,
            "result_provenance": result.provenance, "cad_source": "repository-authored CadQuery reference generator",
            "mocked_components": [], "app_actions": actions, "app_metrics": metrics,
            "displayed_result_charts": len(app.get("plotly_chart")), "checks": checks,
            "report": str(directory / "integration_report.md"), "directory": str(directory)}
        store.write_once(solve_job.result["artifact_directory"] + "/app_evidence.json", json.dumps(evidence, indent=2).encode())
        # Reopening the actual persisted session must display the same run,
        # never enqueue another mesh or solve.
        before = len(store.jobs(project_id))
        reopened = AppTest.from_file(Path(__file__).parents[1] / "app.py")
        reopened.session_state["project_id"] = project_id
        reopened.run(timeout=30)
        assert not reopened.exception and len(store.jobs(project_id)) == before
        assert any(h.value == "FreeCAD FEM results" for h in reopened.header)
        return evidence

from streamlit.testing.v1 import AppTest
from pathlib import Path
import shutil


def _new_app(monkeypatch, tmp_path):
    data = tmp_path / "app-data"
    shutil.copytree(Path(__file__).parents[1] / "data" / "knowledge", data / "knowledge")
    monkeypatch.setenv("CAE_DATA_DIR", str(data))
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=10)
    assert not app.exception
    return app


def _submit_minimal_intake(app):
    app.text_area[0].input("A small sensor mounting bracket")
    app.button(key="FormSubmitter:intake-Save idea and continue").click().run(timeout=10)
    assert not app.exception
    assert any(header.value == "Choose how to continue" for header in app.header)
    assert "Brainstorm with our AI Mechanical Engineering Maestro" in [item.value for item in app.subheader]
    assert "Design it for me—I trust your judgment" in [item.value for item in app.subheader]
    return app


def test_automatic_route_persists_incomplete_intake_and_enters_spec_state(monkeypatch, tmp_path):
    app = _submit_minimal_intake(_new_app(monkeypatch, tmp_path))
    next(item for item in app.button if item.label == "Draft automatically").click().run(timeout=10)
    assert not app.exception
    assert any(header.value == "Specification generation" for header in app.header)
    assert any("Specification generation is blocked" in warning.value for warning in app.warning)
    assert "Dimensions will be inferred" in str(app.json[0].value)


def test_advisor_route_opens_shared_editable_brief_with_honest_blocked_notice(monkeypatch, tmp_path):
    app = _submit_minimal_intake(_new_app(monkeypatch, tmp_path))
    next(item for item in app.button if item.label == "Open engineering advisor").click().run(timeout=10)
    assert not app.exception
    assert "Engineering advisor" in [item.value for item in app.subheader]
    assert "Living design brief" in [item.value for item in app.subheader]
    assert any("Gemini is blocked" in notice.value for notice in app.warning)
    assert any(item.label == "Generate this design" for item in app.button)


def test_blocked_vertex_route_still_returns_cited_local_evidence(monkeypatch, tmp_path):
    data = tmp_path / "app-data"
    shutil.copytree(Path(__file__).parents[1] / "data" / "knowledge", data / "knowledge")
    monkeypatch.setenv("CAE_DATA_DIR", str(data))
    app = AppTest.from_file(Path(__file__).parents[1] / "app.py").run(timeout=10)
    # Use a fresh project even when the repository data directory contains prior demos.
    app.text_area[0].input("A serviceable mounting bracket")
    app.button(key="FormSubmitter:intake-Save idea and continue").click().run(timeout=10)
    next(item for item in app.button if item.label == "Open engineering advisor").click().run(timeout=10)
    app.chat_input[0].set_value("What joint and fastener trade-offs affect disassembly?").run(timeout=10)
    assert not app.exception
    assistant_messages = [item for item in app.chat_message if item.name == "assistant"]
    assert assistant_messages
    assert "Local retrieved evidence" in assistant_messages[-1].children[0].value
    assert any(expander.label == "Sources" for expander in app.expander)


def test_advisor_resends_persisted_intake_images_after_reopen(monkeypatch, tmp_path, png_bytes):
    import json
    from schemas import DesignBrief, Intake, WorkflowState
    from storage import Store, Upload
    from workflow import Workflow
    calls = []
    class Provider:
        def __init__(self, config): pass
        def availability_issues(self): return []
        def generate(self, **kwargs):
            calls.append(kwargs)
            return json.dumps({"text": "I received the reference.", "source_chunk_ids": []})
    app = _new_app(monkeypatch, tmp_path)
    store = Store(tmp_path / "app-data")
    project = store.create_project(Intake(idea="Bracket"), [Upload("reference.png", "image/png", png_bytes)])
    ids = store.original_intake(project).reference_image_ids
    flow = Workflow(store)
    flow.transition(project, WorkflowState.ROUTE_SELECTION, expected_version=0, reason="test")
    store.save_brief(project, DesignBrief(design_name="Bracket", reference_image_ids=ids),
                     expected_version=0, actor="test", reason="test")
    flow.transition(project, WorkflowState.ADVISOR_CHAT, expected_version=2, route="advisor", reason="test")
    monkeypatch.setattr("providers.vertex.VertexGeminiProvider", Provider)
    app.session_state["project_id"] = project
    app.run(timeout=10)
    app.chat_input[0].set_value("What can you see in my intake reference?").run(timeout=10)
    assert not app.exception
    assert calls[-1]["images"][0].data == png_bytes
    assert calls[-1]["images"][0].image_id == ids[0]


def test_automatic_generation_persists_spec_and_displays_blocked_job_without_rerunning(monkeypatch, tmp_path):
    import json
    from schemas import DesignBrief, DesignSpec, Dimension, Feature
    from workers.runtime import SandboxUnavailable
    from generation import start_generation as real_start
    calls = []
    class Provider:
        def __init__(self, config): pass
        def availability_issues(self): return []
        def generate(self, **kwargs):
            payload = json.loads(kwargs["prompt"])
            calls.append(payload)
            if "frozen_brief" in payload:
                brief = DesignBrief.model_validate(payload["frozen_brief"])
                return DesignSpec(brief_id=brief.brief_id, brief_version=brief.version,
                    design_name=brief.design_name, purpose="Mount a sensor", units="mm",
                    dimensions=[Dimension(name="length", value=100, unit="mm", origin="inferred")],
                    features=[Feature(feature_id="beam", kind="extrusion", description="Supported beam", parameter_names=["length"])],
                    assumptions=["Concept dimensions inferred"]).model_dump_json()
            return json.dumps({"code": "def build(params):\n return cq.Workplane('XY').box(params['length'], 20, 10)",
                               "explanation": "Provider double for blocked job test"})
    class Immediate:
        def submit(self, function, **kwargs): return function(**kwargs)
    def start(**kwargs): return real_start(**{**kwargs, "executor": Immediate()})
    def blocked(**kwargs): raise SandboxUnavailable("Container engine is missing")
    monkeypatch.setattr("providers.vertex.VertexGeminiProvider", Provider)
    monkeypatch.setattr("generation.start_generation", start)
    monkeypatch.setattr("generation.execute_generated", blocked)
    app = _submit_minimal_intake(_new_app(monkeypatch, tmp_path))
    next(b for b in app.button if b.label == "Draft automatically").click().run(timeout=10)
    assert not app.exception
    assert any("Container engine is missing" in item.value for item in app.error)
    assert len(calls) == 2
    app.run(timeout=10)
    assert not app.exception and len(calls) == 2
    assert any(b.label == "Download design_spec.json" for b in app.get("download_button"))

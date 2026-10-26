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
    assert any("real Vertex specification writer is not implemented" in warning.value for warning in app.warning)
    assert "Dimensions will be inferred" in str(app.json[0].value)


def test_advisor_route_opens_shared_editable_brief_with_honest_blocked_notice(monkeypatch, tmp_path):
    app = _submit_minimal_intake(_new_app(monkeypatch, tmp_path))
    next(item for item in app.button if item.label == "Open engineering advisor").click().run(timeout=10)
    assert not app.exception
    assert "Engineering advisor" in [item.value for item in app.subheader]
    assert "Living design brief" in [item.value for item in app.subheader]
    assert any("Vertex Gemini is blocked" in notice.value for notice in app.warning)
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

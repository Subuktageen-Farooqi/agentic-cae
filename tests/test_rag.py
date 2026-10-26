import json
from pathlib import Path

import pytest

from agents.advisor import (AdvisorReply, BriefUpdates, accept_choice, advise, apply_reply_to_brief,
                            explicit_dimension_edit, grounded_local_fallback, should_retrieve)
from config import Config
from providers.vertex import ImagePayload, ProviderUnavailable, VertexGeminiProvider
from rag.ingest import build_index, chunk_document
from rag.retriever import LocalHybridRetriever
from rag.sources import load_collection
from schemas import ChatMessage, DesignBrief, Dimension, Requirement


KNOWLEDGE = Path(__file__).parents[1] / "data" / "knowledge"


@pytest.fixture
def index(tmp_path):
    path = tmp_path / "index.json"
    value = build_index(KNOWLEDGE, path)
    return path, value


def test_actual_authored_sources_have_complete_honest_provenance_and_topic_coverage():
    documents = load_collection(KNOWLEDGE)
    assert len(documents) == 4
    assert all(item.reference.source_kind == "authored_seed_note" for item in documents)
    assert all(item.reference.reference.startswith("sources/") for item in documents)
    topics = {topic for document in documents for topic in document.reference.topic}
    expected = {"mechanisms", "degrees of freedom", "constraints", "joints", "fasteners",
                "bearings", "linear guides", "engineering structures", "load paths", "materials",
                "CNC machining", "laser cutting", "waterjet cutting", "additive manufacturing",
                "weldments", "joining", "assembly", "disassembly", "design for manufacturing",
                "design examples"}
    assert expected <= topics


def test_ingestion_chunks_indexes_and_persists_repeatably(index, tmp_path):
    path, value = index
    assert value["source_count"] == 4 and value["chunk_count"] >= 10
    assert value["embedding"] == "local_tfidf_v1" and value["lexical"] == "bm25_v1"
    reloaded = json.loads(path.read_text(encoding="utf-8"))
    assert reloaded["source_hash"] == value["source_hash"]
    other = build_index(KNOWLEDGE, tmp_path / "other.json")
    assert [item["reference"]["chunk_id"] for item in other["chunks"]] == [
        item["reference"]["chunk_id"] for item in value["chunks"]]


def test_retrieves_relevant_passage_with_source_context(index):
    retriever = LocalHybridRetriever(index[0])
    hits = retriever.search("Should this flat bracket be waterjet or CNC machined?")
    assert hits and hits[0].reference.source_id == "seed-materials-manufacturing"
    assert "waterjet" in hits[0].text.casefold()
    assert hits[0].reference.equipment_context and hits[0].reference.supplier_context
    assert hits[0].semantic_score > 0 and hits[0].lexical_score > 0


def test_insufficient_evidence_is_honest(index):
    hits = LocalHybridRetriever(index[0]).search("quantum chromodynamic color confinement")
    reply = grounded_local_fallback("unrelated", hits)
    assert hits == [] and "does not contain enough evidence" in reply.text
    assert reply.sources == [] and reply.mode == "local_retrieval_only"


def test_local_grounded_recommendation_cites_actual_chunks(index):
    hits = LocalHybridRetriever(index[0]).search("How should I plan fastener access for disassembly?")
    reply = grounded_local_fallback("question", hits)
    assert reply.sources
    assert all(source.chunk_id in reply.text for source in reply.sources)
    assert "Vertex advisor unavailable" in reply.text


def test_simple_dimension_edit_skips_retrieval_but_engineering_decision_uses_it():
    assert not should_retrieve("Change length to 120 mm")
    assert should_retrieve("Should I use a welded joint or fasteners?")


class FakeProvider:
    def __init__(self, source_id):
        self.source_id = source_id
        self.prompt = None
        self.images = None

    def generate(self, *, system_instruction, prompt, images=()):
        self.prompt, self.images = prompt, images
        return json.dumps({"text": "Consider tool access and service needs.",
                           "questions": ["Must the joint be removable?"],
                           "proposed_choices": ["Use a removable bolted joint"],
                           "visual_observations": [], "source_chunk_ids": [self.source_id, "invented-id"]})


def test_advisor_reads_brief_history_images_and_only_accepts_real_citations(index):
    retriever = LocalHybridRetriever(index[0])
    hit = retriever.search("fastener joint assembly access")[0]
    provider = FakeProvider(hit.reference.chunk_id)
    image = ImagePayload(data=b"real bytes", media_type="image/png", role="desired_reference", image_id="img")
    reply = advise(provider=provider, retriever=retriever, brief=DesignBrief(design_name="Bracket"),
                   history=[ChatMessage(role="user", text="It must be serviceable")],
                   message="What joint and fastener trade-offs matter?", images=[image])
    prompt = json.loads(provider.prompt)
    assert prompt["current_brief"]["design_name"] == "Bracket"
    assert prompt["recent_conversation"][0]["text"] == "It must be serviceable"
    assert provider.images == [image]
    assert [item.chunk_id for item in reply.sources] == [hit.reference.chunk_id]


def test_reply_updates_shared_versioned_brief_and_choice_acceptance(index):
    hit = LocalHybridRetriever(index[0]).search("joint fastener service access")[0]
    reply = grounded_local_fallback("question", [hit]).model_copy(
        update={"proposed_choices": ["Use a removable bolted joint"]})
    original = DesignBrief(design_name="Bracket")
    updated = apply_reply_to_brief(original, reply)
    assert updated.version == 2 and updated.proposed_choices and updated.supporting_sources
    accepted = accept_choice(updated, updated.proposed_choices[0].decision_id)
    assert accepted.version == 3 and accepted.accepted_decisions[0].status == "accepted"
    assert accepted.proposed_choices == [] and original.version == 1


def test_vertex_adapter_is_explicitly_blocked_without_configuration():
    provider = VertexGeminiProvider(Config.from_env({}))
    with pytest.raises(ProviderUnavailable, match="GOOGLE_CLOUD_PROJECT"):
        provider.generate(system_instruction="test", prompt="test")


def test_vertex_adapter_builds_actual_inline_byte_part_without_filename_only():
    provider = VertexGeminiProvider(Config.from_env({}))
    image = ImagePayload(data=b"\x89PNG\r\nactual-content", media_type="image/png",
                         role="desired_reference", image_id="image-1")
    parts = provider._contents("Inspect it", [image])
    assert parts[-1].inline_data.data == image.data
    assert parts[-1].inline_data.mime_type == "image/png"
    assert "desired_reference" in parts[-2].text


def test_explicit_dimension_edit_changes_only_requested_dimension_without_model():
    brief = DesignBrief(design_name="Beam", dimensions=[
        Dimension(name="length", value=100, unit="mm", origin="user_provided"),
        Dimension(name="width", value=20, unit="mm", origin="inferred")],
        hard_requirements=[Requirement(requirement_id="H1", text="One solid", confirmed=True)])
    reply = explicit_dimension_edit(brief, "Change length to 120 mm")
    updated = apply_reply_to_brief(brief, reply)
    assert updated.dimensions[0].value == 120 and updated.dimensions[1] == brief.dimensions[1]
    assert updated.hard_requirements == brief.hard_requirements and updated.version == brief.version + 1
    assert brief.dimensions[0].value == 100


def test_structured_advisor_edits_preserve_requirements_and_resolve_questions():
    brief = DesignBrief(design_name="Beam", unresolved_questions=["Which material?"],
                        hard_requirements=[Requirement(requirement_id="H1", text="Keep interface")])
    reply = AdvisorReply(text="Updated the user-specified material.",
                         brief_updates=BriefUpdates(materials=["Aluminum"], unresolved_questions=[]))
    updated = apply_reply_to_brief(brief, reply)
    assert updated.materials == ["Aluminum"] and updated.unresolved_questions == []
    assert updated.hard_requirements == brief.hard_requirements


def test_vertex_client_initialization_failure_is_provider_unavailable(monkeypatch):
    from google import genai
    def fail(**kwargs):
        raise RuntimeError("ADC initialization failed")
    monkeypatch.setattr(genai, "Client", fail)
    provider = VertexGeminiProvider(Config.from_env({"GOOGLE_CLOUD_PROJECT": "test",
        "GOOGLE_CLOUD_LOCATION": "global", "GEMINI_MODEL_ID": "test"}))
    with pytest.raises(ProviderUnavailable, match="ADC initialization failed"):
        provider.generate(system_instruction="test", prompt="test")

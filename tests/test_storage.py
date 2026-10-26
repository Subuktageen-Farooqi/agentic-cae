from concurrent.futures import ThreadPoolExecutor
import hashlib
import sqlite3

import pytest
from pydantic import ValidationError

from schemas import Artifact, ArtifactManifest, ChatMessage, DesignBrief, Intake, JobStatus
from storage import ConflictError, IntegrityError, Store, Upload


def test_intake_and_actual_image_survive_store_restart(store, project, png_bytes):
    reopened = Store(store.root)
    original = reopened.original_intake(project)
    image = reopened.images(project)[0]
    assert original.idea == "A support arm"
    assert original.reference_image_ids == [image.image_id]
    assert reopened.read_image(project, image.image_id) == png_bytes
    assert image.role == "desired_reference"
    assert image.sha256 == hashlib.sha256(png_bytes).hexdigest()
    assert image.size_bytes == len(png_bytes)


@pytest.mark.parametrize("sql", [
    "UPDATE projects SET original_intake='{}'",
    "UPDATE images SET json='{}'", "DELETE FROM images",
    "UPDATE events SET payload='{}'", "DELETE FROM events",
])
def test_database_enforces_immutable_original_images_and_audit(store, project, sql):
    with sqlite3.connect(store.database) as db:
        with pytest.raises(sqlite3.IntegrityError, match="immutable"):
            db.execute(sql)


def test_partial_file_failure_rolls_back_project_and_image_index(store, png_bytes, monkeypatch):
    original_write = store.write_once

    def fail_intake(relative, data):
        if relative.endswith("intake.json"):
            raise OSError("Simulated full disk")
        return original_write(relative, data)

    monkeypatch.setattr(store, "write_once", fail_intake)
    with pytest.raises(OSError, match="full disk"):
        store.create_project(Intake(idea="Arm"), [Upload("ref.png", "image/png", png_bytes)])
    assert store.projects() == []
    with sqlite3.connect(store.database) as db:
        assert db.execute("SELECT COUNT(*) FROM images").fetchone()[0] == 0
    # A fully written, unreferenced file may remain; it is not indexed as a project.


def test_invalid_image_does_not_create_project(store):
    with pytest.raises(ValueError):
        store.create_project(Intake(idea="Arm"), [Upload("ref.svg", "image/svg+xml", b"<svg/>")])
    assert store.projects() == []


def test_empty_image_rejected(store, project):
    with pytest.raises(ValidationError):
        store.save_image(project, Upload("empty.png", "image/png", b""))
    assert len(store.images(project)) == 1


def test_brief_versions_do_not_mutate_original_or_approved_snapshot(store, project, brief):
    attempt = store.create_attempt(project, brief.version)
    changed = brief.model_copy(update={"version": 2, "description": "User edited description"})
    store.save_brief(project, changed, expected_version=1, actor="user", reason="Refined description")
    reopened = Store(store.root)
    assert reopened.brief(project).description == "User edited description"
    assert reopened.brief(project, attempt["brief_version"]).description == "A simple connected part"
    assert reopened.original_intake(project).idea == "A support arm"
    assert len([event for event in reopened.events(project) if event["kind"] == "brief_saved"]) == 2


def test_stale_llm_brief_cannot_overwrite_direct_edit(store, project, brief):
    update = brief.model_copy(update={"version": 2, "purpose": "Edited by user"})
    store.save_brief(project, update, expected_version=1, actor="user", reason="Explicit purpose")
    stale = brief.model_copy(update={"version": 2, "purpose": "Stale model response"})
    with pytest.raises(ConflictError, match="Stale brief"):
        store.save_brief(project, stale, expected_version=1, actor="advisor", reason="Earlier response")
    assert store.brief(project).purpose == "Edited by user"


def test_competing_brief_edits_only_commit_once(store, project, brief):
    def save(label):
        try:
            store.save_brief(project, brief.model_copy(update={"version": 2, "purpose": label}),
                             expected_version=1, actor=label, reason="Concurrent edit")
            return True
        except ConflictError:
            return False

    with ThreadPoolExecutor(max_workers=2) as executor:
        assert sum(executor.map(save, ["user", "advisor"])) == 1
    assert store.project(project)["brief_version"] == 2


def test_brief_validation_cannot_be_bypassed_by_model_copy_or_generic_save(store, project, brief):
    bad = brief.model_copy(update={"version": 2, "design_name": ""})
    with pytest.raises(ValidationError):
        store.save_brief(project, bad, expected_version=1, actor="advisor", reason="Invalid response")
    with pytest.raises(ValueError, match="optimistic"):
        store.save_record(project, "brief", 2, brief)
    with pytest.raises(ValueError):
        store.save_brief(project, brief.model_copy(update={"version": 2, "reference_image_ids": ["other-project"]}),
                         expected_version=1, actor="user", reason="Wrong image")


@pytest.mark.parametrize("relative", ["../secret", "/absolute", "C:/secret", "x/../../secret", "x\\..\\secret", "x//file", "x/./file"])
def test_path_traversal_and_absolute_paths_rejected(store, relative):
    with pytest.raises(ValueError):
        store.write_once(relative, b"should not be written")


def test_artifacts_cannot_be_overwritten(store):
    path = store.write_once("projects/example/model.step", b"first")
    with pytest.raises(FileExistsError):
        store.write_once("projects/example/model.step", b"replacement")
    assert path.read_bytes() == b"first"
    assert not list(path.parent.glob(".pending-*"))


def test_image_tampering_and_missing_files_detected(store, project):
    image = store.images(project)[0]
    path = store.path(image.relative_path)
    path.write_bytes(b"tampered")
    with pytest.raises(IntegrityError, match="integrity"):
        store.read_image(project, image.image_id)
    path.unlink()
    with pytest.raises(IntegrityError, match="Missing"):
        store.read_image(project, image.image_id)


def test_original_intake_file_tampering_is_detected(store, project):
    path = store.path(f"projects/{project}/intake/intake.json")
    path.write_text(Intake(idea="Tampered idea").model_dump_json(), encoding="utf-8")
    with pytest.raises(IntegrityError):
        store.original_intake(project)


def test_manifest_requires_existing_intact_artifacts_and_expected_roles(store, project):
    data = b"Contract fixture, NOT real STEP geometry"
    relative = f"projects/{project}/attempts/a/revisions/r/model.step"
    artifact = Artifact(relative_path=relative, sha256=hashlib.sha256(data).hexdigest(),
                        size_bytes=len(data), media_type="application/step", role="geometry")
    manifest = ArtifactManifest(project_id=project, job_id="fixture-job", stage="fixture",
                                completed=True, artifacts=[artifact])
    with pytest.raises(IntegrityError, match="Missing artifact"):
        store.verify_manifest(manifest)
    store.write_once(relative, data)
    store.verify_manifest(manifest, required_roles=["geometry"])
    with pytest.raises(IntegrityError, match="expected artifact roles"):
        store.verify_manifest(manifest, required_roles=["fcstd"])
    store.path(relative).write_bytes(b"Changed")
    with pytest.raises(IntegrityError, match="integrity"):
        store.verify_manifest(manifest)


def test_manifest_cannot_use_another_projects_artifacts(store, project):
    artifact = Artifact(relative_path="projects/another/model.step", sha256="a" * 64,
                        size_bytes=1, media_type="application/step", role="geometry")
    with pytest.raises(IntegrityError, match="different project"):
        store.verify_manifest(ArtifactManifest(project_id=project, job_id="j", stage="CAD",
                                               completed=True, artifacts=[artifact]))


def test_versioned_records_are_append_only_and_reload_after_restart(store, project):
    message = ChatMessage(role="user", text="Use a single part", image_ids=store.original_intake(project).reference_image_ids)
    store.save_record(project, message.message_id, 1, message)
    assert Store(store.root).record(project, "ChatMessage", message.message_id, 1) == message
    assert Store(store.root).records(project, "ChatMessage") == [message]
    with pytest.raises(ConflictError):
        store.save_record(project, message.message_id, 1, message.model_copy(update={"text": "Overwrite"}))
    with sqlite3.connect(store.database) as db:
        with pytest.raises(sqlite3.IntegrityError):
            db.execute("DELETE FROM records")


def test_attempt_revisions_have_unique_folders_and_two_candidate_limit(store, project, brief):
    a1 = store.create_attempt(project, 1)
    a2 = store.create_attempt(project, 1)
    r1 = store.create_revision(a1["attempt_id"])
    r2 = store.create_revision(a1["attempt_id"])
    r3 = store.create_revision(a2["attempt_id"])
    assert len({r["relative_path"] for r in (r1, r2, r3)}) == 3
    assert all(store.path(r["relative_path"]).is_dir() for r in (r1, r2, r3))
    with pytest.raises(ConflictError, match="two"):
        store.create_revision(a1["attempt_id"])
    assert a2["user_rejections"] == 0


def test_reruns_reuse_job_and_reject_different_inputs(store, project):
    first = store.enqueue(project, "spec:v1", "spec", {"brief": 1, "images": []})
    same = store.enqueue(project, "spec:v1", "spec", {"images": [], "brief": 1})
    assert first.job_id == same.job_id
    assert len(store.jobs(project)) == 1
    with pytest.raises(ConflictError):
        store.enqueue(project, "spec:v1", "spec", {"brief": 2})
    with pytest.raises(ConflictError):
        store.enqueue(project, "spec:v1", "solver", {"brief": 1, "images": []})


def test_only_one_concurrent_worker_claims_job(store, project):
    job = store.enqueue(project, "cad:r1", "CAD", {})
    with ThreadPoolExecutor(max_workers=8) as executor:
        claims = list(executor.map(lambda n: store.claim(job.job_id, f"worker-{n}"), range(8)))
    assert sum(claim is not None for claim in claims) == 1
    assert store.job(job.job_id).status == JobStatus.RUNNING


def test_job_completion_requires_current_owner_and_error_evidence(store, project):
    job = store.enqueue(project, "solver:v1", "solver", {})
    store.claim(job.job_id, "worker")
    with pytest.raises(ConflictError):
        store.finish(job.job_id, "other", JobStatus.SUCCEEDED)
    with pytest.raises(ValueError):
        store.finish(job.job_id, "worker", JobStatus.BLOCKED)
    done = store.finish(job.job_id, "worker", JobStatus.BLOCKED, error="Mechanical executable not found")
    assert done.status == JobStatus.BLOCKED and "not found" in done.error
    assert store.enqueue(project, "solver:v1", "solver", {}).job_id == job.job_id
    assert store.claim(job.job_id, "worker") is None


def test_restart_never_requeues_running_work_and_recovery_is_explicit_and_scoped(store, project):
    first = store.enqueue(project, "LLM:v1", "LLM", {})
    second = store.enqueue(project, "CAD:v1", "CAD", {})
    store.claim(first.job_id, "stopped-owner")
    store.claim(second.job_id, "active-owner")
    reopened = Store(store.root)
    assert reopened.job(first.job_id).status == JobStatus.RUNNING
    assert reopened.claim(first.job_id, "new-owner") is None
    assert reopened.recover_interrupted("stopped-owner") == [first.job_id]
    assert reopened.job(first.job_id).status == JobStatus.INTERRUPTED
    assert reopened.job(second.job_id).status == JobStatus.RUNNING
    assert reopened.enqueue(project, "LLM:v1", "LLM", {}).status == JobStatus.INTERRUPTED
    assert reopened.claim(first.job_id, "new-owner") is None
    retry = reopened.enqueue(project, "LLM:v1:explicit-retry-1", "LLM", {})
    assert retry.job_id != first.job_id
    assert reopened.claim(retry.job_id, "new-owner").status == JobStatus.RUNNING


def test_unknown_database_version_is_not_silently_modified(tmp_path):
    root = tmp_path / "future-data"
    root.mkdir()
    with sqlite3.connect(root / "workflow.sqlite3") as db:
        db.execute("PRAGMA user_version=999")
    with pytest.raises(RuntimeError, match="Unsupported"):
        Store(root)

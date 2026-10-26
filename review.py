"""Artifact-bound design review, bounded user revisions and preserved restarts."""
from __future__ import annotations

from app_logic import draft_brief
from rules.geometry import core_geometry_rules, mandatory_geometry_passes
from schemas import (ChatMessage, DesignAcceptance, DesignBrief, DesignFeedback, DesignReview,
                     RestartDecision, WorkflowState as S, new_id, utc_now)
from storage import ConflictError, IntegrityError, Store


def current_review(store: Store, project_id: str) -> DesignReview:
    attempt = store.project(project_id)["active_attempt_id"]
    reviews = [r for r in store.records(project_id, "DesignReview") if r.attempt_id == attempt]
    if not reviews:
        raise ValueError("No checked geometry is available for the current attempt")
    return reviews[-1]


def review_artifacts(store: Store, project_id: str, review: DesignReview) -> dict:
    revision = store.revision(review.revision_id)
    if revision["project_id"] != project_id or revision["attempt_id"] != review.attempt_id:
        raise IntegrityError("Review does not belong to this project/attempt")
    cad = store.record(project_id, "ArtifactManifest", review.cad_manifest_id, 1)
    imported = store.record(project_id, "ArtifactManifest", review.freecad_manifest_id, 1)
    store.verify_manifest(cad, ["step", "preview", "model_source", "parameters"])
    store.verify_manifest(imported, ["fcstd", "freecad_metrics"])
    metrics = [m for m in store.records(project_id, "GeometryMetrics") if m.revision_id == review.revision_id][-1]
    if metrics.geometry_hash != review.geometry_hash:
        raise IntegrityError("Review geometry differs from imported geometry")
    required = {r.rule_id for r in core_geometry_rules(metrics)}
    if not required.issubset({c.rule_id for c in review.checks}) or not mandatory_geometry_passes(review.checks + core_geometry_rules(metrics)):
        raise ValueError("Implemented mandatory geometry checks did not pass")
    step = next(a for a in cad.artifacts if a.role == "step")
    if step.sha256 != review.geometry_hash:
        raise IntegrityError("Review is not bound to the actual STEP artifact")
    return {"cad": cad, "freecad": imported, "metrics": metrics, "step": step,
            "spec": store.record(project_id, "DesignSpec", review.spec_id, review.spec_version)}


def _checked_action(store, db, project_id, expected_version, review):
    project = store._project_row(db, project_id)
    if project["row_version"] != expected_version or project["state"] != S.DESIGN_REVIEW:
        raise ConflictError("Stale design action; reload the current checked revision")
    if project["active_attempt_id"] != review.attempt_id:
        raise ConflictError("This attempt is no longer current")
    latest = db.execute("SELECT revision_id FROM revisions WHERE attempt_id=? ORDER BY ordinal DESC LIMIT 1",
                        (review.attempt_id,)).fetchone()
    attempt = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (review.attempt_id,)).fetchone()
    if latest[0] != review.revision_id or attempt["status"] != "active":
        raise ConflictError("Only the current active candidate can be reviewed")
    return attempt


def _state(store, db, project_id, target, reason):
    current = store._project_row(db, project_id)["state"]
    db.execute("UPDATE projects SET state=?,resume_state=NULL,row_version=row_version+1 WHERE project_id=?", (target, project_id))
    store._event(db, project_id, "state_transition", {"from": current, "to": target, "reason": reason})


def accept_design(store: Store, project_id: str, *, expected_version: int, revision_id: str,
                  geometry_hash: str) -> DesignAcceptance:
    review = current_review(store, project_id)
    artifacts = review_artifacts(store, project_id, review)
    if (revision_id, geometry_hash) != (review.revision_id, review.geometry_hash):
        raise ConflictError("Acceptance must bind to the exact displayed revision and STEP hash")
    accepted = DesignAcceptance(attempt_id=review.attempt_id, revision_id=revision_id,
        geometry_hash=geometry_hash, step_relative_path=artifacts["step"].relative_path,
        cad_manifest_id=review.cad_manifest_id)
    feedback = DesignFeedback(attempt_id=review.attempt_id, revision_id=revision_id, action="accept", thumbs="up")
    with store._connection(write=True) as db:
        _checked_action(store, db, project_id, expected_version, review)
        store._insert_record(db, project_id, accepted.acceptance_id, 1, accepted)
        store._insert_record(db, project_id, feedback.feedback_id, 1, feedback)
        db.execute("UPDATE attempts SET status='accepted' WHERE attempt_id=?", (review.attempt_id,))
        db.execute("UPDATE projects SET accepted_revision_id=?,accepted_geometry_hash=? WHERE project_id=?",
                   (revision_id, geometry_hash, project_id))
        _state(store, db, project_id, S.ANALYSIS_INTAKE, "User accepted this exact checked design; engineering analysis has not run")
    return accepted


def reject_design(store: Store, project_id: str, feedback: DesignFeedback, *, expected_version: int):
    feedback = DesignFeedback.model_validate_json(feedback.model_dump_json())
    review = current_review(store, project_id)
    review_artifacts(store, project_id, review)
    if feedback.action != "revise" or (feedback.attempt_id, feedback.revision_id) != (review.attempt_id, review.revision_id):
        raise ValueError("Revision feedback must refer to the displayed candidate")
    if not set(feedback.reference_image_ids).issubset({i.image_id for i in store.images(project_id)}):
        raise ValueError("Feedback images must be persisted in this project")
    with store._connection(write=True) as db:
        attempt = _checked_action(store, db, project_id, expected_version, review)
        if attempt["user_rejections"] >= 2:
            raise ConflictError("User revision budget exhausted")
        count = attempt["user_rejections"] + 1
        store._insert_record(db, project_id, feedback.feedback_id, 1, feedback)
        db.execute("UPDATE attempts SET user_rejections=?,status=? WHERE attempt_id=?",
                   (count, "failed" if count == 2 else "active", review.attempt_id))
        store._event(db, project_id, "design_rejected", {"feedback_id": feedback.feedback_id, "rejection": count})
        if count == 2:
            _state(store, db, project_id, S.RESTART_OFFER, "Second user rejection; both candidates and all feedback retained")
            return None
        _state(store, db, project_id, S.SPEC_GENERATION, "First user rejection; regenerate once using saved feedback")
        brief = store.brief(project_id, review.brief_version)
        return store._enqueue(db, project_id, "feedback:" + feedback.feedback_id, "DESIGN_GENERATION",
            {"brief_id": brief.brief_id, "brief_version": brief.version, "attempt_id": review.attempt_id,
             "previous_revision_id": review.revision_id, "feedback_id": feedback.feedback_id})


def restart_attempt(store: Store, project_id: str, choice: str, *, expected_version: int) -> RestartDecision:
    if choice not in ("approved_brief", "brainstorm", "original_idea"):
        raise ValueError("Unknown restart choice")
    project, review = store.project(project_id), current_review(store, project_id)
    if project["state"] != S.RESTART_OFFER or project["row_version"] != expected_version:
        raise ConflictError("Stale restart action")
    previous = store.attempt(review.attempt_id)
    if previous["status"] != "failed" or previous["user_rejections"] != 2:
        raise ValueError("Restart requires a preserved failed attempt")
    current = store.brief(project_id)
    source = (draft_brief(store.original_intake(project_id), automatic=False) if choice == "original_idea"
              else store.brief(project_id, review.brief_version))
    values = {**source.model_dump(), "brief_id": current.brief_id, "version": current.version + 1}
    feedback = [f for f in store.records(project_id, "DesignFeedback") if f.attempt_id == review.attempt_id and f.action == "revise"]
    if choice == "brainstorm":
        values["reference_image_ids"] = list(dict.fromkeys(source.reference_image_ids + [i for f in feedback for i in f.reference_image_ids]))
    brief = DesignBrief.model_validate(values)
    new_attempt = new_id()
    decision = RestartDecision(previous_attempt_id=review.attempt_id, new_attempt_id=new_attempt,
                               choice=choice, brief_version=brief.version)
    with store._connection(write=True) as db:
        actual = store._project_row(db, project_id)
        if actual["row_version"] != expected_version:
            raise ConflictError("Stale restart action")
        store._insert_record(db, project_id, brief.brief_id, brief.version, brief)
        store.write_once(f"projects/{project_id}/briefs/v{brief.version:04d}.json", brief.model_dump_json(indent=2).encode())
        db.execute("INSERT INTO attempts(attempt_id,project_id,brief_version,created_at) VALUES (?,?,?,?)",
                   (new_attempt, project_id, brief.version, utc_now().isoformat()))
        db.execute("UPDATE projects SET brief_version=?,active_attempt_id=?,accepted_revision_id=NULL,accepted_geometry_hash=NULL,route=? WHERE project_id=?",
                   (brief.version, new_attempt, None if choice == "original_idea" else project["route"], project_id))
        store._insert_record(db, project_id, decision.decision_id, 1, decision)
        if choice == "brainstorm":
            message = ChatMessage(role="user", text="Review the failed attempt with me. Saved feedback: " +
                                  "; ".join(f.text or "Revision requested without a stated reason" for f in feedback),
                                  image_ids=[i for f in feedback for i in f.reference_image_ids], brief_version=brief.version)
            store._insert_record(db, project_id, message.message_id, 1, message)
        _state(store, db, project_id, {"approved_brief": S.SPEC_GENERATION, "brainstorm": S.ADVISOR_CHAT,
                                     "original_idea": S.ROUTE_SELECTION}[choice], "Explicit restart: " + choice)
        store._event(db, project_id, "attempt_restarted", decision.model_dump(mode="json"))
    return decision

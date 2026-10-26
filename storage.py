"""Transactional SQLite records and immutable, integrity-checked local files.

SQLite is the authoritative index. Files are published completely before their
index entry is committed. A failed transaction can leave an unreferenced file;
it cannot expose a partially written file as a committed record. No automatic
garbage collection or expensive-operation retries run on application startup.
"""

from __future__ import annotations

from contextlib import contextmanager
from dataclasses import dataclass
import hashlib
import json
import os
from pathlib import Path
import re
import sqlite3
import tempfile
import time
from typing import Iterator, Sequence

from schemas import (
    AnalysisRecommendation, AnalysisResults, AnalysisSpec, AnalysisPlan, ReportExplanation, ArtifactManifest,
    CADGeneration, ChatMessage, Contract, DesignBrief, DesignFeedback, DesignSpec,
    GeometryMetrics, ImageReference, Intake, Job, JobStatus, RuleResult,
    WorkflowState, FEMPreparation, DesignReview, DesignAcceptance, RestartDecision, new_id, utc_now,
)


class ConflictError(RuntimeError):
    """Stale edit, duplicate immutable record or incompatible idempotency key."""


class IntegrityError(RuntimeError):
    """Persisted bytes do not match their manifest."""


@dataclass(frozen=True)
class Upload:
    filename: str
    media_type: str
    data: bytes
    role: str = "desired_reference"


RECORD_TYPES = {c.__name__: c for c in (
    DesignBrief, DesignSpec, CADGeneration, GeometryMetrics, RuleResult,
    DesignFeedback, AnalysisRecommendation, AnalysisSpec, AnalysisResults, AnalysisPlan, ReportExplanation,
    ArtifactManifest, ChatMessage, FEMPreparation, DesignReview, DesignAcceptance, RestartDecision,
)}


def _json(value: object) -> str:
    return json.dumps(value, sort_keys=True, separators=(",", ":"), allow_nan=False)


def _safe_id(value: str) -> str:
    if not re.fullmatch(r"[A-Za-z0-9_-]{1,128}", value):
        raise ValueError("Identifiers must contain only letters, numbers, underscore or hyphen")
    return value


class Store:
    def __init__(self, root: str | Path):
        self.root = Path(root).resolve()
        # UUID revision trees can exceed legacy MAX_PATH under a long Windows
        # profile/workspace. Extended absolute paths work without registry edits.
        if os.name == "nt" and not str(self.root).startswith("\\\\?\\"):
            absolute = str(self.root)
            self.root = Path("\\\\?\\UNC\\" + absolute[2:] if absolute.startswith("\\\\")
                             else "\\\\?\\" + absolute)
        self.root.mkdir(parents=True, exist_ok=True)
        self.database = self.root / "workflow.sqlite3"
        with self._connection() as db:
            version = db.execute("PRAGMA user_version").fetchone()[0]
            if version not in (0, 1, 2):
                raise RuntimeError(f"Unsupported database schema version {version}")
            db.execute("PRAGMA journal_mode=WAL")
            db.executescript("""
                CREATE TABLE IF NOT EXISTS projects (
                    project_id TEXT PRIMARY KEY, original_intake TEXT NOT NULL,
                    state TEXT NOT NULL, row_version INTEGER NOT NULL DEFAULT 0,
                    brief_version INTEGER NOT NULL DEFAULT 0,
                    route TEXT, resume_state TEXT, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS images (
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    image_id TEXT NOT NULL, json TEXT NOT NULL,
                    PRIMARY KEY(project_id, image_id)
                );
                CREATE TABLE IF NOT EXISTS records (
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    kind TEXT NOT NULL, entity_id TEXT NOT NULL, version INTEGER NOT NULL,
                    json TEXT NOT NULL, created_at TEXT NOT NULL,
                    PRIMARY KEY(project_id, kind, entity_id, version)
                );
                CREATE TABLE IF NOT EXISTS events (
                    event_id INTEGER PRIMARY KEY AUTOINCREMENT,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    kind TEXT NOT NULL, payload TEXT NOT NULL, created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS attempts (
                    attempt_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    brief_version INTEGER NOT NULL,
                    status TEXT NOT NULL DEFAULT 'active',
                    user_rejections INTEGER NOT NULL DEFAULT 0 CHECK(user_rejections BETWEEN 0 AND 2),
                    created_at TEXT NOT NULL
                );
                CREATE TABLE IF NOT EXISTS revisions (
                    revision_id TEXT PRIMARY KEY,
                    attempt_id TEXT NOT NULL REFERENCES attempts(attempt_id),
                    ordinal INTEGER NOT NULL CHECK(ordinal BETWEEN 1 AND 2),
                    technical_repairs INTEGER NOT NULL DEFAULT 0 CHECK(technical_repairs BETWEEN 0 AND 1),
                    relative_path TEXT NOT NULL UNIQUE,
                    UNIQUE(attempt_id, ordinal)
                );
                CREATE TABLE IF NOT EXISTS jobs (
                    job_id TEXT PRIMARY KEY,
                    project_id TEXT NOT NULL REFERENCES projects(project_id),
                    idempotency_key TEXT NOT NULL, kind TEXT NOT NULL,
                    payload TEXT NOT NULL, payload_hash TEXT NOT NULL,
                    status TEXT NOT NULL, owner_id TEXT, error TEXT, result TEXT,
                    created_at TEXT NOT NULL, updated_at TEXT NOT NULL,
                    UNIQUE(project_id, idempotency_key)
                );
                CREATE TRIGGER IF NOT EXISTS immutable_intake
                    BEFORE UPDATE OF original_intake ON projects
                    BEGIN SELECT RAISE(ABORT, 'Original intake is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_records_update BEFORE UPDATE ON records
                    BEGIN SELECT RAISE(ABORT, 'Versioned records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_records_delete BEFORE DELETE ON records
                    BEGIN SELECT RAISE(ABORT, 'Versioned records are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_images_update BEFORE UPDATE ON images
                    BEGIN SELECT RAISE(ABORT, 'Image metadata is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_images_delete BEFORE DELETE ON images
                    BEGIN SELECT RAISE(ABORT, 'Image metadata is immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_events_update BEFORE UPDATE ON events
                    BEGIN SELECT RAISE(ABORT, 'Audit events are immutable'); END;
                CREATE TRIGGER IF NOT EXISTS immutable_events_delete BEFORE DELETE ON events
                    BEGIN SELECT RAISE(ABORT, 'Audit events are immutable'); END;
            """)
        # Additive migration: retain every v1 record and artifact.
        with self._connection(write=True) as db:
            columns = {row[1] for row in db.execute("PRAGMA table_info(projects)")}
            for name in ("active_attempt_id", "accepted_revision_id", "accepted_geometry_hash"):
                if name not in columns:
                    db.execute(f"ALTER TABLE projects ADD COLUMN {name} TEXT")
            db.execute("PRAGMA user_version=2")

    @contextmanager
    def _connection(self, *, write: bool = False) -> Iterator[sqlite3.Connection]:
        # Windows WAL can briefly return SQLITE_PROTOCOL while competing
        # connections initialize. Retry only before yielding the transaction;
        # never replay a transaction body or a commit with unknown outcome.
        for attempt in range(5):
            db = sqlite3.connect(self.database, timeout=15, isolation_level=None)
            db.row_factory = sqlite3.Row
            try:
                db.execute("PRAGMA foreign_keys=ON")
                db.execute("PRAGMA synchronous=FULL")
                if write:
                    db.execute("BEGIN IMMEDIATE")
                break
            except sqlite3.OperationalError as error:
                db.close()
                if getattr(error, "sqlite_errorcode", None) != sqlite3.SQLITE_PROTOCOL or attempt == 4:
                    raise
                time.sleep(.02 * (attempt + 1))
        try:
            yield db
            if write:
                db.commit()
        except BaseException:
            if write:
                db.rollback()
            raise
        finally:
            db.close()

    def path(self, relative: str) -> Path:
        # Treat Windows and POSIX path syntax identically, including on POSIX CI.
        if not relative or "\\" in relative or ":" in relative:
            raise ValueError("Expected a relative artifact path using forward slashes")
        parts = relative.split("/")
        if any(part in ("", ".", "..") for part in parts):
            raise ValueError("Artifact paths must not contain traversal or empty segments")
        target = (self.root / relative).resolve()
        if not target.is_relative_to(self.root):
            raise ValueError("Artifact path escapes data root")
        return target

    def write_once(self, relative: str, data: bytes) -> Path:
        target = self.path(relative)
        target.parent.mkdir(parents=True, exist_ok=True)
        descriptor, temporary = tempfile.mkstemp(prefix=".pending-", dir=target.parent)
        try:
            with os.fdopen(descriptor, "wb") as file:
                file.write(data)
                file.flush()
                os.fsync(file.fileno())
            # Atomic no-clobber publication on local NTFS and normal POSIX filesystems.
            # Failure on an unsupported filesystem is explicit; never fall back to overwrite.
            os.link(temporary, target)
        finally:
            Path(temporary).unlink(missing_ok=True)
        return target

    @staticmethod
    def _event(db: sqlite3.Connection, project_id: str, kind: str, payload: dict) -> None:
        db.execute("INSERT INTO events(project_id,kind,payload,created_at) VALUES (?,?,?,?)",
                   (project_id, kind, _json(payload), utc_now().isoformat()))

    def create_project(self, intake: Intake, uploads: Sequence[Upload] = ()) -> str:
        # Validate again: callers may have used model_copy(update=...) or mutated lists.
        intake = Intake.model_validate_json(intake.model_dump_json())
        if intake.reference_image_ids:
            raise ValueError("New intake image IDs are assigned from uploaded bytes")
        project_id = new_id()
        images = [self._prepare_image(project_id, upload) for upload in uploads]
        original = Intake.model_validate({**intake.model_dump(),
                                         "reference_image_ids": [i.image_id for i in images]})
        with self._connection(write=True) as db:
            db.execute("INSERT INTO projects(project_id,original_intake,state,created_at) VALUES (?,?,?,?)",
                       (project_id, original.model_dump_json(), WorkflowState.INTAKE, utc_now().isoformat()))
            for image, upload in zip(images, uploads):
                self._save_prepared_image(db, project_id, image, upload.data)
            self.write_once(f"projects/{project_id}/intake/intake.json", original.model_dump_json(indent=2).encode())
            self._event(db, project_id, "project_created", {"image_ids": original.reference_image_ids})
        return project_id

    @staticmethod
    def _prepare_image(project_id: str, upload: Upload) -> ImageReference:
        image_id = new_id()
        suffixes = {"image/png": ".png", "image/jpeg": ".jpg", "image/webp": ".webp"}
        if upload.media_type not in suffixes:
            raise ValueError("Only PNG, JPEG and WebP images are supported")
        return ImageReference(
            image_id=image_id, filename=upload.filename, media_type=upload.media_type,
            role=upload.role, sha256=hashlib.sha256(upload.data).hexdigest(),
            size_bytes=len(upload.data),
            relative_path=f"projects/{_safe_id(project_id)}/uploads/{image_id}{suffixes[upload.media_type]}",
        )

    def _save_prepared_image(self, db: sqlite3.Connection, project_id: str,
                             image: ImageReference, data: bytes) -> None:
        self.write_once(image.relative_path, data)
        db.execute("INSERT INTO images VALUES (?,?,?)", (project_id, image.image_id, image.model_dump_json()))

    def save_image(self, project_id: str, upload: Upload) -> ImageReference:
        with self._connection(write=True) as db:
            self._project_row(db, project_id)
            image = self._prepare_image(project_id, upload)
            self._save_prepared_image(db, project_id, image, upload.data)
            self._event(db, project_id, "image_saved", {"image_id": image.image_id, "sha256": image.sha256})
        return image

    def images(self, project_id: str) -> list[ImageReference]:
        with self._connection() as db:
            self._project_row(db, project_id)
            return [ImageReference.model_validate_json(row[0]) for row in db.execute(
                "SELECT json FROM images WHERE project_id=? ORDER BY rowid", (project_id,))]

    def read_image(self, project_id: str, image_id: str) -> bytes:
        images = {image.image_id: image for image in self.images(project_id)}
        if image_id not in images:
            raise KeyError(image_id)
        image = images[image_id]
        return self._verified_bytes(image.relative_path, image.sha256, image.size_bytes)

    def _verified_bytes(self, relative: str, digest: str, size: int) -> bytes:
        try:
            data = self.path(relative).read_bytes()
        except FileNotFoundError as error:
            raise IntegrityError(f"Missing artifact: {relative}") from error
        if len(data) != size or hashlib.sha256(data).hexdigest() != digest:
            raise IntegrityError(f"Artifact integrity check failed: {relative}")
        return data

    def verify_manifest(self, manifest: ArtifactManifest, required_roles: Sequence[str] = ()) -> None:
        manifest = ArtifactManifest.model_validate_json(manifest.model_dump_json())
        if not manifest.completed:
            raise IntegrityError("Incomplete manifest")
        prefix = f"projects/{_safe_id(manifest.project_id)}/"
        for artifact in manifest.artifacts:
            if not artifact.relative_path.startswith(prefix):
                raise IntegrityError("Manifest artifact belongs to a different project")
            self._verified_bytes(artifact.relative_path, artifact.sha256, artifact.size_bytes)
        missing = set(required_roles) - {a.role for a in manifest.artifacts}
        if missing:
            raise IntegrityError(f"Missing expected artifact roles: {sorted(missing)}")

    @staticmethod
    def _project_row(db: sqlite3.Connection, project_id: str) -> sqlite3.Row:
        row = db.execute("SELECT * FROM projects WHERE project_id=?", (project_id,)).fetchone()
        if row is None:
            raise KeyError(project_id)
        return row

    def project(self, project_id: str) -> dict:
        with self._connection() as db:
            row = dict(self._project_row(db, project_id))
            row["original_intake"] = Intake.model_validate_json(row["original_intake"])
            row["state"] = WorkflowState(row["state"])
            return row

    def projects(self) -> list[dict]:
        with self._connection() as db:
            return [dict(row) for row in db.execute(
                "SELECT project_id,state,row_version,brief_version,route,created_at FROM projects ORDER BY created_at")]

    def original_intake(self, project_id: str) -> Intake:
        original = self.project(project_id)["original_intake"]
        data = self.path(f"projects/{_safe_id(project_id)}/intake/intake.json").read_bytes()
        if Intake.model_validate_json(data) != original:
            raise IntegrityError("Original intake file differs from immutable database record")
        return original

    def events(self, project_id: str) -> list[dict]:
        with self._connection() as db:
            self._project_row(db, project_id)
            return [{**dict(row), "payload": json.loads(row["payload"])} for row in db.execute(
                "SELECT * FROM events WHERE project_id=? ORDER BY event_id", (project_id,))]

    def _insert_record(self, db: sqlite3.Connection, project_id: str,
                       entity_id: str, version: int, record: Contract) -> None:
        if type(record).__name__ not in RECORD_TYPES or version < 1:
            raise ValueError("Unsupported record type or version")
        validated = RECORD_TYPES[type(record).__name__].model_validate_json(record.model_dump_json())
        try:
            db.execute("INSERT INTO records VALUES (?,?,?,?,?,?)", (
                project_id, type(record).__name__, entity_id, version,
                validated.model_dump_json(), utc_now().isoformat()))
        except sqlite3.IntegrityError as error:
            raise ConflictError("Record already exists or project is missing") from error

    def save_record(self, project_id: str, entity_id: str, version: int, record: Contract) -> None:
        if isinstance(record, DesignBrief):
            raise ValueError("Brief writes require save_brief with optimistic concurrency")
        with self._connection(write=True) as db:
            self._project_row(db, project_id)
            self._insert_record(db, project_id, entity_id, version, record)
            self._event(db, project_id, "record_saved", {"kind": type(record).__name__,
                                                       "entity_id": entity_id, "version": version})

    def record(self, project_id: str, kind: str, entity_id: str, version: int) -> Contract:
        if kind not in RECORD_TYPES:
            raise ValueError("Unsupported record type")
        with self._connection() as db:
            row = db.execute("SELECT json FROM records WHERE project_id=? AND kind=? AND entity_id=? AND version=?",
                             (project_id, kind, entity_id, version)).fetchone()
            if row is None:
                raise KeyError((project_id, kind, entity_id, version))
            return RECORD_TYPES[kind].model_validate_json(row[0])

    def records(self, project_id: str, kind: str) -> list[Contract]:
        if kind not in RECORD_TYPES:
            raise ValueError("Unsupported record type")
        with self._connection() as db:
            self._project_row(db, project_id)
            return [RECORD_TYPES[kind].model_validate_json(row[0]) for row in db.execute(
                "SELECT json FROM records WHERE project_id=? AND kind=? ORDER BY created_at,rowid",
                (project_id, kind))]

    def save_brief(self, project_id: str, brief: DesignBrief, *, expected_version: int,
                   actor: str, reason: str) -> DesignBrief:
        brief = DesignBrief.model_validate_json(brief.model_dump_json())
        if brief.version != expected_version + 1 or not actor.strip() or not reason.strip():
            raise ValueError("Brief version must advance once; actor and change reason are required")
        with self._connection(write=True) as db:
            project = self._project_row(db, project_id)
            if project["brief_version"] != expected_version:
                raise ConflictError("Stale brief response; reload current brief and reconcile changes")
            if expected_version:
                prior = db.execute("SELECT json FROM records WHERE project_id=? AND kind='DesignBrief' AND version=?",
                                   (project_id, expected_version)).fetchone()
                if DesignBrief.model_validate_json(prior[0]).brief_id != brief.brief_id:
                    raise ValueError("Brief identity must remain stable across versions")
            known_images = {row[0] for row in db.execute("SELECT image_id FROM images WHERE project_id=?", (project_id,))}
            if not set(brief.reference_image_ids).issubset(known_images):
                raise ValueError("Brief references images not stored in this project")
            self._insert_record(db, project_id, brief.brief_id, brief.version, brief)
            self.write_once(f"projects/{_safe_id(project_id)}/briefs/v{brief.version:04d}.json",
                            brief.model_dump_json(indent=2).encode())
            db.execute("UPDATE projects SET brief_version=?,row_version=row_version+1 WHERE project_id=?",
                       (brief.version, project_id))
            self._event(db, project_id, "brief_saved", {"version": brief.version, "actor": actor, "reason": reason})
        return brief

    def brief(self, project_id: str, version: int | None = None) -> DesignBrief:
        with self._connection() as db:
            project = self._project_row(db, project_id)
            number = project["brief_version"] if version is None else version
            row = db.execute("SELECT json FROM records WHERE project_id=? AND kind='DesignBrief' AND version=?",
                             (project_id, number)).fetchone()
            if row is None:
                raise KeyError((project_id, "DesignBrief", number))
            return DesignBrief.model_validate_json(row[0])

    def create_attempt(self, project_id: str, brief_version: int) -> dict:
        # Freeze by reference to an append-only validated record, not mutable intake.
        self.brief(project_id, brief_version)
        attempt_id = new_id()
        with self._connection(write=True) as db:
            db.execute("INSERT INTO attempts(attempt_id,project_id,brief_version,created_at) VALUES (?,?,?,?)",
                       (attempt_id, project_id, brief_version, utc_now().isoformat()))
            db.execute("UPDATE projects SET active_attempt_id=? WHERE project_id=?", (attempt_id, project_id))
            self._event(db, project_id, "attempt_created", {"attempt_id": attempt_id, "brief_version": brief_version})
        return self.attempt(attempt_id)

    def attempt(self, attempt_id: str) -> dict:
        with self._connection() as db:
            row = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if row is None:
                raise KeyError(attempt_id)
            return dict(row)

    def consume_technical_repair(self, revision_id: str) -> None:
        with self._connection(write=True) as db:
            row = db.execute("SELECT r.*,a.project_id FROM revisions r JOIN attempts a USING(attempt_id) WHERE revision_id=?",
                             (revision_id,)).fetchone()
            if row is None:
                raise KeyError(revision_id)
            if db.execute("UPDATE revisions SET technical_repairs=technical_repairs+1 WHERE revision_id=? AND technical_repairs=0",
                          (revision_id,)).rowcount != 1:
                raise ConflictError("Technical repair budget exhausted for this revision")
            self._event(db, row["project_id"], "technical_repair_consumed", {"revision_id": revision_id})

    def revision(self, revision_id: str) -> dict:
        with self._connection() as db:
            row = db.execute("SELECT r.*,a.project_id FROM revisions r JOIN attempts a USING(attempt_id) WHERE revision_id=?",
                             (revision_id,)).fetchone()
            if row is None:
                raise KeyError(revision_id)
            return dict(row)

    def create_revision(self, attempt_id: str) -> dict:
        with self._connection(write=True) as db:
            attempt = db.execute("SELECT * FROM attempts WHERE attempt_id=?", (attempt_id,)).fetchone()
            if attempt is None:
                raise KeyError(attempt_id)
            if attempt["status"] != "active":
                raise ConflictError("Cannot create a candidate in a closed attempt")
            ordinal = db.execute("SELECT COUNT(*)+1 FROM revisions WHERE attempt_id=?", (attempt_id,)).fetchone()[0]
            if ordinal > 2:
                raise ConflictError("At most two candidate revisions per attempt")
            revision_id = new_id()
            relative = f"projects/{attempt['project_id']}/attempts/{attempt_id}/revisions/{revision_id}"
            self.path(relative).mkdir(parents=True, exist_ok=False)
            db.execute("INSERT INTO revisions(revision_id,attempt_id,ordinal,relative_path) VALUES (?,?,?,?)",
                       (revision_id, attempt_id, ordinal, relative))
            self._event(db, attempt["project_id"], "revision_created", {"revision_id": revision_id, "ordinal": ordinal})
            return {"revision_id": revision_id, "attempt_id": attempt_id, "ordinal": ordinal,
                    "technical_repairs": 0, "relative_path": relative}

    def enqueue(self, project_id: str, key: str, kind: str, payload: dict) -> Job:
        with self._connection(write=True) as db:
            return self._enqueue(db, project_id, key, kind, payload)

    def _enqueue(self, db: sqlite3.Connection, project_id: str, key: str, kind: str, payload: dict) -> Job:
        if not key.strip() or not kind.strip():
            raise ValueError("Job kind and idempotency key are required")
        body = _json(payload)
        digest = hashlib.sha256(body.encode()).hexdigest()
        self._project_row(db, project_id)
        row = db.execute("SELECT * FROM jobs WHERE project_id=? AND idempotency_key=?", (project_id, key)).fetchone()
        if row is not None:
            if row["kind"] != kind or row["payload_hash"] != digest:
                raise ConflictError("Idempotency key reused for different inputs")
            return self._job(row)
        job_id, now = new_id(), utc_now().isoformat()
        db.execute("INSERT INTO jobs(job_id,project_id,idempotency_key,kind,payload,payload_hash,status,created_at,updated_at) VALUES (?,?,?,?,?,?,?,?,?)",
                   (job_id, project_id, key, kind, body, digest, JobStatus.PENDING, now, now))
        self._event(db, project_id, "job_enqueued", {"job_id": job_id, "kind": kind})
        row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
        return self._job(row)


    @staticmethod
    def _job(row: sqlite3.Row) -> Job:
        values = dict(row)
        values.pop("payload_hash")
        values["payload"] = json.loads(values["payload"])
        values["result"] = json.loads(values["result"]) if values["result"] is not None else None
        return Job.model_validate(values)

    def job(self, job_id: str) -> Job:
        with self._connection() as db:
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            if row is None:
                raise KeyError(job_id)
            return self._job(row)

    def jobs(self, project_id: str) -> list[Job]:
        with self._connection() as db:
            self._project_row(db, project_id)
            return [self._job(row) for row in db.execute("SELECT * FROM jobs WHERE project_id=? ORDER BY created_at", (project_id,))]

    def claim(self, job_id: str, owner_id: str) -> Job | None:
        _safe_id(owner_id)
        with self._connection(write=True) as db:
            changed = db.execute("UPDATE jobs SET status=?,owner_id=?,updated_at=? WHERE job_id=? AND status=?",
                                 (JobStatus.RUNNING, owner_id, utc_now().isoformat(), job_id, JobStatus.PENDING)).rowcount
            if not changed:
                return None
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            self._event(db, row["project_id"], "job_claimed", {"job_id": job_id, "owner_id": owner_id})
            return self._job(row)

    def finish(self, job_id: str, owner_id: str, status: JobStatus, *,
               result: dict | None = None, error: str | None = None) -> Job:
        if status not in (JobStatus.SUCCEEDED, JobStatus.FAILED, JobStatus.BLOCKED):
            raise ValueError("Invalid completion status")
        if status != JobStatus.SUCCEEDED and not error:
            raise ValueError("Failed/blocked jobs require the actual error or dependency reason")
        if status == JobStatus.SUCCEEDED and error:
            raise ValueError("Successful jobs cannot include an error")
        with self._connection(write=True) as db:
            changed = db.execute("UPDATE jobs SET status=?,result=?,error=?,updated_at=? WHERE job_id=? AND status=? AND owner_id=?",
                                 (status, _json(result) if result is not None else None, error,
                                  utc_now().isoformat(), job_id, JobStatus.RUNNING, owner_id)).rowcount
            if not changed:
                raise ConflictError("Only the current owner may complete a running job")
            row = db.execute("SELECT * FROM jobs WHERE job_id=?", (job_id,)).fetchone()
            self._event(db, row["project_id"], "job_finished", {"job_id": job_id, "status": status, "error": error})
            return self._job(row)

    def recover_interrupted(self, owner_id: str) -> list[str]:
        """Explicit operator recovery, only after checking this owner is no longer running.

        This marks jobs interrupted; it never re-enqueues, executes, or assumes
        a job failed merely because the frontend reran or another Store opened.
        """
        _safe_id(owner_id)
        with self._connection(write=True) as db:
            rows = db.execute("SELECT job_id,project_id FROM jobs WHERE owner_id=? AND status=?",
                              (owner_id, JobStatus.RUNNING)).fetchall()
            for row in rows:
                db.execute("UPDATE jobs SET status=?,error=?,updated_at=? WHERE job_id=?",
                           (JobStatus.INTERRUPTED, "Owner interrupted; inspect artifacts before explicit retry with a new key",
                            utc_now().isoformat(), row["job_id"]))
                self._event(db, row["project_id"], "job_interrupted", {"job_id": row["job_id"], "owner_id": owner_id})
            return [row["job_id"] for row in rows]

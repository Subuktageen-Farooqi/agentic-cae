"""Export, inspect and restore private local workflow state without credentials.

Git contains source and curated knowledge. This archive contains only the
committed SQLite snapshot, its referenced project artifacts and live-call ledgers.
Restore is no-clobber and requires a checkout with no existing workflow data.
"""
from __future__ import annotations

import argparse
from contextlib import closing
from datetime import datetime, timezone
import hashlib
import json
import os
from pathlib import Path, PurePosixPath
import shutil
import sqlite3
from uuid import uuid4
import zipfile


REPO = Path(__file__).resolve().parents[1]
STATE_FORMAT = "agentic-cae-local-state-v1"
LEDGERS = ("requests.sqlite3", "recovery-requests.sqlite3", "bracket-requests.sqlite3")


def digest(data: bytes) -> str:
    return hashlib.sha256(data).hexdigest()


def safe_name(name: str) -> bool:
    path = PurePosixPath(name)
    if not name or "\\" in name or path.is_absolute() or ".." in path.parts or str(path) != name:
        return False
    return (name == "data/workflow.sqlite3"
            or (len(path.parts) >= 3 and path.parts[:2] == ("data", "projects"))
            or (path.parts == (".tools", "live-smoke", path.name) and path.name in LEDGERS))


def inspect_archive(archive: Path) -> dict:
    with zipfile.ZipFile(archive) as bundle:
        names = bundle.namelist()
        if len(names) != len(set(names)) or names.count("handoff_manifest.json") != 1:
            raise ValueError("Archive has missing or duplicate manifest/entries")
        manifest = json.loads(bundle.read("handoff_manifest.json"))
        if manifest.get("format") != STATE_FORMAT or set(manifest["files"]) != set(names) - {"handoff_manifest.json"}:
            raise ValueError("Archive manifest does not match its files")
        if "data/workflow.sqlite3" not in manifest["files"]:
            raise ValueError("Archive has no committed workflow database")
        if len({name.casefold() for name in manifest["files"]}) != len(manifest["files"]):
            raise ValueError("Case-colliding archive paths cannot be restored on Windows")
        for name, expected in manifest["files"].items():
            if not safe_name(name):
                raise ValueError("Archive contains a forbidden or unsafe path")
            record = bundle.getinfo(name)
            if record.is_dir() or (record.external_attr >> 16) & 0o170000 == 0o120000:
                raise ValueError("Archive contains a directory or symlink entry")
            payload = bundle.read(name)
            if len(payload) != expected["size_bytes"] or digest(payload) != expected["sha256"]:
                raise ValueError("Archive content differs from its manifest")
        return manifest


def export_state(output: Path, repo: Path = REPO) -> dict:
    data_root = (repo / "data").resolve()
    database = data_root / "workflow.sqlite3"
    projects = data_root / "projects"
    if not database.is_file() or not projects.is_dir():
        raise FileNotFoundError("Expected workflow.sqlite3 and data/projects before export")
    output = output.resolve()
    if output.exists():
        raise FileExistsError("Never overwrite a handoff archive")
    output.parent.mkdir(parents=True, exist_ok=True)
    # The database backup is transactionally consistent even when the source
    # uses WAL. Do not archive the source SQLite file and WAL independently.
    backup = output.parent / (".workflow-backup-" + uuid4().hex + ".sqlite3")
    if backup.exists():
        raise FileExistsError("Private SQLite backup path already exists")
    try:
        with closing(sqlite3.connect(database)) as source, closing(sqlite3.connect(backup)) as target:
            if source.execute("SELECT COUNT(*) FROM jobs WHERE status IN ('pending','running')").fetchone()[0]:
                raise RuntimeError("Inspect active jobs before exporting immutable artifacts")
            source.backup(target)
        with closing(sqlite3.connect(backup)) as check:
            project_ids = [row[0] for row in check.execute("SELECT project_id FROM projects ORDER BY project_id")]
        files: dict[str, Path] = {"data/workflow.sqlite3": backup}
        for path in projects.rglob("*"):
            if path.is_symlink():
                raise ValueError("Local project artifacts cannot contain symlinks")
            if path.is_file():
                name = (PurePosixPath("data/projects") / path.relative_to(projects).as_posix()).as_posix()
                if not safe_name(name):
                    raise ValueError("Unsafe local project artifact path")
                files[name] = path
        for filename in LEDGERS:
            path = repo / ".tools" / "live-smoke" / filename
            if path.is_file():
                files[f".tools/live-smoke/{filename}"] = path
        metadata: dict[str, dict[str, str | int]] = {}
        with output.open("xb") as stream, zipfile.ZipFile(stream, "w", compression=zipfile.ZIP_DEFLATED, compresslevel=6) as bundle:
            for name, path in sorted(files.items()):
                contents = path.read_bytes()
                metadata[name] = {"size_bytes": len(contents), "sha256": digest(contents)}
                bundle.writestr(name, contents)
            manifest = {"format": STATE_FORMAT, "created_utc": datetime.now(timezone.utc).isoformat(),
                        "project_ids": project_ids, "files": metadata,
                        "excluded": [".env", "credentials", "Python environment", "FreeCAD/Podman installations", "container images/VM"]}
            bundle.writestr("handoff_manifest.json", json.dumps(manifest, indent=2))
        checked = inspect_archive(output)
        return {"archive": str(output), "sha256": digest(output.read_bytes()),
                "bytes": output.stat().st_size, "projects": len(checked["project_ids"]),
                "artifact_files": len(files) - 1 - sum(name.startswith(".tools/") for name in files),
                "ledger_files": sum(name.startswith(".tools/") for name in files)}
    finally:
        if backup.is_file():
            backup.unlink()


def restore_state(archive: Path, repo: Path) -> dict:
    repo = repo.resolve()
    if not repo.is_dir():
        raise FileNotFoundError("Restore target must be an existing checkout folder")
    manifest = inspect_archive(archive)
    names = sorted(manifest["files"])
    targets = {}
    for name in names:
        target = (repo / Path(*PurePosixPath(name).parts)).resolve()
        if not target.is_relative_to(repo) or target.exists():
            raise FileExistsError("Restore requires an empty local state; will not overwrite " + name)
        targets[name] = target
    private = (repo / ".tools" / "handoff").resolve()
    if not private.is_relative_to(repo):
        raise ValueError("Private restore staging escaped the target checkout")
    private.mkdir(parents=True, exist_ok=True)
    staging = private / ("restore-" + uuid4().hex)
    staging.mkdir(exist_ok=False)
    if not staging.resolve().is_relative_to(private):
        raise ValueError("Restore staging escaped its private directory")
    try:
        with zipfile.ZipFile(archive) as bundle:
            for name in names:
                staged = staging / Path(*PurePosixPath(name).parts)
                staged.parent.mkdir(parents=True, exist_ok=True)
                staged.write_bytes(bundle.read(name))
        for name in names:
            target = targets[name]
            target.parent.mkdir(parents=True, exist_ok=True)
            # Same-volume hard link publishes each verified file atomically;
            # os.link refuses to replace an existing local database/artifact.
            os.link(staging / Path(*PurePosixPath(name).parts), target)
    finally:
        if staging.resolve().is_relative_to(private) and staging.is_dir():
            shutil.rmtree(staging)
    return {"restored_projects": len(manifest["project_ids"]), "files": len(names),
            "data_dir": str(repo / "data"), "ledger_dir": str(repo / ".tools" / "live-smoke")}


def main() -> None:
    parser = argparse.ArgumentParser(description=__doc__)
    sub = parser.add_subparsers(dest="command", required=True)
    export = sub.add_parser("export")
    export.add_argument("--output", type=Path, help="Private ZIP destination; must not already exist")
    inspect = sub.add_parser("inspect")
    inspect.add_argument("archive", type=Path)
    restore = sub.add_parser("restore")
    restore.add_argument("archive", type=Path)
    restore.add_argument("--repo-root", type=Path, default=REPO)
    args = parser.parse_args()
    if args.command == "export":
        output = args.output or REPO / ".tools" / "handoff" / ("agentic-cae-state-" + datetime.now(timezone.utc).strftime("%Y%m%d-%H%M%S") + ".zip")
        result = export_state(output)
    elif args.command == "inspect":
        archive = args.archive.resolve()
        result = {"archive": str(archive), "sha256": digest(archive.read_bytes()),
                  "projects": len(inspect_archive(archive)["project_ids"])}
    else:
        result = restore_state(args.archive.resolve(), args.repo_root)
    print(json.dumps(result, indent=2))


if __name__ == "__main__":
    main()

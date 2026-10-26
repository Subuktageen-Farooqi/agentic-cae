"""Only execution path for generated CAD: a restricted Docker/Podman container."""
from __future__ import annotations

import hashlib
import json
from pathlib import Path
import shutil
import subprocess
import uuid

from config import Config, local_podman
from schemas import ArtifactManifest, CADGeneration
from workers.code_validation import validate_code


class SandboxUnavailable(RuntimeError):
    pass


class CADBuildError(RuntimeError):
    pass


def runtime_executable(config: Config) -> str:
    return shutil.which(config.container_runtime) or (local_podman() if config.container_runtime == "podman" else None) or config.container_runtime


def check_runtime(config: Config) -> None:
    executable = runtime_executable(config)
    if not shutil.which(executable):
        raise SandboxUnavailable(f"{config.container_runtime} is unavailable; generated code was not executed")
    try:
        daemon = subprocess.run([executable, "info", "--format", "{{json .}}"],
                                capture_output=True, text=True, timeout=15)
        try:
            info = json.loads(daemon.stdout)
        except json.JSONDecodeError:
            info = {}
        system = info.get("OSType") or info.get("host", {}).get("os")
        if daemon.returncode != 0 or system != "linux":
            raise SandboxUnavailable("A running Linux container engine is required for generated CAD")
        image = subprocess.run([executable, "image", "inspect", config.cad_image],
                               capture_output=True, text=True, timeout=15)
        if image.returncode != 0:
            raise SandboxUnavailable(f"CAD image is missing. Build it: {config.container_runtime} build -f workers/Dockerfile -t {config.cad_image} .")
    except (OSError, subprocess.TimeoutExpired) as error:
        raise SandboxUnavailable(f"Container engine could not be verified: {error}") from error


def container_command(config: Config, directory: Path, name: str) -> list[str]:
    source = str(directory.resolve())
    if source.startswith("\\\\?\\UNC\\"):
        source = "\\\\" + source[8:]
    elif source.startswith("\\\\?\\"):
        source = source[4:]
    return [runtime_executable(config), "run", "--rm", "--name", name, "--network=none", "--read-only",
            "--user=65532:65532", "--cap-drop=ALL", "--security-opt=no-new-privileges", "--pids-limit=64",
            "--cpus=2", "--memory=2g", "--memory-swap=2g", "--tmpfs", "/tmp:rw,noexec,nosuid,size=256m",
            "--mount", f"type=bind,source={source},target=/job", config.cad_image]


def execute_generated(*, generation: CADGeneration, project_id: str, job_id: str,
                      output_dir: Path, project_root: Path, config: Config) -> ArtifactManifest:
    validate_code(generation.code)
    check_runtime(config)
    root, directory = project_root.resolve(), output_dir.resolve()
    if not directory.is_relative_to(root):
        raise ValueError("Generated job directory must stay within the artifact root")
    directory.mkdir(parents=True, exist_ok=False)
    # This mount contains only this job's code/parameters, never a project root,
    # credentials, host socket or unrelated uploads.
    (directory / "input.py").write_text(generation.code, encoding="utf-8")
    (directory / "input.json").write_text(json.dumps({"project_id": project_id, "job_id": job_id,
                                                    "parameters": generation.parameters}), encoding="utf-8")
    directory.chmod(0o777)
    name = "cae-cad-" + uuid.uuid4().hex
    try:
        process = subprocess.run(container_command(config, directory, name), capture_output=True, text=True,
                                 timeout=config.worker_timeout_seconds)
    except subprocess.TimeoutExpired as error:
        subprocess.run([runtime_executable(config), "rm", "-f", name], capture_output=True, timeout=15)
        (directory / "container.log").write_text("Container exceeded the configured time limit", encoding="utf-8")
        raise CADBuildError("Generated CAD exceeded the container time limit") from error
    (directory / "container.log").write_text(process.stdout + "\n" + process.stderr, encoding="utf-8")
    if process.returncode != 0:
        raise CADBuildError(f"Generated CAD failed with exit {process.returncode}: {process.stderr[-6000:]}")
    completion = directory / "completion.json"
    if not completion.is_file():
        raise CADBuildError("Container exited without a completion manifest")
    manifest = ArtifactManifest.model_validate_json(completion.read_text(encoding="utf-8"))
    if not manifest.completed or manifest.project_id != project_id or manifest.job_id != job_id:
        raise CADBuildError("Container completion is incomplete or belongs to another job")
    roles = {a.role for a in manifest.artifacts}
    if not {"step", "preview", "model_source", "parameters", "cad_metadata", "cad_log"}.issubset(roles):
        raise CADBuildError("Container manifest is missing required CAD outputs")
    artifacts = []
    total_bytes = 0
    for artifact in manifest.artifacts:
        path = (directory / artifact.relative_path).resolve()
        if not path.is_relative_to(directory) or not path.is_file() or path.is_symlink():
            raise CADBuildError("Container artifact escaped its job directory or is missing")
        total_bytes += path.stat().st_size
        if path.stat().st_size > 64 * 1024 * 1024 or total_bytes > 256 * 1024 * 1024:
            raise CADBuildError("Container outputs exceed prototype artifact size limits")
        data = path.read_bytes()
        if not data or len(data) != artifact.size_bytes or hashlib.sha256(data).hexdigest() != artifact.sha256:
            raise CADBuildError("Container artifact integrity verification failed")
        artifacts.append(artifact.model_copy(update={"relative_path": path.relative_to(root).as_posix()}))
    # Original hashed metadata remains immutable. Host execution evidence is separate.
    (directory / "isolation.json").write_text(json.dumps({"image": config.cad_image,
        "network": "none", "user": "65532:65532", "read_only_root": True,
        "memory_bytes": 2147483648, "cpus": 2, "timeout_seconds": config.worker_timeout_seconds}), encoding="utf-8")
    return manifest.model_copy(update={"artifacts": artifacts, "revision_id": generation.revision_id,
                                       "attempt_id": generation.attempt_id})

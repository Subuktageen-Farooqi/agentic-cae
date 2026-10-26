"""Environment configuration and read-only dependency-presence diagnostics.

Presence is not execution, authentication, compatibility or license validation.
Reports deliberately omit environment values, credential contents and paths.
"""

from __future__ import annotations

from dataclasses import dataclass
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
from typing import Mapping


@dataclass(frozen=True)
class Config:
    data_dir: Path
    google_project: str | None
    google_location: str | None
    gemini_model_id: str | None
    adc_path: Path | None
    freecad_cmd: str | None
    mechanical_exe: str | None
    container_runtime: str
    worker_timeout_seconds: int

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        values = os.environ if env is None else env

        def text(key: str) -> str | None:
            return values.get(key, "").strip() or None

        adc = text("GOOGLE_APPLICATION_CREDENTIALS")
        if adc:
            adc_path = Path(adc).expanduser()
        elif text("APPDATA"):
            adc_path = Path(values["APPDATA"]) / "gcloud" / "application_default_credentials.json"
        else:
            adc_path = Path.home() / ".config" / "gcloud" / "application_default_credentials.json"
        timeout = int(text("CAE_WORKER_TIMEOUT_SECONDS") or "300")
        if timeout <= 0:
            raise ValueError("Worker timeout must be positive")
        runtime = text("CAE_CONTAINER_RUNTIME") or "docker"
        if runtime not in ("docker", "podman"):
            raise ValueError("Container runtime must be docker or podman")
        freecad = text("FREECAD_CMD")
        if not freecad and os.name == "nt":
            candidates: list[Path] = []
            for parent in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                           Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))):
                candidates.extend(parent.glob("FreeCAD */bin/freecadcmd.exe"))
            if candidates:
                freecad = str(sorted(candidates, reverse=True)[0])
        return cls(
            data_dir=Path(text("CAE_DATA_DIR") or "data"),
            google_project=text("GOOGLE_CLOUD_PROJECT"),
            google_location=text("GOOGLE_CLOUD_LOCATION"),
            gemini_model_id=text("GEMINI_MODEL_ID"), adc_path=adc_path,
            freecad_cmd=freecad, mechanical_exe=text("ANSYS_MECHANICAL_EXE"),
            container_runtime=runtime, worker_timeout_seconds=timeout,
        )


def _version(package: str) -> str | None:
    try:
        return importlib.metadata.version(package)
    except importlib.metadata.PackageNotFoundError:
        return None


def _executable(configured: str | None, names: tuple[str, ...]) -> bool:
    if configured:
        return Path(configured).is_file() or shutil.which(configured) is not None
    return any(shutil.which(name) is not None for name in names)


def diagnostics(config: Config) -> dict:
    return {
        "python": {"version": platform.python_version(), "status": "verified_runtime"},
        "packages": {name: _version(name) for name in (
            "pydantic", "pytest", "streamlit", "cadquery", "ansys-mechanical-core",
            "google-genai", "sentence-transformers", "trimesh", "plotly")},
        "freecad": {
            "executable_found": _executable(config.freecad_cmd, ("FreeCADCmd", "FreeCADCmd.exe", "freecadcmd")),
            "execution": "unverified", "note": "Supplied interpreter/API import and save have not been run",
        },
        "mechanical": {
            "executable_found": _executable(config.mechanical_exe, ("AnsysWBU.exe", "ansyswbu")),
            "execution": "unverified", "license": "unverified", "version_compatibility": "unverified",
        },
        "container": {"executable_found": _executable(config.container_runtime, ()),
                      "daemon_and_isolation": "unverified"},
        "vertex": {
            "project_configured": bool(config.google_project),
            "location_configured": bool(config.google_location),
            "model_configured": bool(config.gemini_model_id),
            "adc_file_present": bool(config.adc_path and config.adc_path.is_file()),
            "authentication": "unverified", "model_availability": "unverified",
            "note": "File presence does not prove ADC works; attached/cloud ADC may use other sources",
        },
        "scope": "Presence-only probes. No CAD, FreeCAD, Gemini or solver execution is asserted.",
    }


def diagnostics_json(config: Config | None = None) -> str:
    return json.dumps(diagnostics(config or Config.from_env()), indent=2)

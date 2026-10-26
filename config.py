"""Environment configuration and read-only dependency-presence diagnostics.

Presence is not execution, authentication, compatibility or license validation.
Reports deliberately omit environment values, credential contents and paths.
"""

from __future__ import annotations

from dataclasses import dataclass, field
import importlib.metadata
import json
import os
from pathlib import Path
import platform
import shutil
from typing import Mapping


def local_podman() -> str | None:
    if os.name == "nt":
        candidates = list(Path(__file__).resolve().parent.glob(".tools/podman/**/podman.exe"))
        if candidates:
            return str(sorted(candidates)[-1])
    return None


@dataclass(frozen=True)
class Config:
    data_dir: Path
    google_project: str | None
    google_location: str | None
    gemini_model_id: str | None
    adc_path: Path | None
    freecad_cmd: str | None
    calculix_exe: str | None
    gmsh_exe: str | None
    container_runtime: str
    worker_timeout_seconds: int
    cad_image: str = "agentic-cae-cad:2.6.1"
    llm_provider: str = "vertex"
    gemini_api_key: str | None = field(default=None, repr=False)

    @classmethod
    def from_env(cls, env: Mapping[str, str] | None = None) -> Config:
        if env is None:
            from dotenv import load_dotenv
            load_dotenv(Path(__file__).resolve().parent / ".env", override=False, interpolate=False)
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
        runtime = text("CAE_CONTAINER_RUNTIME") or ("podman" if env is None and local_podman() and not shutil.which("docker") else "docker")
        provider = text("LLM_PROVIDER") or "vertex"
        if provider not in ("vertex", "gemini_developer"):
            raise ValueError("LLM_PROVIDER must be vertex or gemini_developer")
        if runtime not in ("docker", "podman"):
            raise ValueError("Container runtime must be docker or podman")
        freecad = text("FREECAD_CMD")
        if not freecad and os.name == "nt":
            candidates: list[Path] = []
            for parent in (Path(os.environ.get("ProgramFiles", r"C:\Program Files")),
                           Path(os.environ.get("ProgramFiles(x86)", r"C:\Program Files (x86)"))):
                candidates.extend(parent.glob("FreeCAD */bin/freecadcmd.exe"))
            candidates.extend(Path(__file__).parent.glob(".tools/freecad/**/freecadcmd.exe"))
            if candidates:
                freecad = str(max(candidates, key=lambda p: (p.parent.name.lower() == "bin", str(p))))

        def companion(key: str, name: str) -> str | None:
            configured = text(key)
            if configured:
                return configured
            if freecad:
                for parent in (Path(freecad).parent, Path(freecad).parent / "bin"):
                    candidate = parent / (name + (".exe" if os.name == "nt" else ""))
                    if candidate.is_file():
                        return str(candidate)
            return shutil.which(name)
        return cls(
            data_dir=Path(text("CAE_DATA_DIR") or "data"),
            google_project=text("GOOGLE_CLOUD_PROJECT"),
            google_location=text("GOOGLE_CLOUD_LOCATION"),
            gemini_model_id=text("GEMINI_MODEL_ID"), adc_path=adc_path,
            freecad_cmd=freecad, calculix_exe=companion("CALCULIX_CCX", "ccx"),
            gmsh_exe=companion("GMSH_EXE", "gmsh"),
            container_runtime=runtime, worker_timeout_seconds=timeout,
            cad_image=text("CAE_CAD_IMAGE") or "agentic-cae-cad:2.6.1",
            llm_provider=provider, gemini_api_key=text("GEMINI_API_KEY"),
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
            "pydantic", "pytest", "streamlit", "cadquery",
            "google-genai", "sentence-transformers", "trimesh", "plotly")},
        "freecad": {
            "executable_found": _executable(config.freecad_cmd, ("FreeCADCmd", "FreeCADCmd.exe", "freecadcmd")),
            "execution": "unverified", "note": "This presence-only probe does not execute FreeCAD; see STATUS.md for integration evidence",
        },
        "fem": {
            "backend": "FreeCAD FEM / CalculiX",
            "calculix_found": _executable(config.calculix_exe, ("ccx",)),
            "gmsh_found": _executable(config.gmsh_exe, ("gmsh",)),
            "execution": "unverified", "version_compatibility": "unverified",
        },
        "container": {"executable_found": _executable(config.container_runtime, ()) or bool(config.container_runtime == "podman" and local_podman()),
                      "daemon_and_isolation": "unverified"},
        "llm": {"provider": config.llm_provider, "api_key_configured": bool(config.gemini_api_key),
                "execution": "unverified"},
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

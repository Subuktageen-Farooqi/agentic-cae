# Single live Gemini / container / FreeCAD FEM verification

This procedure is implemented but **has not completed on this PC**. Provider and container doubles do not satisfy it. The historical real reference CAD/FEM run is documented separately in [FEM_INTEGRATION_REPORT.md](./FEM_INTEGRATION_REPORT.md).

## Local prerequisites

Restore the locked environment:

```powershell
uv sync --python 3.12 --frozen --extra test --extra cad --extra ui --extra llm --extra fem
.\.venv\Scripts\python.exe -m cli doctor
```

The repository-root `.env` is ignored. Copy [.env.example](./.env.example) only if `.env` does not already exist. Enter the AI Studio key locally, with `LLM_PROVIDER=gemini_developer` and `GEMINI_MODEL_ID=gemini-3.5-flash-lite`. Never paste or print the key. Process environment values take precedence. Official [model details](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) and [pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite), checked 2026-10-27, list stable image input, structured output and a free tier. This verifies the documentation, not account access or quota. No connectivity request is needed before the journey.

This Windows 10 PC has firmware virtualization enabled, but WSL2 is unavailable and the agent process is not elevated. From an **Administrator PowerShell** in the repository:

```powershell
powershell -NoProfile -ExecutionPolicy Bypass -File .\scripts\enable-wsl2.ps1
```

The [script](./scripts/enable-wsl2.ps1) enables WSL and VirtualMachinePlatform with `-NoRestart`. If Windows requests a restart, save work and restart manually, then run the script again. It never restarts Windows itself. See Microsoft's [WSL installation instructions](https://learn.microsoft.com/en-us/windows/wsl/install) and Podman's [Windows requirements](https://podman-desktop.io/docs/installation/windows-install).

The verified portable Podman **5.8.9** client is under ignored `.tools/podman/5.8.9/podman-5.8.9/usr/bin/`. Its official Windows archive SHA-256 is `5829085422452f4159545325acd52764a4e343937c24087b57da3176a7dd70d7`, verified against the GitHub release asset digest. Podman 6 drops Windows 10; use a supported 5.x client here. Software binaries are not committed. Install from the [official release](https://github.com/podman-container-tools/podman/releases/tag/v5.8.9) on another PC.

After WSL2 is healthy, from ordinary PowerShell:

```powershell
$env:PATH = "$PWD\.tools\podman\5.8.9\podman-5.8.9\usr\bin;$env:PATH"
$env:CAE_CONTAINER_RUNTIME = 'podman'
podman machine list
# Initialize only if the named machine does not already exist.
podman machine init --cpus 2 --memory 4096 --disk-size 20 agentic-cae
podman machine start agentic-cae
podman info
podman build -f workers/Dockerfile -t agentic-cae-cad:2.6.1 .
.\.venv\Scripts\python.exe -m cli verify-container
```

Do not recreate an existing machine or overwrite completed job directories. Docker with a running Linux engine is also supported. The application discovers the local portable Podman client when no Docker/runtime override is present. An explicit `CAE_CONTAINER_RUNTIME=docker` takes precedence.

`verify-container` consumes **zero Gemini quota**. It executes repository-authored deterministic `build(params)` through the real restricted generated-code container, verifies nonempty STEP/STL and worker provenance, imports/saves through real FreeCAD, checks 100 x 20 x 10 mm bounds and 20000 mm³ volume, and writes immutable evidence under ignored `.tools/container-verification/projects/<job>/evidence.json`. The live preflight requires that evidence, verifies artifact hashes and checks that the immutable image ID has not changed. A blocked or mocked job cannot satisfy this prerequisite.

## Five-request allocation

| Request | Role | Required outcome |
| --- | --- | --- |
| 1 | Advisor | Actual small PNG sketch and retrieved seed passages; cited response, visible observations, persisted brief update |
| 2 | Design specification | Validated specification preserving the approved brief and dimension provenance |
| 3 | CAD creator | Restricted CadQuery source; actual container execution, FreeCAD checks, app display and exact-artifact acceptance |
| 4 | Analysis planner | Recommendations and validated analysis specification from complete explicit inputs |
| 5, if available | Report explanation | Plain-language sidecar from actual solver data; deterministic numerical report remains authoritative |

No extra planning conversation, connectivity request, automatic repair or retry is permitted. SDK retry attempts are explicitly **1** (the initial request only). The live generation job disables its ordinary one-repair policy. The shared SQLite ledger reserves requests **before** transport, tracks safe returned token usage, and rejects failures, uncertain outcomes, concurrent in-flight requests and requests after the fifth. It survives process restarts. Never delete/reset it to rerun this allowance. Default pytest tests block real SDK client construction; `live_api` tests are excluded by default.

## Prepare, then wait for the user's confirmation

Run ordinary tests first; they consume no live quota:

```powershell
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m examples.live_smoke status
.\.venv\Scripts\python.exe -m examples.live_smoke prepare --live --container-evidence 'PATH_TO_VERIFIED_EVIDENCE.json'
```

The driver creates a fresh persisted brainstorm project and a readable rectangular-cantilever sketch. It executes the four production roles, requires citations/image observations and unchanged fixed dimensions, runs the actual container/FreeCAD pipeline without repair, displays the STL in Streamlit AppTest, and accepts that exact checked artifact. It then proposes reference steel (E 200000 MPa, ν 0.3, density 7900 kg/m³), min-X fixed face, max-X 100 N negative-Z force, and a 3 mm quadratic mesh.

Preparation resolves and displays the actual imported faces without solving. The driver prints the validated specification, resolved face names/centers/normals/areas, region artifact directory and confirmation hash. Open that saved project in the app or inspect its `regions.html` and setup FCStd. **Ask the user to confirm this actual material, force, supports, mesh and highlighted regions. Do not run the next command until they confirm.** A prior request to generate/analyze the design does not replace this gate.

After the user's confirmation of the displayed exact setup:

```powershell
.\.venv\Scripts\python.exe -m examples.live_smoke solve --live --confirm 'EXACT_REVIEWED_CONFIRMATION_HASH'
```

This starts the real FEM/Gmsh/CalculiX solve. It verifies artifact hashes; raw extraction and deterministic report fields must agree exactly, including DAT reaction totals. It uses the existing displacement tolerance **12%** against the matching 0.1 mm Euler–Bernoulli beam estimate and relative reaction residual **< 1e-4**. A generated model qualifies for beam comparison only when actual shape/bounds/full-box volume establish a rectangular prism with matching dimension mapping and end-load/support selectors. A bounding box alone is insufficient.

If request five remains, the driver exercises the explanation role. An optional explanation failure stops the live budget while preserving the successful solver run and deterministic report. Result display checks actual displacement/stress metrics and charts, then reopens the saved project and verifies unchanged jobs and request count. No LLM/CAD/FEA execution is repeated on reopening.

## Evidence and failure handling

The local `.tools/live-smoke/` directory holds the request ledger and immutable project/prepared/solved checkpoints. The persisted project retains brief/history/image bytes, specs, restricted source, container logs/isolation flags, accepted geometry hashes, FreeCAD FCStd and metrics, actual resolved regions, solver input/results/logs, execution names/versions/commands, verification JSON, deterministic report and optional explanation sidecar. All user/native artifacts and the ledger remain ignored by Git.

On any quota, provider, CAD, preparation, solver, comparison or display failure: stop immediately; preserve successful stages and all records; diagnose offline. No automatic retry, fallback live provider, budget reset, technical repair or entire-journey rerun is allowed. Request another live-call allowance from the user only after an offline diagnosis. A successful reference solver test does not certify this live path.

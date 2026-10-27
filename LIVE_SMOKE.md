# Single live Gemini / container / FreeCAD FEM verification

The real restricted container check passed. The first live Gemini advisor request returned but failed reply validation, so this assisted procedure **has not completed on this PC**. The original ledger stopped at one request; provider doubles do not satisfy it. The historical real reference CAD/FEM run is documented separately in [FEM_INTEGRATION_REPORT.md](./FEM_INTEGRATION_REPORT.md).

## Local prerequisites

Restore the locked environment:

```powershell
uv sync --python 3.12 --frozen --extra test --extra cad --extra ui --extra llm --extra fem
.\.venv\Scripts\python.exe -m cli doctor
```

The repository-root `.env` is ignored. Copy [.env.example](./.env.example) only if `.env` does not already exist. Enter the AI Studio key locally, with `LLM_PROVIDER=gemini_developer` and `GEMINI_MODEL_ID=gemini-3.5-flash-lite`. Never paste or print the key. Process environment values take precedence. Official [model details](https://ai.google.dev/gemini-api/docs/models/gemini-3.5-flash-lite) and [pricing](https://ai.google.dev/gemini-api/docs/pricing#gemini-3.5-flash-lite), checked 2026-10-27, list stable image input, structured output and a free tier. This verifies the documentation, not account access or quota. No connectivity request is needed before the journey.

This Windows 10 PC now has working WSL 3.0.3 and an active hypervisor. On a fresh setup, from an administrator session: From an **Administrator PowerShell** in the repository:

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
podman machine set --rootful agentic-cae
podman machine start agentic-cae
podman info
podman build -f workers/Dockerfile -t agentic-cae-cad:2.6.1 .
.\.venv\Scripts\python.exe -m cli verify-container
```

Do not recreate an existing machine or overwrite completed job directories. The project machine uses a rootful Linux engine so cgroup-v2 memory limits work; each CAD container still runs as UID/GID 65532 with no network, read-only root, dropped capabilities and a job-only bind mount. On this PC the machine VHD was moved through `wsl --manage podman-agentic-cae --move` to ignored `.tools/podman-vm/` on D: before the image build. Docker with a running Linux engine is also supported. The application discovers the local portable Podman client when no Docker/runtime override is present. An explicit `CAE_CONTAINER_RUNTIME=docker` takes precedence.

`verify-container` consumes **zero Gemini quota**. It executes repository-authored deterministic `build(params)` through the real restricted generated-code container, verifies nonempty STEP/STL and worker provenance, imports/saves through real FreeCAD, checks 100 x 20 x 10 mm bounds and 20000 mm³ volume, and writes immutable evidence under ignored `.tools/container-verification/projects/<job>/evidence.json`. This PC passed the actual run: one valid 100 x 20 x 10 mm solid, volume 19999.999999999996 mm^3, with STEP/STL/FCStd manifests at `.tools/container-verification/projects/36c4925539524d06bb361ffdc74fb528/evidence.json` (image ID `0a4e62b0ea4e97e6fc4943822b3f3f09c11f2e82e79e3c0bbe185d0412a943cc`). The live preflight requires that evidence, verifies artifact hashes and checks that the immutable image ID has not changed. A blocked or mocked job cannot satisfy this prerequisite.

## Five-request allocation

| Request | Role | Required outcome |
| --- | --- | --- |
| 1 | Advisor | Actual small PNG sketch and retrieved seed passages; cited response, visible observations, persisted brief update |
| 2 | Design specification | Validated specification preserving the approved brief and dimension provenance |
| 3 | CAD creator | Restricted CadQuery source; actual container execution, FreeCAD checks, app display and exact-artifact acceptance |
| 4 | Analysis planner | Recommendations and validated analysis specification from complete explicit inputs |
| 5, if available | Report explanation | Plain-language sidecar from actual solver data; deterministic numerical report remains authoritative |

No extra planning conversation, connectivity request, automatic repair or retry is permitted. SDK retry attempts are explicitly **1** (the initial request only). The live generation job disables its ordinary one-repair policy. The shared SQLite ledger reserves requests **before** transport, tracks safe returned token usage, and rejects failures, uncertain outcomes, concurrent in-flight requests and requests after the fifth. It survives process restarts. Never delete/reset it to rerun this allowance. Default pytest tests block real SDK client construction; `live_api` tests are excluded by default.

## First live attempt and conditional continuation

On 2026-10-27 the first actual `gemini-3.5-flash-lite` advisor request sent the saved sketch bytes and four retrieved passages. The API returned, using 2590 prompt, 782 candidate and 3372 total tokens, but the reply failed the validated advisor contract. The invalid field cannot be recovered because invalid response text was not persisted. The original `.tools/live-smoke/requests.sqlite3` ledger is stopped at **1/5** and must never be reset. Project `ed1f23922ef74359ae657d88547e5cdb` retains its original intake, PNG, brief and user message; no assistant reply, live CAD or FEM result was created.

Offline diagnosis found that JSON MIME was set without an SDK response schema. The advisor now supplies a schema that the installed Google SDK can transform locally. Its wire dimension field remains permissive only because that SDK does not support Pydantic's `exclusiveMinimum`; the host still applies the authoritative strict Dimension contract. The response-schema path and original records are checked offline. This is a mitigation, not a claim that another live reply has succeeded.

**Only after the user explicitly grants a new allowance of at most four live generation requests**, continue the **same saved project** with:

```powershell
.\.venv\Scripts\python.exe -m examples.live_smoke recover --live --container-evidence '.tools/container-verification/projects/36c4925539524d06bb361ffdc74fb528/evidence.json'
```

Recovery refuses to modify the original stopped ledger, creates a separate maximum-four-request ledger, resends the preserved image and retrieved knowledge for one advisor request, then allocates one request each to the design spec, CAD code and analysis spec. It does not rerun intake, use mocked model responses, automatically repair CAD, or consume an extra explanation call. Across both ledgers the hard maximum remains **five requests**. If any stage fails, stop again and diagnose offline before seeking another allowance.

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

In a fresh successful five-call run, if request five remains, the driver exercises the explanation role. In the one-time recovery above, the fifth cumulative request is allocated to the analysis specification and no AI explanation call is made; the deterministic report remains required. An optional explanation failure stops the live budget while preserving the successful solver run and deterministic report. Result display checks actual displacement/stress metrics and charts, then reopens the saved project and verifies unchanged jobs and request count. No LLM/CAD/FEA execution is repeated on reopening.

## Evidence and failure handling

The local `.tools/live-smoke/` directory holds the request ledger and immutable project/prepared/solved checkpoints. The persisted project retains brief/history/image bytes, specs, restricted source, container logs/isolation flags, accepted geometry hashes, FreeCAD FCStd and metrics, actual resolved regions, solver input/results/logs, execution names/versions/commands, verification JSON, deterministic report and optional explanation sidecar. All user/native artifacts and the ledger remain ignored by Git.

On any quota, provider, CAD, preparation, solver, comparison or display failure: stop immediately; preserve successful stages and all records; diagnose offline. No automatic retry, fallback live provider, budget reset, technical repair or entire-journey rerun is allowed. Request another live-call allowance from the user only after an offline diagnosis. A successful reference solver test does not certify this live path.

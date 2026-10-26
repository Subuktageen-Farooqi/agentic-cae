# agentic-cae

A local prototype for mechanical design: idea → optional RAG engineering advice → structured brief/spec → CadQuery → FreeCAD → checks and feedback → confirmed analysis → FreeCAD FEM → evidence-based report.

**The real CAD → app review → FreeCAD FEM → CalculiX → displayed results/report path has run on this PC.** M7 adds actual STL preview/downloads, artifact-bound acceptance, bounded feedback revisions and all three preserved restart choices. The app now supports explicit reference-steel static-analysis input, actual face review, confirmation, background solving and result/report display. M6's live Gemini and actual generated-code container path remain blocked by credentials/runtime, so live assisted feedback regeneration is not claimed. See [STATUS.md](./STATUS.md), [PLAN.md](./PLAN.md), [REQUIREMENTS_CHECKLIST.md](./REQUIREMENTS_CHECKLIST.md), [PROJECT_SPEC.md](./PROJECT_SPEC.md) and the detailed [real integration report](./FEM_INTEGRATION_REPORT.md).

## Verified behavior and current limits

The latest full verification on 2026-10-26 passed **163 tests with no skips**, including real CadQuery exports, FreeCAD import/save, a FreeCAD FEM/CalculiX solve, and Streamlit interaction tests. The reference 100 x 20 x 10 mm steel cantilever under a 100 N tip force displaced **0.0996479292 mm**, compared with the **0.1000000000 mm** beam estimate; extracted reactions balance the applied force. Saved result artifacts, hashes and the FEM document were also checked. These are integration-example results, not approval of a user design.

| Area | Current boundary |
| --- | --- |
| Real FEM execution | Linear static, sourced reference steel, planar min/max-X face selectors; actual region review/confirmation through the app and CLI |
| Engineering conclusions | Preliminary single-mesh results; nodal plots; no mesh convergence, fatigue, durability or certified material claim |
| Assisted generation | Specification/source/job/repair behavior is locally tested with labeled doubles; live Gemini and the generated-code container have not run here |
| External setup | Vertex project/location/model/ADC and a running Linux Docker/Podman engine with the CAD image are still required |
| Remaining application work | M8 advisor-led analysis recommendations and broader material/selector/input coverage; live assisted revision/container verification and final M9 handoff |

## Run the verified foundation (Windows PowerShell)

The current checkout has a repository-local Python installation and virtual environment; it does not require activating a global Python or changing the registry:

```powershell
.\.venv\Scripts\python.exe -m cli doctor
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m cli projects
.\.venv\Scripts\python.exe -m cli --data-dir data demo-cantilever
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
.\.venv\Scripts\python.exe -m cli knowledge-update
.\.venv\Scripts\python.exe -m cli knowledge-query 'waterjet versus CNC bracket manufacturing'
```

On a fresh checkout with Python 3.12 already installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test,cad,ui,llm,fem]'
.\.venv\Scripts\python.exe -m cli doctor
.\.venv\Scripts\python.exe -m pytest -q
```

With uv installed, restore the locked environment directly:

```powershell
uv sync --python 3.12 --frozen --extra test --extra cad --extra ui --extra llm --extra fem
.\.venv\Scripts\python.exe -m pytest -q
```

Tested versions are recorded in [STATUS.md](./STATUS.md); the uv lockfile pins resolved dependencies. On Linux/macOS, equivalent environment commands use `.venv/bin/python`.

## Continue on another PC

```powershell
git clone https://github.com/Subuktageen-Farooqi/agentic-cae
Set-Location agentic-cae
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test,cad,ui,llm,fem]'
.\.venv\Scripts\python.exe -m cli knowledge-update
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

Install FreeCAD for the verified CAD path. Set its command explicitly if discovery does not find it:

```powershell
$env:FREECAD_CMD = 'C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe'
.\.venv\Scripts\python.exe -m cli --data-dir data demo-cantilever
```

This PC uses the official portable [FreeCAD 1.1.4 Windows release](https://github.com/FreeCAD/FreeCAD/releases/tag/1.1.4), extracted under `.tools/freecad/`. Its bundled Gmsh 4.15.0 and CalculiX 2.22 are discovered beside the `bin/freecadcmd.exe` executable. The downloaded 7z SHA-256 was verified against the release checksum: `4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d`.

## FreeCAD FEM review and solve

For the complete real app-driven verification, use:

```powershell
.\.venv\Scripts\python.exe -m cli --data-dir data verify-fem-e2e
```

This drives actual app controls, generates fresh repository-authored reference CAD, displays the STL, accepts its exact STEP hash, reviews/confirms the actual selected faces, meshes/solves using installed tools, displays the numerical fields/report and reopens the persisted session without another solve. No provider, mesher or solver double is injected. It is not a live Gemini/container test. [FEM_INTEGRATION_REPORT.md](./FEM_INTEGRATION_REPORT.md) records executable versions, commands, logs, result files and numerical comparisons.

For manual app use, open **Real integration example** in the sidebar and select **Generate reference cantilever**. Review/accept the actual solid, explicitly select the reference setup, prepare regions, inspect the highlighted faces, then confirm and run. The report screen contains interactive result fields, numerical checks and downloads. An accepted custom design can use the same limited static setup if its material and planar face selectors are supported.

The deterministic demo prepares the actual STEP, source-based generic steel material, mesh settings, loads/supports and imported face selections. It exports `regions.html` with the actual selected face geometry and a saved `setup.FCStd`. Preparation does not solve.

```powershell
$demo = .\.venv\Scripts\python.exe -m cli --data-dir data demo-fem | ConvertFrom-Json
$demo.review_regions
$demo.spec
# Inspect regions.html, analysis_spec.md and setup.FCStd before confirming.
.\.venv\Scripts\python.exe -m cli fem-solve --step $demo.step --spec $demo.spec --preparation $demo.preparation --confirm $demo.confirmation_hash
```

The confirmation binds the complete analysis specification, geometry hash, actual region geometry and setup FCStd. Changed inputs/geometry invalidate confirmation. Existing runs cannot be overwritten. Generic commands are also available: `fem-prepare --spec FILE --step FILE --output NEW_DIRECTORY`, then `fem-solve` as above.

The fixed FreeCAD FEM template creates the mesh, writes/runs CalculiX, imports actual FRD results and reads support reaction totals from DAT output. It writes `analysis.FCStd`, `results.json`, `report.md`, nodal displacement/stress images, input/result files, logs and a hash/size completion manifest. The allowlisted reference material uses FreeCAD's [Steel-Generic card](https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Material/Resources/Materials/Standard/Metal/Steel/Steel-Generic.FCMat): E = 200000 MPa, Poisson ratio 0.3, density 7900 kg/m³. This does not certify actual stock; other materials require an explicitly sourced allowlist addition. Results are preliminary single-mesh values; no fatigue, convergence or durability claim is made.

## Generated-design execution

The automatic route starts M6 once when Vertex is configured. A durable background job freezes a brief, persists matching JSON/Markdown, generates `build(params)` source and executes only through Docker/Podman. The trusted worker owns imports and exports. One technical repair uses actual code/check failures; unavailable dependencies do not consume that repair budget or a user rejection. A blocked/failed job offers an explicit new-attempt retry. Reopening a session does not rerun existing pending/running/interrupted work.

M7 displays the real STL, parameters, assumptions, check coverage and downloads. Acceptance is bound to the current revision/hash and cannot pass altered artifacts or failed mandatory checks. The first user rejection records any supported feedback mode and queues one new candidate in the same attempt; the second preserves both revisions and offers retry-from-approved-brief, brainstorming-with-feedback, or original-idea restart. These create fresh attempt IDs/counters without replacing original intake or artifacts. Feedback-based brief/spec changes retain unaffected requirements; hard/soft requirement changes require the existing ID and an exact quote from explicit user feedback. The actual LLM/container regeneration remains unverified until external setup is available.

AST validation is defense in depth, not isolation. Build the image on a running Linux container engine:

```powershell
docker build -f workers/Dockerfile -t agentic-cae-cad:2.6.1 .
```

The generated-code container has no network or credentials, a read-only root, a non-root user, dropped capabilities, CPU/memory/process/time limits and only its own input/output directory mounted. The Docker context allowlist excludes credentials and local artifacts. The image/container path is implemented but **has not run on this PC**, where Docker/Podman is absent.

## Vertex configuration

For Vertex Gemini, enable the Vertex AI API, establish Application Default Credentials locally, and set the non-secret identifiers:

```powershell
gcloud auth application-default login
$env:GOOGLE_CLOUD_PROJECT = 'your-project-id'
$env:GOOGLE_CLOUD_LOCATION = 'global'
$env:GEMINI_MODEL_ID = 'gemini-3.8-flash'
```

Do not copy ADC JSON into the repository. Authenticate independently or transfer credentials through an approved secret channel.

### State not stored in Git

- `.venv/` and `.tools/`: the Python environment, portable uv executable/cache, and installed packages. Recreate them from `pyproject.toml` and `uv.lock`.
- `.env`, `.streamlit/secrets.toml`, ADC JSON, private keys and certificate containers: intentionally ignored. No such credential file was present during the handoff scan.
- `data/workflow.sqlite3`: local workflow/session database. It is required only to resume this PC's existing sessions; a fresh checkout creates a new database.
- `data/projects/`: original intake copies, uploaded images, briefs, STEP/STL/FCStd, parameters, manifests, metrics and logs. It is ignored because it can contain user data and generated binaries. Copy it separately only if exact sessions/artifacts must move.
- System software: Git, Python 3.12, FreeCAD with FEM/Gmsh/CalculiX, and Google Cloud CLI for convenient ADC setup. Portable FreeCAD and the Python environment must be recreated on another PC; Docker/Podman is still absent here.
- FEM software: FreeCAD FEM, Gmsh and CalculiX are required for real analysis. No commercial solver license is needed. An enabled Google Cloud project, Vertex permissions/credits, model configuration and ADC are required for live Gemini.

The earlier PC's handoff recorded a 106,496-byte SQLite database and a 29,739-byte deterministic CAD demo; that local state was not part of the checkout. This PC has newly generated FEM demonstration state, also excluded from Git. GitHub receives source, tests, documentation, dependency manifests and the curated knowledge collection/index; environments, credentials, databases, CAD/FEA results and build outputs must be recreated or transferred separately. See [STATUS.md](./STATUS.md) for the verified milestone and next action.

## Configuration and dependency discovery

[.env.example](./.env.example) documents process environment variables. The foundation reads the process environment; `.env` is not automatically loaded. `doctor` checks presence and package versions without reading credential contents, printing configured values, launching software or claiming authentication/license validity.

- `CAE_DATA_DIR`: local SQLite and artifact root (default `data`). Use a local filesystem supporting hard links, such as NTFS. Atomic no-clobber publication uses a temporary file, flush/fsync and a hard link. An unsupported filesystem fails explicitly.
- `FREECAD_CMD`: installed FreeCADCmd executable. Its own Python environment will import and save STEP through the FreeCAD API in M2.
- `CALCULIX_CCX`, `GMSH_EXE`: optional executable overrides for CalculiX and Gmsh. Discovery checks beside FreeCADCmd and PATH. FreeCAD FEM performs actual region resolution, meshing and solving; no solver-client Python package is required.
- `CAE_CONTAINER_RUNTIME`: `docker` or `podman`; `CAE_CAD_IMAGE`: the locally built CAD image. A running Linux engine is required; an ordinary subprocess is not a sandbox.
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GEMINI_MODEL_ID`: Vertex Gemini configuration. ADC will authenticate; no OpenAI key is used. Do not paste credentials into chat or commit them. Official SDK/model documentation has been checked; project-specific access still requires a live request.

The provider uses `google-genai` with an explicit Vertex client, API `v1`, bounded HTTP timeout and byte-bearing `Part.from_bytes` image parts. Client initialization/authentication errors enter the same blocked fallback as request errors. See the [SDK documentation](https://googleapis.github.io/python-genai/). The configurable example is now `gemini-3.8-flash`, a documented [multimodal model](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/gemini/3-8-flash). Google's [lifecycle table](https://docs.cloud.google.com/gemini-enterprise-agent-platform/models/model-versions) lists the previous `gemini-2.5-flash` example as retired on 2026-10-20. Documentation availability does not prove this project's access, permissions or successful model execution; a live ADC-authenticated call remains unverified.

## Knowledge index and advisor boundaries

The four initial documents under `data/knowledge/sources/` are explicitly labeled authored seed notes. They contain general decision context without fabricated numerical limits. `knowledge-update` chunks them and atomically writes `data/knowledge/index.json`, using normalized local TF-IDF vectors plus BM25. This is a lexical hybrid rather than a neural semantic model. Every result retains source kind, local reference, section, date, topic and available material/process/equipment/supplier context.

When Vertex is unavailable, the UI labels the response `local_retrieval_only` and displays extractive passages with chunk citations. It does not present that text as Gemini output. A live Vertex call is required before multimodal interpretation can be marked verified.

Pure tests run without FreeCAD. Integration tests execute installed CadQuery, FreeCAD and CalculiX; they explicitly skip when dependencies are absent. Provider/container doubles are labeled and never count as a live Gemini request or a sandboxed build.

## Persistence and interruption behavior

`storage.Store` creates `workflow.sqlite3` and uniquely identified project/upload/brief/attempt/revision directories under the configured data root. Original intake, image metadata, versioned records and audit events are append-only in SQLite. Bytes are integrity-checked against stored SHA-256 values. Frozen brief versions are separate from original intake. Optimistic concurrency rejects stale advisor responses instead of overwriting direct edits.

Transactions publish files before indexing them. A crash can leave an unreferenced file, but not a committed record referencing a partly published file. There is no automatic deletion of artifacts. New writes never overwrite existing files, including candidate or accepted geometry paths. Windows paths use extended absolute path handling internally for deep revision trees.

An idempotency key identifies a job's kind and canonical input payload. Reruns return the original job; competing workers can claim it once. Reopening storage never requeues pending/running/finished work automatically. M6/M7 supply background generation, geometry gates, bounded feedback/restarts and exact-artifact acceptance. FEM prepare/solve jobs require separate actual-region confirmation. Database schema v1 upgrades additively to v2; original records/images remain readable and intact. Transient Windows SQLite connection-setup errors are retried only before the transaction body, never by replaying a commit.

Inspect jobs before recovering an interrupted worker:

```powershell
.\.venv\Scripts\python.exe -m cli jobs PROJECT_ID
# Only after checking that the named old worker has stopped:
.\.venv\Scripts\python.exe -m cli recover --owner OLD_WORKER_ID --owner-stopped
```

Recovery marks that owner's running jobs `interrupted`; it never executes them. Inspect artifacts and logs before explicitly submitting a new job key. Other live owners are untouched.

## Verification boundaries and forthcoming demos

Foundation tests use real local files and SQLite, including actual PNG bytes. Solver-result fixtures are explicitly labeled `test_fixture`; no solver is invoked. The contracts reject unavailable solvers carrying fabricated results and reject stale geometry/spec bindings.

The real app and solver tests verify displacement against beam theory and extracted reactions against the applied force. Run `pytest -m real_integration` for those cases. M7 review/transaction tests use explicitly synthetic artifacts; M6 includes labeled provider/container doubles. Neither is evidence of a live model or sandbox execution. Live Gemini, actual container execution, broader M8 analysis advising and the final M9 assisted journey remain pending or blocked. The trusted reference CAD/FEM app journey is verified; the complete live-assisted product is not yet verified end to end.

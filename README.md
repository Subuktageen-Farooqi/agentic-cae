# agentic-cae

A local prototype for mechanical design: idea → optional RAG engineering advice → structured brief/spec → CadQuery → FreeCAD → checks and feedback → confirmed analysis → Ansys → evidence-based report.

**Current implementation: M1, M2, M4, and the local portion of M5 are verified; M3 solver execution and live Vertex remain blocked.** Contracts, durable storage/workflow, real deterministic CadQuery/FreeCAD, geometry checks, offline analysis/reporting, Streamlit intake/routes, persistent local RAG, and the living brief are available. The Vertex Gemini adapter exists, but no live request is claimed without configured ADC. No vision response or Ansys solve has been verified. See [STATUS.md](./STATUS.md), [PLAN.md](./PLAN.md), [REQUIREMENTS_CHECKLIST.md](./REQUIREMENTS_CHECKLIST.md) and the authoritative [PROJECT_SPEC.md](./PROJECT_SPEC.md).

## Run the verified foundation (Windows PowerShell)

The current checkout has a repository-local Python installation and virtual environment; it does not require activating a global Python or changing the registry:

```powershell
.\.venv\Scripts\python.exe -m cli doctor
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m cli projects
.\.venv\Scripts\python.exe -m cli --data-dir data demo-cantilever
.\.venv\Scripts\python.exe -m streamlit run app.py
.\.venv\Scripts\python.exe -m cli knowledge-update
.\.venv\Scripts\python.exe -m cli knowledge-query 'waterjet versus CNC bracket manufacturing'
```

On a fresh checkout with Python 3.12 already installed:

```powershell
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test,cad,ui,llm]'
.\.venv\Scripts\python.exe -m cli doctor
.\.venv\Scripts\python.exe -m pytest -q
```

Alternatively bootstrap entirely inside this checkout using portable uv:

```powershell
New-Item -ItemType Directory -Force .tools | Out-Null
Invoke-WebRequest 'https://github.com/astral-sh/uv/releases/download/0.9.7/uv-x86_64-pc-windows-msvc.zip' -OutFile .tools\uv.zip
Expand-Archive .tools\uv.zip -DestinationPath .tools\uv -Force
$env:UV_PYTHON_INSTALL_DIR = Join-Path (Get-Location) '.tools\python'
$env:UV_CACHE_DIR = Join-Path (Get-Location) '.tools\cache'
.\.tools\uv\uv.exe python install 3.12 --no-bin --no-registry
.\.tools\uv\uv.exe sync --extra test --extra cad --extra ui --extra llm --frozen
.\.venv\Scripts\python.exe -m pytest -q
```

Tested versions are recorded in [STATUS.md](./STATUS.md); the uv lockfile pins resolved dependencies. On Linux/macOS, equivalent environment commands use `.venv/bin/python`.

## Continue on another PC

```powershell
git clone https://github.com/Subuktageen-Farooqi/agentic-cae
Set-Location agentic-cae
python -m venv .venv
.\.venv\Scripts\python.exe -m pip install -e '.[test,cad,ui,llm]'
.\.venv\Scripts\python.exe -m cli knowledge-update
.\.venv\Scripts\python.exe -m pytest -q
.\.venv\Scripts\python.exe -m streamlit run app.py
```

Install FreeCAD for the verified CAD path. Set its command explicitly if discovery does not find it:

```powershell
$env:FREECAD_CMD = 'C:\Program Files\FreeCAD 1.1\bin\freecadcmd.exe'
.\.venv\Scripts\python.exe -m cli --data-dir data demo-cantilever
```

For Vertex Gemini, enable the Vertex AI API, establish Application Default Credentials locally, and set the non-secret identifiers:

```powershell
gcloud auth application-default login
$env:GOOGLE_CLOUD_PROJECT = 'your-project-id'
$env:GOOGLE_CLOUD_LOCATION = 'global'
$env:GEMINI_MODEL_ID = 'gemini-2.5-flash'
```

Do not copy ADC JSON into the repository. Authenticate independently or transfer credentials through an approved secret channel.

### State not stored in Git

- `.venv/` and `.tools/`: the Python environment, portable uv executable/cache, and installed packages. Recreate them from `pyproject.toml` and `uv.lock`.
- `.env`, `.streamlit/secrets.toml`, ADC JSON, private keys and certificate containers: intentionally ignored. No such credential file was present during the handoff scan.
- `data/workflow.sqlite3`: local workflow/session database. It is required only to resume this PC's existing sessions; a fresh checkout creates a new database.
- `data/projects/`: original intake copies, uploaded images, briefs, STEP/STL/FCStd, parameters, manifests, metrics and logs. It is ignored because it can contain user data and generated binaries. Copy it separately only if exact sessions/artifacts must move.
- System software: Git, Python 3.12, FreeCAD 1.1.x for the verified CAD path, and Google Cloud CLI for convenient ADC setup. Docker/Podman and Ansys Mechanical were not installed or verified on the source PC.
- Licenses/services: installed and licensed Ansys Mechanical is required for the blocked real solver; an enabled Google Cloud project, Vertex permissions/credits, model configuration and ADC are required for live Gemini.

At handoff, ignored local state contained one 106,496-byte SQLite database and one 29,739-byte deterministic demo project with STEP, STL, FCStd, source, parameters, metrics, manifests and logs. No persistent user-uploaded images were present in the workspace data tree. See [STATUS.md](./STATUS.md) for the exact verified milestone and next action.

## Configuration and dependency discovery

[.env.example](./.env.example) documents process environment variables. The foundation reads the process environment; `.env` is not automatically loaded. `doctor` checks presence and package versions without reading credential contents, printing configured values, launching software or claiming authentication/license validity.

- `CAE_DATA_DIR`: local SQLite and artifact root (default `data`). Use a local filesystem supporting hard links, such as NTFS. Atomic no-clobber publication uses a temporary file, flush/fsync and a hard link. An unsupported filesystem fails explicitly.
- `FREECAD_CMD`: installed FreeCADCmd executable. Its own Python environment will import and save STEP through the FreeCAD API in M2.
- `ANSYS_MECHANICAL_EXE`: installed Mechanical executable. Version and license checks, PyMechanical compatibility, named selections and real static solves follow in M3.
- `CAE_CONTAINER_RUNTIME`: `docker` or `podman`. A working isolated runtime will be required for generated CadQuery execution; an ordinary subprocess is not a sandbox.
- `GOOGLE_CLOUD_PROJECT`, `GOOGLE_CLOUD_LOCATION`, `GEMINI_MODEL_ID`: Vertex Gemini configuration. ADC will authenticate; no OpenAI key is used. Do not paste credentials into chat or commit them. Current SDK/model availability will be checked before provider implementation in M5.

The M5 provider uses `google-genai` with an explicit Vertex client and API `v1`, following the [official Vertex quickstart](https://docs.cloud.google.com/vertex-ai/generative-ai/docs/start/quickstart) and [Google Gen AI Python SDK documentation](https://googleapis.github.io/python-genai/). Local images are sent as byte-bearing `Part.from_bytes` objects. `gemini-2.5-flash` is the documented baseline in [.env.example](./.env.example), while the model remains configurable. Establish local ADC with `gcloud auth application-default login`; a configured filename alone does not prove authentication or model availability.

## Knowledge index and advisor boundaries

The four initial documents under `data/knowledge/sources/` are explicitly labeled authored seed notes. They contain general decision context without fabricated numerical limits. `knowledge-update` chunks them and atomically writes `data/knowledge/index.json`, using normalized local TF-IDF vectors plus BM25. This is a lexical hybrid rather than a neural semantic model. Every result retains source kind, local reference, section, date, topic and available material/process/equipment/supplier context.

When Vertex is unavailable, the UI labels the response `local_retrieval_only` and displays extractive passages with chunk citations. It does not present that text as Gemini output. A live Vertex call is required before multimodal interpretation can be marked verified.

Mechanical is not a dependency of the available test suite. CadQuery/FreeCAD integration tests execute the real installed tools. Synthetic solver fixtures are explicitly labeled and are not integration evidence.

## Persistence and interruption behavior

`storage.Store` creates `workflow.sqlite3` and uniquely identified project/upload/brief/attempt/revision directories under the configured data root. Original intake, image metadata, versioned records and audit events are append-only in SQLite. Bytes are integrity-checked against stored SHA-256 values. Frozen brief versions are separate from original intake. Optimistic concurrency rejects stale advisor responses instead of overwriting direct edits.

Transactions publish files before indexing them. A crash can leave an unreferenced file, but not a committed record referencing a partly published file. There is no automatic deletion of artifacts. New writes never overwrite existing files, including candidate or accepted geometry paths. Windows paths use extended absolute path handling internally for deep revision trees.

An idempotency key identifies a job's kind and canonical input payload. Reruns return the original job; competing workers can claim it once. Reopening storage never requeues pending/running/finished work automatically. The actual executor and stage-specific success gates follow in later milestones.

Inspect jobs before recovering an interrupted worker:

```powershell
.\.venv\Scripts\python.exe -m cli jobs PROJECT_ID
# Only after checking that the named old worker has stopped:
.\.venv\Scripts\python.exe -m cli recover --owner OLD_WORKER_ID --owner-stopped
```

Recovery marks that owner's running jobs `interrupted`; it never executes them. Inspect artifacts and logs before explicitly submitting a new job key. Other live owners are untouched.

## Verification boundaries and forthcoming demos

Foundation tests use real local files and SQLite, including actual PNG bytes. Solver-result fixtures are explicitly labeled `test_fixture`; no solver is invoked. The contracts reject unavailable solvers carrying fabricated results and reject stale geometry/spec bindings.

The deterministic cantilever CAD/FreeCAD command, Streamlit intake/routes, and local knowledge ingestion/query now exist and are verified. M3's actual licensed Mechanical solve remains blocked; offline analysis gates, numerical sanity functions and deterministic reports exist. Live Gemini and the M6–M9 generated-design, feedback and end-to-end stages remain pending or blocked in the checklist. The complete product is not currently working.

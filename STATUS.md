# Project status

Updated: 2026-10-26. Current milestone: **M6 — specification and generated CAD (next)**.

## Authority and repository baseline

- Read the complete [PROJECT_SPEC.md](./PROJECT_SPEC.md), 1,010 lines, before implementation. No scope changes authorized or made.
- Initial repository: README, MIT license, git metadata, user-supplied untracked specification. No application or tests. Preserve original specification.
- See [PLAN.md](./PLAN.md) for ordered milestones and [REQUIREMENTS_CHECKLIST.md](./REQUIREMENTS_CHECKLIST.md) for traceability. Unrelated ideas belong in [BACKLOG.md](./BACKLOG.md).

## Cross-PC handoff snapshot

- Intended Git state: source, tests, project/specification records, four authored knowledge sources, knowledge index, dependency manifests/lockfile and secret-free configuration example.
- Completed: M1 contracts/persistence/workflow verified; M2 actual CadQuery 2.6.1 and FreeCADCmd/API 1.1.4 verified; M3 offline analysis/reporting verified while Mechanical is blocked; M4 Streamlit intake/routes verified; M5 local RAG/living brief verified while live Vertex is blocked.
- Current problems: no Docker/Podman generated-code sandbox; no Ansys installation/license/PyMechanical compatibility; no configured Vertex project/location/model/ADC; no live Gemini image interpretation; no actual solver regions/solve; M6 has not started.
- Latest verification: **116 tests passed** in 20.68 s on Python 3.12.12. Actual CadQuery/FreeCAD integration tests ran. `git diff --check` passed. Secret filename/content scans found no credential file or recognized private-key/API-token pattern in the intended tree. No intended Git file exceeded 1 MiB; the largest is `uv.lock` at 299,937 bytes.
- Exact next action: clone/pull this handoff commit, recreate all four extras (`test,cad,ui,llm`), run `python -m cli knowledge-update` and `python -m pytest -q`, reread §§8–12 and 23–24 of [PROJECT_SPEC.md](./PROJECT_SPEC.md), then begin M6 deterministic DesignSpec JSON/Markdown and generated-CAD validation. Never execute generated code outside the required container boundary.

### Not stored in Git

- Credentials/secrets: none found in this repository. `.env`, Streamlit secrets, ADC JSON, PEM/key/P12/PFX files are ignored. Authenticate ADC independently on the next PC.
- Local database: ignored `data/workflow.sqlite3`, 106,496 bytes. It contains local session/job/state records and is unnecessary for a fresh start.
- Local artifacts: ignored `data/projects/4a4fb88dcc2947e88341886714d07f58/`, 12 files totaling 29,739 bytes. It contains deterministic demo intake/brief, STEP, STL, FCStd, CadQuery source, parameters, metadata, metrics, summary and logs. Copy separately only to preserve that exact evidence bundle.
- Uploaded images: no persistent uploaded-image file currently exists under workspace `data/projects/`; future uploads remain local there by default.
- Local environments/caches: `.venv/`, `.tools/`, `.pytest_cache/`, bytecode and package metadata are ignored and must be recreated.
- Installed software: project-local Python 3.12.12 environment and system FreeCAD 1.1.4. Git is required. Google Cloud CLI supports the documented ADC command. Docker/Podman and Ansys were absent.
- External access/licenses: GitHub credentials for pushing; Google Cloud project/Vertex permissions/credits/ADC for Gemini; Ansys Mechanical installation and license for the real solver.

## M1 boundary — contracts, persistence and orchestration: verified

- What works: strict required contracts; immutable intake/images; append-only versioned records/audit; optimistic concurrency; idempotent single-claim jobs; explicit interrupted-job recovery; no-clobber integrity-checked artifacts; secret-free diagnostics.
- Actual verification: Python 3.12.12, Pydantic 2.14.1, pytest 9.1.1. **77 tests passed** using real temporary SQLite/files, actual PNG bytes, concurrent claims/edits, restart, tamper, stale-action and interruption cases. CLI diagnostics/help/projects and `git diff --check` passed.
- Blocked/unverified: M1 made no UI, LLM, RAG, CAD or solver claim.
- Manual check: review [.env.example](./.env.example) and [README.md](./README.md) persistence/recovery behavior.
- Next milestone selected: M2 deterministic CadQuery/FreeCAD integration.

## M2 boundary — deterministic CAD, FreeCAD and geometry rules: verified

- What works: repository-authored `build(params)` creates a real 100 × 20 × 10 mm solid with CadQuery 2.6.1; trusted worker exports and hashes STEP/STL/source/parameters/metadata/logs without overwrites. FreeCADCmd 1.1.4 imports STEP through its API, saves a real FCStd and returns validity/solid/volume/area/bounding metrics. Geometry and tolerance rules are real; four future checks visibly return `NOT_IMPLEMENTED`.
- Actual verification: **91 tests passed** in 12.08 s, including real CadQuery and FreeCAD executions. Separate demo project `4a4fb88dcc2947e88341886714d07f58`, attempt `ae167cc861b546a4a7c4cbeda23133f7`, revision `163cb34ded514a74851fb68350d9d234` succeeded. STEP SHA-256 `7a6c094538ab78e8f7043a4b38cacceee7153f10f5fa1587bb04879726886650`. FreeCAD found one valid nonempty solid, 19,999.999999999996 mm³ volume, 6,400 mm² area and exact 100 × 20 × 10 mm bounds; all eight mandatory rules passed.
- Actual artifacts: `model.step` 15,457 bytes, `preview.stl` 684 bytes, `model.FCStd` 2,116 bytes, source/parameters/metadata/metrics/logs/summary in ignored local `data/`. Negative cases verified missing parameters, overwrite prevention, missing FreeCAD, geometry failures and missing/altered artifacts.
- Blocked/unverified: Docker/Podman is absent, so this trusted deterministic worker is not a generated-code sandbox. Interactive preview is later UI work. Technical repair counter validation exists; generated-code repair is M6. FCStd is imported geometry; source and parameters remain parametric.
- Manual check: optionally open the latest FCStd/STL found under the recorded revision directory. This is visual review; actual metrics are already verified.
- Next milestone: M3 selectors, fixed Mechanical boundary, sanity checks and reporting. Mechanical installation/version/license/PyMechanical remain unavailable.

## M3 boundary — deterministic Mechanical and reporting: blocked execution, independent parts verified

- What now works: analysis input completeness, explicit-unit/hash/selector-overlap gates; min/max-X selector intent labeled unresolved until Mechanical; elementary cantilever displacement and reaction-equilibrium functions; deterministic success/failure reports; stale result rejection; a Mechanical adapter that returns `BLOCKED` without numeric fields when the executable/PyMechanical/compatibility is unavailable.
- What was tested: **99 tests passed** in 11.79 s. New tests cover geometry-hash changes, missing inputs, overlapping regions, selector coordinates/normals, blocked results without fabricated numbers, exact absent-criterion wording, preliminary single-mesh/constraint warnings, beam-theory units and reaction balance.
- Blocked/unverified: `C:\Program Files\ANSYS Inc` and `C:\Program Files\ANSYSEM` do not exist and no Mechanical executable or PyMechanical package was found. No region was resolved inside Mechanical, no named selection/mesh/solve/contour/project was created, and no numerical solver value is claimed. A verified material allowlist awaits authoritative runtime/material data.
- Manual check: none for the blocked adapter. When Ansys is installed, the user must inspect actual highlighted support/load regions before confirming the solve.
- Next milestone: per §22, continue independent M4 intake/routes/application work while preserving M3 as blocked. Revisit M3 when installed Mechanical version and license are available.

## M4 boundary — intake, routes and application shell: verified

- What now works: Streamlit starts; incomplete intake captures idea/purpose/hard and soft requirements/dimensions with units/material/manufacturing and multiple images; project and bytes persist immediately; sidebar recovers sessions. Exact route titles/descriptions are present. Both routes produce the same validated `DesignBrief`; automatic mode records assumptions and enters `SPEC_GENERATION` without extra confirmation. Advisor mode opens an editable versioned brief and clearly labels the not-yet-connected M5 advisor. Generate/switch actions freeze and advance the brief without starting fake jobs.
- What was tested: **105 tests passed** in 17.51 s. Streamlit AppTest drove minimal intake through both route buttons and verified automatic state/assumptions plus advisor workspace/blocked notice. App startup succeeded headlessly at port 8765 and was stopped after the probe. Pure tests cover dimension parsing and known-input preservation; storage restart tests cover real PNG bytes and idempotent jobs.
- Blocked/unverified: RAG/Gemini chat and actual vision payload are M5 and remain blocked by missing Vertex configuration/ADC. Specification generation is M6; UI labels it unavailable and does not enqueue a fake generation. Interactive STL preview remains M7.
- Manual check: run `.\.venv\Scripts\python.exe -m streamlit run app.py`, submit an incomplete idea with images, exercise both routes, then reopen the session from the sidebar.
- Next milestone: M5 curated real sources, repeatable local index, cited retrieval and shared-brief updates. Implement independent RAG work first; live Gemini vision remains blocked until Vertex configuration/ADC is supplied.

## M5 boundary — RAG and multimodal living brief: local path verified, live Vertex blocked

- What now works: four real authored seed documents cover all required initial knowledge topics without fabricated limits; JSON metadata labels them `authored_seed_note` and preserves topic/material/process/equipment/supplier context. Repeatable ingestion produces a persistent normalized TF-IDF vector plus BM25 hybrid index. Retrieval exposes chunk provenance. The advisor distinguishes simple edits from engineering decisions, builds a grounded prompt from the current brief/history/passages, limits questions, validates citations, records proposals/sources/questions into the same versioned brief, accepts choices, and prevents stale overwrites through existing storage concurrency.
- Multimodal implementation: advisor uploads persist bytes/metadata immediately. The `google-genai` 1.75.0 Vertex adapter creates actual `Part.from_bytes` image parts with MIME type and explicit desired-reference/generated-screenshot role labels. It uses an explicit Vertex client and API `v1`; model/project/location remain configurable. The Streamlit advisor sends relevant stored bytes when Vertex is configured and otherwise displays a clearly labeled local retrieval-only response.
- What was tested: **116 tests passed** in 22.29 s. M5 tests ingest actual files, create/reload 13 chunks from 4 sources, retrieve the relevant manufacturing passage, preserve provenance/context, cite real chunk IDs, reject invented citations, skip retrieval for a dimension edit, update/accept a brief choice, handle insufficient evidence, persist advisor chat/images, and inspect actual SDK inline image bytes. Streamlit AppTest exercised a blocked-Vertex advisor turn and displayed cited local evidence.
- Repeatable evidence: `python -m cli knowledge-update` built source hash `1b9621cb4dd438cb2fdf8b8491e17d8b629964291dd87889c34e88ec69b9d290`; `knowledge-query 'waterjet versus CNC bracket manufacturing'` ranked the authored subtractive/sheet-process passage first with its equipment and supplier qualifiers.
- Blocked/unverified: no ADC-authenticated Vertex request ran. Project, location, model and ADC are absent, so live Gemini model availability, image interpretation, response quality and cost are unverified. Local retrieval-only text is explicitly labeled and is not represented as Gemini. The TF-IDF vector is local and persistent but lexical rather than a neural semantic embedding; BM25 provides the second hybrid signal.
- Manual check: run `python -m cli knowledge-update`, query the index, and use the advisor route in Streamlit. To verify Gemini later, set the documented Vertex variables and establish ADC, then send a message with a real image and inspect the cited response/brief update.
- Next milestone: M6 deterministic JSON-to-Markdown specification rendering, role-specific Vertex spec/CAD functions, restricted generated code, and bounded technical repair. Generated-code execution remains blocked until an actual container runtime is available.

## Current dependency and blocker state

- Verified: Python 3.12.12, CadQuery 2.6.1, FreeCADCmd/API 1.1.4 and local SQLite/artifact storage.
- Blocked: no generated-code container runtime; no Mechanical executable/version/license or compatible PyMechanical; no Vertex project/location/model/ADC.
- Verified: Streamlit 1.66.1, google-genai 1.75.0 SDK construction, local TF-IDF/BM25 index, trimesh 4.12.2 and Plotly 6.9.0 packages. Actual STL preview remains pending.
- Never treat a mock or fixture as actual CAD/solver evidence; never fabricate results.

## Exact next step / resume instructions

1. Reread §§8–12 and 23–24 of [PROJECT_SPEC.md](./PROJECT_SPEC.md).
2. Implement deterministic `design_spec.json` and Markdown from one validated object plus role-specific Vertex spec/CAD adapters.
3. Implement restricted `build(params)` validation and bounded repair bookkeeping. Do not execute generated code without the required container boundary; continue to use the verified trusted deterministic CAD path only for integration evidence.

If resuming after compaction, read this file, [PLAN.md](./PLAN.md), [REQUIREMENTS_CHECKLIST.md](./REQUIREMENTS_CHECKLIST.md), then relevant specification sections. A persisted interrupted job requires artifact inspection and an explicit new retry key; it is never silently rerun.

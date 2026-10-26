# Project status

Updated: 2026-10-26. Current boundary: **M7 implemented and locally tested; real reference CAD ? app review/acceptance ? FEM solve ? displayed results/report verified. Live Vertex and generated-code container execution remain blocked. Next: finish M8 analysis advising/coverage.**

## Authority and continuity

- The existing implementation was preserved. The user authorized four advisor/dependency fixes and replacement of the solver backend with **FreeCAD FEM + Gmsh + CalculiX**. All current/future solver requirements in [PROJECT_SPEC.md](./PROJECT_SPEC.md), [PLAN.md](./PLAN.md), [REQUIREMENTS_CHECKLIST.md](./REQUIREMENTS_CHECKLIST.md), [BACKLOG.md](./BACKLOG.md) and [AGENTS.md](./AGENTS.md) use this backend. No commercial solver license/client is required.
- The published M6 migration is `f8bb50b`; current M7 work continues from it; no database reset or history rewrite was performed. Existing contracts and schema-version-1 SQLite records remain readable; new contract fields have defaults. Database schema v1 upgrades additively to v2 for active-attempt and accepted-revision/hash fields. Historical intake, brief versions, attempts and artifacts remain immutable.
- The requested AGENTS.md was absent on arrival. It now records continuity, the solver decision, execution boundaries and the native Windows path constraint.

## Current PC and setup

- Restored all five locked extras (`test,cad,ui,llm,fem`) with `uv sync --python 3.12 --frozen --extra test --extra cad --extra ui --extra llm --extra fem`.
- Actual runtime: Python 3.12.13; Pydantic 2.14.1; pytest 9.1.1; CadQuery 2.6.1; Streamlit 1.66.1; google-genai 1.75.0; trimesh 4.12.2; Plotly 6.9.0. `.python-version` selects the tested 3.12 series. Portable tools and environments are ignored by Git.
- Downloaded official FreeCAD 1.1.4 portable Windows archive, verified release SHA-256 `4828741fc91ee37fafcdb97a1abacb18b04ba451ac4372d9ff7a7349b36f4d6d`, and extracted under `.tools/freecad/`. Its supplied Python API, Gmsh 4.15.0 and CalculiX 2.22 ran successfully. Discovery prefers `bin/freecadcmd.exe` and finds adjacent mesher/solver binaries; explicit `FREECAD_CMD`, `GMSH_EXE`, `CALCULIX_CCX` overrides remain available.
- Missing: Docker/Podman engine and built CAD container image; Vertex project/location/model process configuration and ADC. No live Gemini request, vision interpretation or generated-code container execution is claimed. Google Cloud CLI was not found; authenticate locally before live verification.
- The configurable model example is now `gemini-3.8-flash`. Official Google lifecycle/model and SDK documentation was checked on 2026-10-26; the former `gemini-2.5-flash` example retired on 2026-10-20. Project-specific model access/quality/cost remain unverified. References are linked in [README.md](./README.md).

## Four review fixes: implemented and regression-tested

1. Advisor requests load persisted intake/prior-chat image bytes referenced by the current brief, including after reopening a session; role labels are preserved.
2. Explicit dimension edits update the versioned structured dimensions without a model call. Typed advisor patches update supported engineering fields and resolved questions while preserving identity/requirements and unaffected dimensions. Stale edits still use optimistic concurrency.
3. Vertex client construction/authentication and request failures share the ProviderUnavailable boundary. SDK calls have bounded timeouts; owned clients are closed.
4. The previous nested-package probe failure was removed with the old solver adapter. The FEM boundary checks executable presence without importing a nonexistent solver-client package and returns BLOCKED without numerical results when dependencies are missing.

## Solver changeover: real deterministic path verified

- Fixed trusted FreeCAD FEM template imports the exact STEP, checks validity/single solid and accepted mm bounds, resolves planar min/max-X faces by position/normal tolerances, rejects zero/ambiguous/overlapping regions, and creates labeled supports/loads with verified force directions.
- `demo-fem` prepares actual tessellated region geometry in `regions.html`, saved `setup.FCStd`, structured analysis JSON/Markdown and a preparation record. It does not solve. `fem-solve` requires explicit confirmation binding spec, geometry, actual region data and the setup FCStd; modified inputs invalidate confirmation and repeated runs cannot overwrite outputs.
- The solve meshes through Gmsh, writes/runs CalculiX, checks completion/FRD/DAT evidence, imports real displacement/stress fields and reads support reaction totals from DAT. It saves `analysis.FCStd`, results/report, preliminary nodal result images, logs, solver input/output and a hash/size completion manifest. Owned process trees are terminated on timeout.
- Material allowlist currently contains only FreeCAD's sourced Steel-Generic reference: E 200000 MPa, Poisson ratio 0.3, density 7900 kg/m^3. This is a demonstration material, not certification of user stock; other materials require a reviewed/source-backed addition.
- Real test and documented CLI demo: 100 x 20 x 10 mm cantilever, 100 N negative-Z tip force, 3 mm quadratic tetrahedral mesh. **Maximum displacement 0.0996479292 mm**, versus Euler-Bernoulli **0.1000000000 mm** (about 0.352% difference); max von Mises **29.8857787 MPa**. Extracted reaction `(2.345342e-10, 3.10296e-10, 100.0) N`; **7,761 nodes / 4,346 elements**. No acceptance criterion, convergence, fatigue or durability claim.
- Persistent demonstration project: `25f06e9e33784d6187ea1b2fb8957db5`; analysis `5d993167c2da4b199162fb62c44a0f0b`; geometry SHA-256 `f3be430528516bddbe3e9fd115b6b387057be6b4560f06a2152d5f559b549cf8`. Artifacts are under ignored `data/projects/<project>/analyses/<analysis>/`. These are explicit integration-example inputs, not inferred conditions for a user design.
- Current result images show actual nodal displacement/stress fields. App and CLI actual-face review/confirmation, explicit reference-steel static input, real solving and report display work. Smooth contour controls, broader materials/selectors and advisor-led analysis planning remain M8/M9 work.

## M6: specification and generated CAD

- `agents/spec_writer.py` consumes a frozen brief and real image payloads, creates DesignSpec, preserves known dimensions/provenance, requirements, decisions, material intent and image IDs, and identifies unsupported designs. JSON and Markdown share one validated contract.
- `agents/cad_creator.py` produces only a restricted `build(params)` function and explanation, converts parameters explicitly to mm/degrees, and receives previous code plus actual technical errors for one bounded repair.
- `workers/code_validation.py` rejects imports, infrastructure/file/network/shell access, dunder/unknown attributes, decorators, rebinding trusted names and unsupported syntax. This is defense in depth, never a sandbox claim.
- `workers/runtime.py`, `workers/Dockerfile`, `workers/container_entry.py` and `.dockerignore` implement the container boundary: no network/secrets, minimal job mount, non-root user, read-only root, dropped capabilities and CPU/memory/process/time limits; required outputs, hashes, sizes and completion evidence are checked. **Actual image build and isolated generated-code execution remain unverified because the runtime is absent.**
- `generation.py` connects frozen brief -> persisted spec -> generated source -> container -> real FreeCAD -> geometry/bounding rules -> DESIGN_REVIEW. Durable single-claim jobs run in background; reruns/restarts do not silently replay existing work. A technical failure can consume one repair; blocked dependencies consume no repair or user rejection. Explicit retry creates a new attempt while preserving earlier artifacts.
- Streamlit automatic mode starts generation once when configured, displays progress/errors and specification downloads, and exposes explicit blocked/failed retry. M7 now supplies artifact-bound acceptance, feedback and restart gates. Tests use labeled provider/container doubles for these transitions; they do not count as a live model or container integration.
- Long-path regression exposed native STL/STEP/FCStd limitations beyond Python's extended-path support. Trusted CAD/FreeCAD/FEM native IO now uses short private staging paths and publishes verified outputs back to immutable revision directories; hashes and original artifact locations remain intact. This is captured in AGENTS.md.
- Packaging includes previously omitted application/reporting/analysis modules; wheel build succeeded. The local knowledge index rebuilt with the unchanged source hash `1b9621cb4dd438cb2fdf8b8491e17d8b629964291dd87889c34e88ec69b9d290` (4 sources / 13 chunks). Timestamp-only index churn was not retained.

## M7 and the real app integration

- `review.py` binds acceptance to the current checked revision, STEP hash and verified manifests; altered artifacts or failed mandatory geometry checks cannot pass. The app displays the actual STL, parameters, assumptions, rule coverage and CAD downloads.
- All feedback modes persist text/images/action. First rejection queues a new candidate in the same attempt and preserves unrelated requirements; the second closes the failed attempt with both candidates/artifacts retained. Technical repair and user rejection counts are separate. Explicit hard/soft requirement changes need an existing stable ID and exact evidence from the user's feedback.
- Retry approved brief / brainstorm with saved failure feedback / original-idea restart each creates a fresh attempt with reset counters. Original intake/images and previous brief/revision records are preserved. Original-idea fields/images are prepopulated in an editable working copy.
- `fem_workflow.py` connects exact accepted geometry to durable prepare/solve jobs. The operator explicitly selects material, force and mesh, views actual imported support/load faces, then confirms the setup hash before a solve. Changed/failed analysis inputs can be edited as a new setup without replaying or overwriting a previous run.
- The app displays actual nodal displacement/stress fields, mesh counts, beam comparison, reaction balance, deterministic report, logs and downloadable files. The integration report includes executed executable paths/versions/arguments. The explicit `fem` deployment extra declares Matplotlib; restore all five extras.
- `python -m cli --data-dir data verify-fem-e2e` generated fresh repository-authored reference geometry and drove the real app through review, exact-artifact acceptance, actual face confirmation, meshing/solving and result/report display, then reopened the saved session without another solve. No CAD/FEM/provider component was replaced by a double; only the data-directory environment is scoped by the test driver. The browser view was also checked at localhost:8501.
- The run matched the reference displacement/stress/mesh values above: 0.09964792921575177 mm displacement versus 0.1 mm beam theory (0.352070784% difference), 29.885778687934497 MPa extracted von Mises stress, and a 3.8896002183468676e-10 N reaction residual (relative 3.889600218346868e-12).
- [FEM_INTEGRATION_REPORT.md](./FEM_INTEGRATION_REPORT.md) records reproducible commands, names/versions, numerical comparisons and the persistent local evidence bundle. `app_evidence.json` records actual UI actions/metrics/plot count and no-mock boundaries. Native result bundles and databases remain ignored by Git.
- M7's counter/transaction/restart tests use explicitly synthetic artifact fixtures; provider/container doubles remain labeled. Live feedback-based Gemini/container regeneration has not been executed. The real app FEM test and core real FEM test are marked `real_integration` and never substitute a mock solver.
- Windows SQLite occasionally returned SQLITE_PROTOCOL during competing connection initialization. A bounded retry now applies only before yielding the transaction; transaction bodies/commits are never replayed. Existing single-claim and concurrent-edit tests pass.

## Verification

- Current full rerun: **163 tests passed, no skips, in 122.12 seconds** on Python 3.12.13. This includes both marked real FEM integrations and M7 transaction/restart/UI tests; the 15 warnings are third-party CadQuery/pyparsing deprecations. The final CLI app verification also exited 0.
- Latest persistent app run: project `86d4169f8c74414cbbe680239001c105`, analysis `70889c1e4617419cb5eac55600868b3f`, accepted revision `0d6991021fa141f1803fd50ff90b6427`, STEP SHA-256 `8405e5d7f7ac5b4e064cdc70a5fde8c88989d2dbeebba415665fad437e86adde`. All 32 published FEM artifacts passed hash/size verification, and the manifest points to the actual durable solve job. The result/report bundle remains local and ignored; see FEM_INTEGRATION_REPORT.md for its filenames and numerical comparisons.
- Current wheel build, five-extra frozen restore, lockfile validation and whitespace checks passed. Prior M6 publication evidence below is retained as history.

- Prior M6 publication checkpoint: **143 tests passed**, no skips, in **61.41 seconds** on Python 3.12.13, including real CAD, FreeCAD import/save, FreeCAD FEM/CalculiX and Streamlit tests. Fifteen third-party CadQuery/pyparsing deprecation warnings remain; no test failed.
- Real FEM integration tests also verify explicit confirmation, stale setup rejection, no-overwrite runs, source-backed material gates and DAT reaction extraction. M6 tests cover requirement preservation, unit conversion, unsafe-source rejection, bounded repair, duplicate claims, blocked dependencies, explicit new attempts and recovery behavior.
- A complete M6 state-machine test uses a clearly labeled container double with real repository-authored CAD/FreeCAD. It proves orchestration and native IO, **not sandbox execution**. No mock numeric solver values are used as integration evidence.
- `uv lock --check`, wheel build and `git diff --check` passed. The repository reference scan found no remaining obsolete solver imports, executable variables, adapter references or names. The knowledge update/query and documented prepare/confirm/solve CLI commands ran successfully.
- Final saved-demo audit verified all 27 artifact hashes/sizes, the FCStd ZIP integrity and embedded FEM mesh/results, exact raw-to-report result values, and both generated PNG files.

## Earlier handoff evidence retained

The previous machine recorded M1 77 tests; M2 91 tests including real CadQuery 2.6.1 / FreeCAD 1.1.4; M4 105 tests; and local M5 116 tests on Python 3.12.12. These historical counts are not current-PC verification. The old deterministic example was one valid 100 x 20 x 10 mm solid (volume approximately 20000 mm^3, area 6400 mm^2). Existing local databases, uploads and artifacts were ignored by Git and were not part of the checkout; newly generated demonstration state is also ignored. No credential file was transferred or created.

## Commit and handoff contents

The publication includes intended source/tests, project records, secret-free configuration examples, Python/dependency manifests and the existing curated knowledge sources/index. Local credentials, `.env`, ADC/secrets files, SQLite databases, `.venv/`, `.tools/`, caches, package/build outputs, uploads and generated CAD/FEM artifacts are excluded. The persistent demo paths above describe local verification evidence; those result bundles are not included in the repository. Another PC must restore the environment and FreeCAD/FEM tools, configure Vertex/container access if needed, and rerun the documented demos.

The prior M6 publication review scanned 75 intended files and found no recognized credential patterns, unexpected binaries or forbidden local/generated paths. Ignore checks confirmed exclusion of environments, portable software, local SQLite/demo data and secret-file locations; `uv lock --check` and `git diff --check` also passed. Only the example configuration is included, with no credentials.

Current M7 review scanned 83 intended source/documentation/test files with no recognized credential patterns, unexpected binaries or forbidden local/generated paths. Environments, portable binaries, databases and native result bundles remain ignored. A final retry-key regression also verifies that allocating a revision cannot change the identity of an existing queued generation job.

## Exact next action

1. Finish M8's advisor-led analysis recommendations and missing-input conversation, maintaining clear unsupported-analysis labels and the existing real static setup/confirmation/report path. Add only explicitly sourced materials/selectors with actual verification.
2. Verify live-assisted CAD and feedback regeneration when Vertex project/location/current model/ADC and a running Linux Docker/Podman engine plus CAD image are available. Do not run generated source in a host process to bypass these blockers.
3. Complete M9 assisted end-to-end verification, negative input/selector cases, failure reporting and portable handoff. The trusted reference app/FEM journey is verified; it is not a complete live-assisted-product claim.
4. Inspect interrupted job logs/artifacts and confirm the old owner stopped before explicit recovery/retry. No silent requeue, transaction replay or overwrite.

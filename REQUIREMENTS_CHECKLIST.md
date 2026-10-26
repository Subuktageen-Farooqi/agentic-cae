# Requirements traceability

Authority: [PROJECT_SPEC.md](./PROJECT_SPEC.md), updated for the user-approved FreeCAD FEM changeover on 2026-10-26. IDs below reference its numbered sections. A location listed for pending work is a **planned implementation location**, not an existing or working integration. Verification describes the required method; actual evidence belongs in [STATUS.md](./STATUS.md). Status vocabulary: **pending**, **implemented**, **verified**, **blocked**. Implemented means code exists without sufficient execution evidence; blocked means an identified external dependency prevents verification/execution. No mocked boundary is evidence of a live integration.

## Local software, credentials and licenses

| ID | Required dependency / context | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| DEP-01 | Supported Python and Pydantic, SQLite, pytest | `pyproject.toml`, `.venv/`, `config.py` | Project-local interpreter, installed versions, complete M1 tests | verified |
| DEP-02 | Streamlit, trimesh and Plotly | `pyproject.toml`, `app.py` | Start app and interact with actual STL | implemented |
| DEP-03 | CadQuery in isolated execution environment | `workers/cad_worker.py`, `workers/Dockerfile` | Real STEP/STL with valid manifest and measured solid | blocked |
| DEP-04 | Docker or equivalent no-network/resource-limited runtime | `config.py`, `workers/runtime.py` | Probe daemon; enforce mounts, limits, user and no-network | blocked |
| DEP-05 | Installed FreeCADCmd supplied Python/API, explicit executable path | `config.py`, `workers/freecad_worker.py` | Actual STEP import, metrics, FCStd and completion manifest | verified |
| DEP-06 | Installed/version-compatible FreeCAD FEM FreeCAD FEM | `config.py`, `workers/fem_worker.py` | Version probe, launch/connect, actual import and solve | verified |
| DEP-07 | Installed CalculiX ccx; no commercial license | `config.py`, `workers/fem_worker.py` | Actual ccx version and completed static solve | verified |
| DEP-08 | Installed Gmsh and compatible FreeCAD FEM API | `config.py`, `workers/fem_worker.py` | Actual tetrahedral mesh and fixed API template | verified |
| DEP-09 | Vertex project, location, vision Gemini model ID and ADC permissions | `.env.example`, `config.py`, `providers/vertex.py` | Current official SDK/model docs; ADC live vision/text request; never print secrets | blocked |
| DEP-10 | Local embedding package/model cache | `rag/ingest.py`, `rag/retriever.py` | Local index build and semantic query; honest lexical fallback | implemented |
| DEP-11 | Writable local SQLite/artifact storage | `storage.py`, `config.py` | Atomic/recovery/concurrent persistence tests | verified |

Current PC: Python 3.12.13 and all four locked extras are installed; portable FreeCAD 1.1.4, Gmsh 4.15.0 and CalculiX 2.22 have completed a real deterministic solve. Docker/Podman and Vertex project/location/model/ADC remain unavailable. Historical evidence and remaining limitations are in STATUS.md. Never request credentials in chat or log their values.

## Product, scope and architecture (§§1–3)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 01-01 | Full idea → informed brief → spec → CadQuery → FreeCAD → checks → review → analysis/spec → actual FreeCAD FEM → grounded report journey | `workflow.py`, `app.py`, `examples/` | Complete assisted and deterministic demos using real boundaries | pending |
| 01-02 | RAG engineering conversation before generation present from first version | `agents/advisor.py`, `rag/`, `app.py` | Cited recommendation and brief update before CAD | pending |
| 02-01 | One connected solid; prismatic extrusions, holes, cuts, unions, basic fillets | `schemas.py`, `agents/cad_creator.py`, `rules/geometry.py` | Real geometry examples; multiple-solid rejection | pending |
| 02-02 | One real linear static analysis; deterministic cantilever and assisted bracket/support demo | `analysis/static_structural_template.py`, `examples/` | Run both demos; real solve where installed | pending |
| 02-03 | Unsupported geometry/analysis identified with supported simplification; extensible assemblies/selectors/rules/analyses | `agents/`, `schemas.py`, `rules/registry.py` | Unsupported request tests and explicit UI labels | pending |
| 02-04 | CAD acceptance separate from engineering adequacy; successful solve separate from acceptance criteria | `workflow.py`, `reporting.py`, `app.py` | Acceptance/solve result tests and UI inspection | pending |
| 03-01 | Python, Streamlit, Pydantic, SQLite, local artifacts, Markdown, lightweight actual STL viewer | `pyproject.toml`, `schemas.py`, `storage.py`, `app.py` | Run application, contract tests, inspect real preview | pending |
| 03-02 | Configurable replaceable vision provider/retriever; role functions; no distributed/multi-agent infrastructure | `providers/`, `agents/`, `rag/retriever.py` | Adapter contract tests and source inspection | pending |
| 03-03 | Deterministic state machine; UI/orchestration/model/worker separation | `workflow.py`, `app.py`, `workers/` | Transition tests and isolated stage execution | implemented |
| 03-04 | Separate CAD/solver environments; FreeCAD supplied interpreter; responsive progress/error display | `workers/`, `app.py`, `storage.py` | Worker launch failure/progress and frontend rerun tests | pending |

## Intake and route selection (§4)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 04-01 | Collect idea, purpose, hard/soft requirements, dimensions/units, optional material/manufacturing, multiple images; incomplete ideas allowed | `schemas.py:Intake`, `app.py` | Incomplete/full intake validation and UI tests | verified |
| 04-02 | Immediately persist original intake immutably and image bytes | `storage.py:create_project`, `app.py` | Reload bytes and immutable original after editing/restart | verified |
| 04-03 | Exact Maestro title/description opens multimodal advisor beside editable brief | `app.py`, `agents/advisor.py` | Route UI and conversation integration tests | implemented |
| 04-04 | Exact automatic-route title/description; immediately draft shared brief/spec with visible assumptions, no mandatory second confirmation | `app.py`, `workflow.py`, `agents/spec_writer.py` | Automatic route proceeds from incomplete intake | implemented |
| 04-05 | Focused clarification only when genuinely blocking; both routes same DesignBrief | `schemas.py:DesignBrief`, `agents/` | Both routes validate same contract; missing-input scenarios | verified |

## RAG advisor (§5)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 05-01 | Small real curated collection covers demo decisions; supports mechanisms/motion, DOF/constraints, joints/fasteners, bearings/guides | `data/knowledge/`, `rag/sources.py` | Inspect actual source documents and retrieve relevant chunks | verified |
| 05-02 | Knowledge topics include structures/load paths, materials, CNC, laser/waterjet, additive, weldments/joining, assembly/disassembly, DFM, examples | `data/knowledge/`, `rag/sources.py` | Corpus/topic coverage checks; no invented engineering limits | verified |
| 05-03 | Ingest, chunk, embed/index, persist and retrieve; repeatable update command | `rag/ingest.py`, `rag/retriever.py` | Actual ingestion/index reload/query command | verified |
| 05-04 | Prefer local semantic retrieval with lexical/hybrid fallback; replaceable lightweight retriever | `rag/retriever.py`, `pyproject.toml` | Semantic relevance and explicit fallback tests | implemented |
| 05-05 | Retain source ID/title/URL or local ref/section or page/version-date/topic/material-process/chunk ID when available | `schemas.py:SourceReference`, `rag/sources.py` | Provenance roundtrip from actual source to cited answer | verified |
| 05-06 | Label authored seed notes; distinguish manufacturer/authority; no fabricated sources, attribution or limits | `data/knowledge/`, `agents/advisor.py` | Inspect corpus and citations against actual text | verified |
| 05-07 | Advisor reads current brief/history/images, identifies decision, retrieves engineering context, offers alternatives/tradeoffs/plain explanations | `agents/advisor.py`, `providers/vertex.py` | Grounded conversation and captured live payload when possible | implemented |
| 05-08 | One/two useful questions, avoid answered questions, skip retrieval for simple edits | `agents/advisor.py` | Multi-turn and dimension-edit tests | verified |
| 05-09 | Cite supporting passages, acknowledge insufficient evidence; retrieved data cannot override app instructions | `agents/advisor.py` | Citation validation, empty retrieval, adversarial source tests | verified |
| 05-10 | Distinguish confirmed requirements/preferences/proposed/accepted/assumptions/unresolved; guidelines never silently become hard requirements | `schemas.py:DesignBrief`, `agents/advisor.py` | Structured choice acceptance and requirement preservation tests | verified |
| 05-11 | Keep material/equipment/supplier context with process constraints | `schemas.py:SourceReference`, `agents/advisor.py` | Context preserved through retrieval and brief update | verified |

## Images and living brief (§§6–7)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 06-01 | Multiple image uploads in intake, advisor messages and CAD feedback | `app.py`, `schemas.py`, `storage.py` | All three upload flows retain bytes and references | implemented |
| 06-02 | Actually send relevant image content to vision model; filenames insufficient | `providers/vertex.py`, `agents/` | Live actual-image call; inspect byte-bearing provider payload tests | blocked |
| 06-03 | Persist bytes/metadata through reruns/restarts; default images mean desired/reference object | `schemas.py:ImageReference`, `storage.py` | Restart integrity/hash tests and semantic defaults | verified |
| 06-04 | No precise dimensions/properties/capacity from unscaled photos; separate observations/inferences/confirmed facts | `schemas.py`, `agents/` | Image interpretation contract and prompt/output tests | implemented |
| 06-05 | Label generated-model screenshots separately | `schemas.py:ImageReference`, `providers/vertex.py` | Role-specific image labels tested | verified |
| 07-01 | Editable brief with name/description/purpose, hard/soft requirements, dimensions/interfaces, mechanisms/joints, materials | `schemas.py:DesignBrief`, `app.py` | Contract roundtrip and direct UI editing | implemented |
| 07-02 | Brief includes manufacturing/assembly, loads/environment, accepted/proposed choices, assumptions/questions, image IDs and sources | `schemas.py:DesignBrief`, `app.py` | Complete contract validation and UI rendering | implemented |
| 07-03 | Chat/direct edits update same versioned object; reject stale LLM overwrite; meaningful audit trail | `storage.py:save_brief`, `agents/advisor.py` | Optimistic-concurrency, version-history/audit tests | implemented |
| 07-04 | Continue brainstorming / Generate this design / Switch to automatic design controls | `app.py`, `workflow.py` | Three control paths and state tests | implemented |
| 07-05 | Generate freezes brief version; automatic creates version with inferred assumptions | `storage.py`, `workflow.py`, `agents/spec_writer.py` | Frozen snapshot stays unchanged after later edits | implemented |

## Data contracts (§8)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 08-01 | Validated Intake, DesignBrief, DesignSpec, CADGeneration contracts | `schemas.py` | Valid/invalid fixtures and strict extra-field rejection | verified |
| 08-02 | GeometryMetrics, RuleResult, DesignFeedback contracts | `schemas.py` | Units, statuses, evidence and feedback mode validation | verified |
| 08-03 | AnalysisRecommendation, AnalysisSpec, AnalysisResults, ArtifactManifest, WorkflowState contracts | `schemas.py` | Complete serialized roundtrips, invalid-boundary rejection | verified |
| 08-04 | DesignSpec schema/brief versions, name/purpose, units/coordinates, dimensions/features | `schemas.py:DesignSpec` | Required fields and positive parameter validation | verified |
| 08-05 | Stable hard/soft IDs, verification methods, material/manufacturing intent, images, assumptions/questions | `schemas.py:DesignSpec` | ID uniqueness and preservation on revision | implemented |
| 08-06 | Every dimension records user-provided/inferred/accepted values | `schemas.py:Dimension` | Reject missing provenance and inconsistent accepted values | verified |
| 08-07 | design_spec.json and deterministic Markdown from validated JSON | `agents/spec_writer.py`, `reporting.py` | Render same validated fixture and compare outputs | verified |
| 08-08 | Immutable original intake separate from approved brief versions | `storage.py` | Mutation attempts fail; approved snapshot reloads separately | verified |

## CAD execution and FreeCAD (§§9–10)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 09-01 | CAD role receives spec, reference image content, accepted decisions, prior code/feedback or technical errors | `agents/cad_creator.py`, `agents/revision_writer.py` | Captured input tests and live generation when available | implemented |
| 09-02 | Restricted build(params) function; trusted worker owns imports/params/invocation/export/error/log/manifest | `workers/cad_worker.py`, `workers/runtime.py` | Allowed/disallowed source tests and actual worker execution | implemented |
| 09-03 | Generated code cannot control infrastructure, secrets, files, shell or network; real isolation with no-network/no-secrets/non-root/minimal mounts/CPU-memory-time limits | `workers/Dockerfile`, `workers/runtime.py` | Container configuration inspection and adversarial execution tests | blocked |
| 09-04 | Never call subprocess or blacklist a security sandbox | `workers/runtime.py`, `README.md` | Documentation and execution-path review | verified |
| 09-05 | CadQuery produces model.step, preview.stl, model.py, parameters.json, metadata and logs | `workers/cad_worker.py`, `schemas.py:ArtifactManifest` | Real exports and content/hash/completion checks | verified |
| 10-01 | FreeCADCmd API imports STEP, creates document, validates shape, saves actual model.FCStd | `workers/freecad_worker.py` | Real import/save/reopen with installed FreeCAD | verified |
| 10-02 | FCStd is imported geometry; CadQuery remains parametric source; no native feature-tree claim | `app.py`, `README.md` | User labels and actual document inspection | implemented |
| 10-03 | Collect validity, solid count, volume, bbox and useful metrics | `schemas.py:GeometryMetrics`, `workers/freecad_worker.py` | Actual metrics match deterministic cantilever | verified |
| 10-04 | Require expected outputs and completion manifest; exit code alone insufficient; FreeCAD failure blocks CAD success | `workflow.py`, `workers/freecad_worker.py` | Missing executable/output/manifest and real success tests | verified |

## Rule registry (§11)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 11-01 | Extensible rule registry; actual STEP import, nonempty, validity, exactly-one-solid, positive-volume checks | `rules/registry.py`, `rules/geometry.py` | Real metrics plus focused pass/fail fixtures | verified |
| 11-02 | Applicable bbox dimension checks with explicit tolerances | `rules/geometry.py`, `schemas.py:Dimension` | Matched/out-of-tolerance unit-aware tests | verified |
| 11-03 | Wall thickness, manufacturing, application rules and additional requirement checks scaffold explicitly | `rules/manufacturing.py` | Every scaffold returns NOT_IMPLEMENTED, never PASS | verified |
| 11-04 | Rule ID, requirement ID, status, measured/expected/tolerance/message/evidence | `schemas.py:RuleResult` | Contract serialization of all statuses | verified |
| 11-05 | PASS/FAIL/NOT_IMPLEMENTED/NOT_APPLICABLE; separate geometry, coverage, analysis; mandatory failures prevent acceptance; missing checks visible | `workflow.py`, `app.py`, `rules/registry.py` | Acceptance gates and coverage/UI tests | implemented |

## Repairs, feedback and restarts (§§12–14)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 12-01 | Technical repair triggered by execution/mandatory failure, receives real traceback/checks, max one per generated revision; exhausted stage exposes real error | `workflow.py`, `agents/cad_creator.py` | Failure capture and bounded-repair tests | verified |
| 12-02 | Separate repair/rejection counters; max two user rejections; initial plus one feedback regeneration; no unbounded loop | `workflow.py`, `storage.py` | Counter and per-attempt/revision tests | verified |
| 13-01 | Interactive actual preview; params/spec/assumptions/rules/coverage/CAD downloads | `app.py` | Real STL display and download hashes | verified |
| 13-02 | Accept/revise/thumb controls, feedback text/images, explicit submit | `app.py`, `schemas.py:DesignFeedback` | UI paths and feedback contract tests | implemented |
| 13-03 | Thumbs-only, text-only, text+image, image+explicit-revision feedback all valid | `schemas.py:DesignFeedback`, `app.py` | Four input-mode tests; explicit revise action, including no-detail feedback | verified |
| 13-04 | Thumbs down without detail uses reasoned revision from known requirements and explains change without inventing reason | `agents/revision_writer.py` | No-detail feedback prompt/output test | implemented |
| 13-05 | First rejection persists feedback, updates brief/spec intent, preserves unaffected requirements, regenerates and reruns checks | `workflow.py`, `agents/revision_writer.py` | Complete first-rejection integration with preserved IDs | implemented |
| 13-06 | Second rejection records failed attempt preserving both revisions/artifacts/feedback; offers restarts | `workflow.py`, `storage.py`, `app.py` | Failed-attempt persistence and no third candidate | verified |
| 13-07 | Acceptance binds exact revision/geometry artifact then analysis intake | `workflow.py`, `storage.py` | Accepted hash stays tied to reviewed revision | verified |
| 14-01 | Preserve original intake/images and approved/refined brief as distinct snapshots | `storage.py` | Independent snapshot reload and immutable image hashes | verified |
| 14-02 | Retry approved brief / brainstorm with failed feedback / original idea, preserving correct context | `workflow.py`, `app.py` | All three restart scenarios and original prepopulation | verified |
| 14-03 | Restart new attempt ID/reset counters; never overwrite failed attempts; brainstorming retains decisions/failure context | `storage.py`, `workflow.py` | Attempt history/reset/context tests | verified |

## Analysis intake/spec (§§15–16)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 15-01 | Ask exact learning-goal question after acceptance; use purpose/requirements/material/geometry/conditions | `app.py`, `agents/analysis_planner.py` | Accepted-design analysis intake test | implemented |
| 15-02 | Recommendations name/question/relevance/inputs/supported flag | `schemas.py:AnalysisRecommendation`, `agents/analysis_planner.py` | Complete validated recommendations | pending |
| 15-03 | Execute linear static only; identify modal/random vibration/fatigue/transient/other as unsupported | `schemas.py`, `agents/analysis_planner.py` | Unsupported analysis requests never reach solver | implemented |
| 15-04 | No invented spectra/S-N curves/damping/histories/mounts; static does not prove fatigue/vibration life | `agents/analysis_planner.py`, `reporting.py` | Missing-input and scope-limitation tests | pending |
| 16-01 | analysis_spec.json and deterministic Markdown | `reporting.py`, `examples/fem_demo.py` | Same validated source produces both | verified |
| 16-02 | Schema/spec version, accepted revision/hash, type/question, material ID/source and explicit units | `schemas.py:AnalysisSpec` | Required-field, unit and binding validation | verified |
| 16-03 | Supports/loads/selectors/mesh/outputs/acceptance/assumptions/missing/supported status | `schemas.py:AnalysisSpec` | Complete/incomplete/unsupported contract cases | verified |
| 16-04 | Sufficient material/load/support before execution; verified small material allowlist; no brief contradiction | `analysis/materials.py`, `workflow.py` | Material-source and missing-input gate tests | implemented |
| 16-05 | Proposed setup and actual selected regions shown; explicit input confirmation; automatic CAD route never authorizes analysis defaults | `app.py`, `workflow.py` | Confirm-before-solve and invalidation tests | verified |

## Selectors and FreeCAD FEM (§§17–18)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 17-01 | No face IDs across revisions; min/max-X planar selectors with position/orientation/tolerances | `schemas.py:RegionSelector`, `analysis/selectors.py` | Contract and deterministic geometric matching tests | verified |
| 17-02 | Resolve in FreeCAD FEM after import; create labeled FEM constraints; reject zero/ambiguous/invalid/overlapping regions | `workers/fem_script.py`, `analysis/static_structural_template.py` | Actual imported-face matching and invalid-region tests | verified |
| 17-03 | Display actual selected regions before solving, not textual selectors | `workers/fem_worker.py`, `app.py` | Real region images/geometry preview before confirmation | verified |
| 17-04 | Check imported dimensions for scaling; explicit units on every API boundary | `analysis/selectors.py`, `analysis/static_structural_template.py` | mm/m geometry scaling and force/stress unit tests | verified |
| 18-01 | FreeCAD FEM Python API controls installed FreeCAD FEM with CalculiX; verify installed-version compatibility | `workers/fem_worker.py`, `config.py` | FreeCAD 1.1.4 / Gmsh 4.15.0 / CalculiX 2.22 real solve | verified |
| 18-02 | Fixed parameterized AnalysisSpec template, never arbitrary LLM solver scripts | `analysis/static_structural_template.py` | Template review and invalid input tests | verified |
| 18-03 | Launch/connect, transfer/import exact accepted STEP, verify geometry/units, assign verified material | `workers/fem_worker.py`, `analysis/static_structural_template.py` | Actual session/import/material evidence | verified |
| 18-04 | Resolve support/load, mesh, BCs/loads, requested results, solve and check actual completion/errors | `analysis/static_structural_template.py` | Actual solver completion and negative solve evidence | verified |
| 18-05 | Extract results, images/logs, save project when supported, clean up owned sessions | `workers/fem_worker.py` | Actual files, data, session cleanup tests | verified |
| 18-06 | Max displacement, max von Mises, reaction forces, mesh data, status, contours/logs | `schemas.py:AnalysisResults`, `workers/fem_worker.py` | Actual numeric extraction and manifest verification | implemented |
| 18-07 | Every run bound to geometry hash/spec version; reject stale results | `schemas.py`, `storage.py`, `workflow.py` | Changed-geometry/spec stale-result tests | verified |
| 18-08 | Absent/incompatible solver shows useful BLOCKED; preserve workflow; no fabricated or silently mocked solver | `workers/fem_worker.py`, `app.py` | Missing-path/solver failure tests and no fake numbers | verified |

## Reporting (§19)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 19-01 | results.json/report.md/images/downloads; deterministic numeric tables; LLM explains supplied facts only | `reporting.py`, `agents/report_writer.py`, `app.py` | Extracted-value equality and downloadable artifact hashes | implemented |
| 19-02 | Revision/hash, question, material/source, loads/supports/units, mesh/counts, status, displacement/stress | `reporting.py` | Complete report fixture and real extracted values | implemented |
| 19-03 | Reaction balance, plots, supplied acceptance comparisons, missing checks, assumptions/limitations | `reporting.py` | Force equilibrium and threshold comparison tests | implemented |
| 19-04 | Exact absent-criterion phrase; failed/incomplete solve yields failure report | `reporting.py` | Success without criteria and failed/incomplete cases | verified |
| 19-05 | Label preliminary single-mesh; no unverified convergence/peak-stress claims; constraint singularity limits | `reporting.py`, `agents/report_writer.py` | Report limitation assertions and manual review | verified |

## Durable state and organization (§§20–21)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 20-01 | All named states INTAKE through REPORT_READY plus BLOCKED/ERROR | `schemas.py:WorkflowState`, `workflow.py` | Complete enum coverage and valid/invalid transition tests | verified |
| 20-02 | Project/session IDs, immutable intake, route, chats/images/sources, brief/spec versions | `storage.py`, `schemas.py` | Reload actual SQLite records with integrity checks | implemented |
| 20-03 | Attempts/revisions, separate counters, state/feedback/accepted revision | `storage.py`, `workflow.py` | Transaction and persisted history tests | pending |
| 20-04 | Analysis configs/runs, manifests/errors/stage logs | `storage.py`, `schemas.py` | Structured record roundtrip and audit events | implemented |
| 20-05 | Atomic writes/transactions; idempotent job IDs/statuses avoid duplicate LLM/CAD/solver on rerun | `storage.py`, `workflow.py` | Concurrent job claim and same-key deduplication tests | verified |
| 20-06 | Recover restart; check interrupted jobs/artifacts; never automatically rerun expensive work | `storage.py`, `workflow.py` | Reopen DB with running jobs, explicit interrupted state | verified |
| 20-07 | Unique project/intake/uploads/briefs/attempt/revision/analysis folders; accepted/failed artifacts never overwritten | `storage.py`, `schemas.py:ArtifactManifest` | Path containment, no-clobber and integrity/tampering tests | verified |
| 21-01 | Clear suggested module structure; UI, orchestration, LLM and execution separate | `app.py`, `agents/`, `workers/`, `analysis/`, `rules/`, `rag/` | Source structure and isolated testability review | pending |

## Process, verification and handoff (§§22–24 and closing provider decision)

| ID | Requirement | Implementation location | Verification method | Status |
| --- | --- | --- | --- | --- |
| 22-01 | Inspect repository/local software/credential presence without exposing secrets | `config.py`, `STATUS.md` | Actual diagnostic execution, redacted output | verified |
| 22-02 | Follow implementation order; deterministic slice before assistance; continue independent work when blocked | `PLAN.md`, `STATUS.md` | Milestone evidence and blocker records | pending |
| 23-01 | Actual source ingestion/relevant retrieval/cited recommendation/accepted choice/insufficient evidence | `tests/test_rag.py`, `examples/` | Execute all five RAG demonstrations | verified |
| 23-02 | Actual image through vision and preserved through restart | `tests/`, `examples/` | Live Gemini image response plus persisted-byte hash | blocked |
| 23-03 | Actual model/export/FreeCAD/preview; failed build; repair budget; scaffold NOT_IMPLEMENTED | `tests/`, `examples/cantilever.py` | Execute deterministic CAD demo and negative cases | blocked |
| 23-04 | First revision, second failure, three restarts, artifact-bound acceptance | `tests/test_review.py`, `tests/test_app_fem_e2e.py` | Complete feedback/restart integration cases | implemented |
| 23-05 | Accepted geometry import/actual face display; missing/ambiguous rejection; real solve/report equality/stale result rejection | `tests/`, `examples/cantilever.py` | Real FreeCAD FEM demo and failure tests | verified |
| 23-06 | Reload session after application restart; no duplicate frontend jobs | `tests/test_storage.py`, `tests/test_app.py` | SQLite restart and Streamlit rerun tests | verified |
| 23-07 | Matching-assumption beam-theory displacement and force equilibrium; no overinterpreted constrained peak stress | `analysis/sanity.py`, `reporting.py`, `tests/` | Real solver versus analytical estimate with explicit tolerance | verified |
| 24-01 | Source/dependency setup/tested versions/config without secrets/exact startup | `README.md`, `pyproject.toml`, `.env.example` | Clean-environment documented commands and version evidence | implemented |
| 24-02 | KB update command, FreeCAD/FreeCAD FEM paths, deterministic and assisted demos | `README.md`, `examples/`, `config.py` | Run each documented command, record actual outcomes | implemented |
| 24-03 | Truthful verified/unverified/blocked/planned distinctions, known limitations and actual evidence; no complete-product claim with blocked solver | `STATUS.md`, `REQUIREMENTS_CHECKLIST.md`, `README.md`, `app.py` | Audit claims against recorded executions | pending |
| 24-04 | Google Vertex vision Gemini for advisor/spec/CAD/revision/analysis/report; ADC/configurable project/location/model; current SDK/model availability verified; replaceable provider | `providers/vertex.py`, `config.py`, `agents/`, `.env.example` | Official docs/SDK check before implementation; live configured-role calls | blocked |
| 24-05 | Local embeddings initially, no OpenAI dependency/key; proceed reasonably and ask only unresolved external/consequential blockers | `rag/`, `pyproject.toml`, `PLAN.md` | Dependency/config review and local index execution | verified |
| PROC-01 | Create these four records before implementation; ordered testable milestones with behavior/verification/manual check | `PLAN.md`, `STATUS.md`, `BACKLOG.md`, `REQUIREMENTS_CHECKLIST.md` | Inspect records created before application source | verified |
| PROC-02 | Update records at each boundary, five-point report, exact resume step; reread relevant spec on new milestone/compaction | `STATUS.md`, `PLAN.md` | Boundary evidence and resumption instructions | implemented |
| PROC-03 | No silent requirement removal/scope changes; unrelated improvements in backlog; no mock/scaffold success claims | All four project records | Traceability/evidence review each milestone | implemented |

## Current verification boundary

The real deterministic FEM path is verified. App and CLI actual-region review/confirmation work for the limited reference-steel linear-static setup. Broader M8 advisor-led intake/recommendations remain pending. Exported images currently show actual nodal displacement/stress fields; smooth contour/postprocessing controls remain unverified. M6 specification/source/repair/job behavior is tested with labeled provider/container doubles; actual Vertex and generated-code container execution remain blocked. M7 feedback/restart transactions and UI are tested with labeled fixtures; live Gemini/container regeneration and the full assisted journey remain pending. Real no-solver-mock app integration is in tests/test_app_fem_e2e.py and FEM_INTEGRATION_REPORT.md.

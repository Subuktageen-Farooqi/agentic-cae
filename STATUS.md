# Project status

Updated: 2026-10-26. Current boundary: **M6 implemented and locally tested; live Vertex and generated-code container execution blocked. Next independent milestone: M7.**

## Authority and continuity

- The existing implementation was preserved. The user authorized four advisor/dependency fixes and replacement of the solver backend with **FreeCAD FEM + Gmsh + CalculiX**. All current/future solver requirements in [PROJECT_SPEC.md](./PROJECT_SPEC.md), [PLAN.md](./PLAN.md), [REQUIREMENTS_CHECKLIST.md](./REQUIREMENTS_CHECKLIST.md), [BACKLOG.md](./BACKLOG.md) and [AGENTS.md](./AGENTS.md) use this backend. No commercial solver license/client is required.
- This change set continues from Git baseline `26d842a`; no database reset or history rewrite was performed. Existing contracts and schema-version-1 SQLite records remain readable; new contract fields have defaults. Historical intake, brief versions, attempts and artifacts remain immutable.
- The requested AGENTS.md was absent on arrival. It now records continuity, the solver decision, execution boundaries and the native Windows path constraint.

## Current PC and setup

- Restored all four locked extras (`test,cad,ui,llm`) with `uv sync --python 3.12 --frozen --extra test --extra cad --extra ui --extra llm`.
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
- Current result images show actual nodal displacement/stress fields. Smooth contour controls and application analysis intake/review are not yet delivered; they remain M8/M9 work. CLI actual-face review and confirmation already work.

## M6: specification and generated CAD

- `agents/spec_writer.py` consumes a frozen brief and real image payloads, creates DesignSpec, preserves known dimensions/provenance, requirements, decisions, material intent and image IDs, and identifies unsupported designs. JSON and Markdown share one validated contract.
- `agents/cad_creator.py` produces only a restricted `build(params)` function and explanation, converts parameters explicitly to mm/degrees, and receives previous code plus actual technical errors for one bounded repair.
- `workers/code_validation.py` rejects imports, infrastructure/file/network/shell access, dunder/unknown attributes, decorators, rebinding trusted names and unsupported syntax. This is defense in depth, never a sandbox claim.
- `workers/runtime.py`, `workers/Dockerfile`, `workers/container_entry.py` and `.dockerignore` implement the container boundary: no network/secrets, minimal job mount, non-root user, read-only root, dropped capabilities and CPU/memory/process/time limits; required outputs, hashes, sizes and completion evidence are checked. **Actual image build and isolated generated-code execution remain unverified because the runtime is absent.**
- `generation.py` connects frozen brief -> persisted spec -> generated source -> container -> real FreeCAD -> geometry/bounding rules -> DESIGN_REVIEW. Durable single-claim jobs run in background; reruns/restarts do not silently replay existing work. A technical failure can consume one repair; blocked dependencies consume no repair or user rejection. Explicit retry creates a new attempt while preserving earlier artifacts.
- Streamlit automatic mode starts generation once when configured, displays progress/errors and specification downloads, and exposes explicit blocked/failed retry. Acceptance remains intentionally gated for M7. Tests use labeled provider/container doubles for these transitions; they do not count as a live model or container integration.
- Long-path regression exposed native STL/STEP/FCStd limitations beyond Python's extended-path support. Trusted CAD/FreeCAD/FEM native IO now uses short private staging paths and publishes verified outputs back to immutable revision directories; hashes and original artifact locations remain intact. This is captured in AGENTS.md.
- Packaging includes previously omitted application/reporting/analysis modules; wheel build succeeded. The local knowledge index rebuilt with the unchanged source hash `1b9621cb4dd438cb2fdf8b8491e17d8b629964291dd87889c34e88ec69b9d290` (4 sources / 13 chunks). Timestamp-only index churn was not retained.

## Verification

- Pre-publication full rerun: **143 tests passed**, no skips, in **61.41 seconds** on Python 3.12.13, including real CAD, FreeCAD import/save, FreeCAD FEM/CalculiX and Streamlit tests. Fifteen third-party CadQuery/pyparsing deprecation warnings remain; no test failed.
- Real FEM integration tests also verify explicit confirmation, stale setup rejection, no-overwrite runs, source-backed material gates and DAT reaction extraction. M6 tests cover requirement preservation, unit conversion, unsafe-source rejection, bounded repair, duplicate claims, blocked dependencies, explicit new attempts and recovery behavior.
- A complete M6 state-machine test uses a clearly labeled container double with real repository-authored CAD/FreeCAD. It proves orchestration and native IO, **not sandbox execution**. No mock numeric solver values are used as integration evidence.
- `uv lock --check`, wheel build and `git diff --check` passed. The repository reference scan found no remaining obsolete solver imports, executable variables, adapter references or names. The knowledge update/query and documented prepare/confirm/solve CLI commands ran successfully.
- Final saved-demo audit verified all 27 artifact hashes/sizes, the FCStd ZIP integrity and embedded FEM mesh/results, exact raw-to-report result values, and both generated PNG files.

## Earlier handoff evidence retained

The previous machine recorded M1 77 tests; M2 91 tests including real CadQuery 2.6.1 / FreeCAD 1.1.4; M4 105 tests; and local M5 116 tests on Python 3.12.12. These historical counts are not current-PC verification. The old deterministic example was one valid 100 x 20 x 10 mm solid (volume approximately 20000 mm^3, area 6400 mm^2). Existing local databases, uploads and artifacts were ignored by Git and were not part of the checkout; newly generated demonstration state is also ignored. No credential file was transferred or created.

## GitHub handoff contents

The publication includes intended source/tests, project records, secret-free configuration examples, Python/dependency manifests and the existing curated knowledge sources/index. Local credentials, `.env`, ADC/secrets files, SQLite databases, `.venv/`, `.tools/`, caches, package/build outputs, uploads and generated CAD/FEM artifacts are excluded. The persistent demo paths above describe local verification evidence; those result bundles are not included in the repository. Another PC must restore the environment and FreeCAD/FEM tools, configure Vertex/container access if needed, and rerun the documented demos.

Pre-publication review scanned 75 intended files and found no recognized credential patterns, unexpected binaries or forbidden local/generated paths. Ignore checks confirmed exclusion of environments, portable software, local SQLite/demo data and secret-file locations; `uv lock --check` and `git diff --check` also passed. Only the example configuration is included, with no credentials.

## Exact next action

1. Begin M7 from sections 12-14 and 23 of [PROJECT_SPEC.md](./PROJECT_SPEC.md): actual STL preview/downloads, bounded user feedback/revisions, exact artifact-bound acceptance, and the three restart choices. Reuse the existing M6 pipeline and persistent records; do not restart the project.
2. Keep the FreeCAD FEM + Gmsh + CalculiX backend for all future analysis work. M8 must connect its existing actual-region preparation/confirmation/solve API to the application and collect user-confirmed material/load/support information; an automatic CAD route never authorizes invented analysis inputs.
3. Live-assisted verification still needs Vertex project/location/current model/ADC and a running Linux Docker/Podman engine with the CAD image. Do not execute generated source in an ordinary host process to bypass these blockers. Independent M7/M8 implementation can continue while the integrations remain explicitly blocked.
4. If a job was interrupted, inspect its logs/artifacts and confirm the old owner stopped before explicit recovery/retry. No silent requeue or overwrite.

You are implementing a local prototype of an AI-assisted mechanical
engineering design system.

Solver decision updated by the user on 2026-10-26: all analysis requirements
use FreeCAD FEM with Gmsh and CalculiX. The full product journey and verification
requirements remain in scope; no commercial solver license is required.

Provider decision updated by the user on 2026-10-27: use the Gemini Developer
API with a locally entered Google AI Studio key; preserve Vertex as optional.
Load the ignored repository-root .env server-side, never expose its key, and
keep the vision-capable model configurable. See the live verification budget
and staged actual-region confirmation procedure in LIVE_SMOKE.md.

Treat this document as the authoritative implementation brief. The shared
conversation provides context, but do not require the user to repeat decisions
already specified here.

YOUR TASK

Build the application and its real integrations. Do not stop at architecture,
pseudocode, a UI mockup, or a list of recommendations.

Work incrementally, inspect the existing repository before changing it, preserve
working functionality, and verify each integration with actual execution where
the local environment permits.

The goal is a small but complete end-to-end prototype that can be developed
approximately within a day, assuming the necessary CAD/FEM software,
and LLM credentials are available.

The one-day constraint limits initial geometry complexity and analysis coverage.
It does not authorize removing the RAG advisor, multimodal input, feedback loop,
persistent state, FreeCAD integration, or analysis/reporting stages.

Do not claim that an integration works unless you have run it successfully.
If an external dependency is unavailable, implement the adapter, clearly expose
the blocked state, and continue building the remaining components.

==================================================
1. PRODUCT INTENT
==================================================

The application helps a user turn an initially vague mechanical design idea into:

1. A clearer, technically informed design brief.
2. A structured design specification.
3. Executable CadQuery code.
4. A real CAD model imported and saved through the FreeCAD Python API.
5. Geometry checks and an extensible rule-testing result.
6. A user-reviewed design with bounded revision attempts.
7. A proposed and user-confirmed engineering analysis.
8. A structured analysis specification.
9. An actual analysis executed through FreeCAD FEM, Gmsh and CalculiX.
10. A report grounded in solver results.

A central product feature is a RAG-assisted mechanical engineering conversation
that helps the user think through their idea BEFORE model generation.

This advisor must be implemented from the first version. It is not a future
enhancement or a decorative chat interface.

==================================================
2. INITIAL SCOPE AND NON-NEGOTIABLE BOUNDARIES
==================================================

Implement the entire workflow, initially supporting:

- One connected solid part.
- Simple prismatic geometry, extrusions, holes, cuts, unions, and basic fillets.
- One real linear static structural analysis.
- A simple cantilever/support arm as the deterministic integration example.
- A simple bracket or support component as the intended assisted-design demo.

Do not attempt a full rooftop-camper assembly on day one. The rooftop camper
illustrates the broader intended use case.

Maintain extensible interfaces for assemblies, more geometric selectors,
additional manufacturing rules, and other analyses.

Do not present unsupported geometry or analysis types as implemented.
Explicitly identify unsupported requests and offer a supported simplification.

An accepted CAD model means the user accepts the design representation.
It does not mean the design has passed engineering analysis.

A successful solver run does not automatically mean the design is acceptable.

==================================================
3. TECHNICAL ARCHITECTURE
==================================================

Default implementation:

- Python.
- Streamlit frontend.
- Pydantic data contracts.
- SQLite for workflow state and structured records.
- Local artifact folders for uploads, code, CAD, logs, and results.
- Configurable vision-capable LLM provider.
- A replaceable RAG retriever interface.
- CadQuery execution worker.
- FreeCADCmd adapter.
- FreeCAD FEM Python API adapter with Gmsh meshing and CalculiX solving.
- STL preview using trimesh and Plotly, or an equally lightweight viewer.
- Markdown specifications and reports.

Use a deterministic state machine for orchestration.

Separate LLM responsibilities into role-specific functions/prompts. These can
use the same model. Multiple independently running agents are not required.

Do not add a distributed task system, microservices, or a multi-agent framework
unless the existing project genuinely requires one.

Use separate worker processes/environments where CAD and solver dependencies
require them. Do not assume FreeCAD can be imported into the app's Python
environment; prefer its supplied command-line interpreter.

The app must remain responsive enough to display progress and errors during
long-running work.

==================================================
4. ENTRY FLOW
==================================================

Initial intake collects:

- What the user wants to design.
- Purpose and intended use.
- Known hard requirements.
- Known soft requirements.
- Known dimensions and units.
- Optional material or manufacturing preferences.
- Multiple reference images.

The intake must accommodate incomplete ideas. Do not force the user to already
know the answers that the advisor is intended to help discover.

Persist original intake and image bytes immediately.

Then display two routes:

OPTION 1
Title:
"Brainstorm with our AI Mechanical Engineering Maestro"

Description:
"Explore mechanisms, joints, materials, manufacturing methods, and design
trade-offs with an AI advisor supported by a mechanical engineering knowledge
base. Together, refine your idea into a clearer design brief."

Behavior:
Open a multimodal advisor chat with an editable living design brief beside it.

OPTION 2
Title:
"Design it for me—I trust your judgment"

Description:
"Start from your description. The AI will choose reasonable defaults and
clearly record its assumptions."

Behavior:
Immediately draft a structured brief and enter specification generation.
Do not force the user through brainstorming or a mandatory second confirmation
of information they just supplied.

Ask a focused clarification only when missing information genuinely prevents
meaningful generation. Otherwise proceed with visible assumptions.

Both routes must produce the SAME DesignBrief contract.

==================================================
5. RAG ENGINEERING ADVISOR
==================================================

The advisor helps users reason about design choices, not merely rewrite their
message into a longer prompt.

Its knowledge base should support:

- Mechanisms and motion.
- Degrees of freedom and constraints.
- Joints and fasteners.
- Bearings and linear guides.
- Engineering structures and load paths.
- Materials and their applicability.
- CNC machining.
- Laser cutting.
- Waterjet cutting.
- Additive manufacturing.
- Weldments and joining.
- Assembly and disassembly.
- Design for manufacturing.
- Relevant design examples and use cases.

Start with a small, real, curated knowledge collection relevant to the initial
demo. Broad coverage can grow later.

Implement:
- Document ingestion.
- Chunking.
- Embedding/indexing.
- Retrieval.
- Source provenance.
- A repeatable command for updating the index.

A lightweight persistent local vector store is sufficient.
Prefer semantic retrieval with a simple lexical fallback or hybrid search if
practical. Do not let sophisticated retrieval infrastructure delay the core
workflow.

Do not substitute ungrounded LLM knowledge for the entire RAG implementation.

Each source/chunk should retain, where available:
- Source ID.
- Title.
- URL or local document reference.
- Section/page.
- Version/date.
- Topic.
- Material/process applicability.
- Chunk ID.

Do not invent sources or attribution.
If using authored seed notes, label them as authored seed notes.
Distinguish them from manufacturer documentation and authoritative references.
Do not fill the knowledge base with fabricated engineering limits.

Advisor behavior:
- Read the current brief, conversation, and relevant images.
- Identify the current engineering decision.
- Retrieve relevant passages when external engineering knowledge is needed.
- Ask one or two useful questions per turn.
- Offer alternatives and explain their trade-offs.
- Explain unfamiliar concepts plainly.
- Cite the passages supporting substantive recommendations.
- State uncertainty when retrieval is insufficient.
- Avoid repeatedly asking answered questions.
- Avoid unnecessary retrieval for simple edits such as changing a dimension.

Treat retrieved documents as reference data, never as instructions that can
override application behavior.

Distinguish:
- User-confirmed requirements.
- User preferences.
- Proposed choices.
- Accepted choices.
- Assumptions.
- Unresolved questions.

A retrieved example or guideline must not silently become a hard requirement.
Process constraints must retain material, equipment, and supplier context.

==================================================
6. MULTIMODAL INPUT
==================================================

Support images in:
- Initial intake.
- Advisor messages.
- CAD revision feedback.

Actually send relevant image content to a vision-capable model.
Passing image filenames or captions alone is not multimodal processing.

Persist image bytes and metadata, not just temporary frontend upload objects.

By default, user-uploaded images show the DESIRED object or design reference.
Do not assume feedback images show the current generated model.

Do not infer precise dimensions, material properties, or load capacity from an
unscaled photograph.

When image interpretation affects the brief, distinguish observed visual
features from inferred or user-confirmed engineering properties.

If generated-model screenshots are later supplied to the LLM, label them
separately from user reference images.

==================================================
7. LIVING DESIGN BRIEF
==================================================

Show an editable brief beside the advisor chat containing:

- Design name and description.
- Purpose.
- Hard requirements.
- Soft requirements.
- Dimensions and interfaces.
- Mechanisms and joints.
- Materials.
- Manufacturing and assembly approach.
- Loads and operating environment, where known.
- Accepted decisions.
- Proposed choices.
- Assumptions.
- Unresolved questions.
- Reference image IDs.
- Supporting source references.

Both direct editing and chat should update the same versioned object.

Do not overwrite direct user edits with stale LLM responses.
Keep an auditable record of meaningful changes.

Buttons:
- Continue brainstorming.
- Generate this design.
- Switch to automatic design.

"Generate this design" freezes the current brief version for a CAD attempt.

The automatic route also creates a versioned brief, with inferred choices
marked as assumptions.

==================================================
8. DATA CONTRACTS
==================================================

Use validated schemas, not loosely structured prose passed between stages.

Implement at least:

Intake
DesignBrief
DesignSpec
CADGeneration
GeometryMetrics
RuleResult
DesignFeedback
AnalysisRecommendation
AnalysisSpec
AnalysisResults
ArtifactManifest
WorkflowState

DesignSpec should include:
- Schema version.
- Brief version.
- Design name and purpose.
- Units and coordinate system.
- Parameters/dimensions.
- Features.
- Hard requirements with stable IDs.
- Soft requirements with stable IDs.
- Verification method where applicable.
- Material/manufacturing intent.
- Reference images.
- Assumptions.
- Unresolved questions.

Every dimension should distinguish user-provided, inferred, and accepted values.

Generate:
- design_spec.json
- design_spec.md

Render Markdown from validated JSON. Avoid independently generating inconsistent
JSON and prose documents.

Store original intake immutably.
Store approved brief versions separately from original intake.

==================================================
9. CAD GENERATION AND EXECUTION
==================================================

The CAD creator receives:
- Current DesignSpec.
- Relevant reference images.
- Relevant accepted design decisions.
- Previous code and feedback when revising.
- Technical errors/check failures when repairing.

Generate a restricted CadQuery function with a stable interface, for example:

    def build(params):
        ...
        return result

The trusted worker owns:
- Imports.
- Parameter loading.
- Invocation.
- Export paths.
- STEP/STL export.
- Error capture.
- Artifact manifests.

Generated code should not control infrastructure, read secrets, execute shell
commands, access the network, or load arbitrary files.

Use a practical execution boundary such as a restricted container:
- No network.
- No secrets.
- Non-root execution where supported.
- Only the necessary input/job directory mounted.
- CPU/memory/time limits.

A subprocess or import blacklist alone is not a security sandbox.
Do not claim otherwise.

CadQuery creates the geometry.
Export:
- model.step
- preview.stl
- model.py
- parameters.json
- generation metadata and logs.

==================================================
10. FREECAD INTEGRATION
==================================================

Use the FreeCAD Python API through FreeCADCmd to:

- Import the generated STEP.
- Create a FreeCAD document.
- Inspect and validate the imported shape.
- Collect geometric metrics.
- Save model.FCStd.

This is a real API integration, not a file rename or instruction for the user
to import manually.

Important:
The initial FCStd contains imported geometry.
The editable parametric source remains the CadQuery script and parameters.
Do not claim to create a native FreeCAD sketch-and-feature tree.

Collect:
- Shape validity.
- Solid count.
- Volume.
- Bounding box.
- Other useful basic metrics.

Require actual expected output files and a completion manifest.
An exit code alone is insufficient evidence of a successful build.

FreeCAD failure must prevent the workflow from presenting the CAD stage as
successfully completed.

==================================================
11. RULE-BASED VALIDATION
==================================================

Implement an extensible registry from the beginning.

Initial real checks:
- STEP import succeeds.
- Shape is nonempty.
- Shape is valid.
- Exactly one solid for the supported scope.
- Volume is positive.
- Applicable bounding dimensions match specified tolerances.

Scaffold:
- Minimum wall thickness.
- Manufacturing constraints.
- Application-specific mechanical rules.
- Additional requirement verification.

RuleResult includes:
- Rule ID.
- Requirement ID if applicable.
- Status.
- Measured value.
- Expected value/tolerance.
- Message.
- Evidence/artifact reference where useful.

Statuses:
PASS
FAIL
NOT_IMPLEMENTED
NOT_APPLICABLE

An unimplemented rule must NEVER pass by default.

Separate:
- Geometry validity.
- Requirement-check coverage.
- Engineering-analysis outcome.

Failed mandatory geometry checks prevent user acceptance of the model.
Unimplemented checks may allow prototype continuation with visible status.

==================================================
12. TECHNICAL REPAIR VS USER REVISION
==================================================

These are separate mechanisms with separate counters.

Technical repair:
- Triggered by execution errors or implemented mandatory check failures.
- Provide traceback and failed checks to the CAD creator.
- Allow one automatic repair per generated revision initially.
- If repair fails, stop that stage and expose the real error.
- Do not count this as a user rejection.

User revision:
- Triggered by the user's dissatisfaction with the displayed design.
- Maximum two user rejections per attempt.
- Initial model plus one feedback-based regenerated model.

Do not create an unbounded retry loop.

==================================================
13. DESIGN PREVIEW AND FEEDBACK
==================================================

Display:
- Interactive model preview.
- Main parameters.
- Current specification.
- Assumptions.
- Rule results and coverage.
- Downloads for CAD artifacts.

Controls:
- Thumbs up / Accept design.
- Thumbs down / Revise design.
- Feedback text.
- Optional feedback images.
- Submit revision.

Support:
- Thumbs-only feedback.
- Text-only feedback.
- Text plus image feedback.
- Image feedback with an explicit revision action.

Thumbs down without details is valid. Use existing requirements to propose a
reasoned revision, clearly explaining what changed; do not invent the user's
reason for rejection.

First rejection:
- Save feedback.
- Update the brief/spec when design intent changes.
- Preserve unaffected requirements.
- Generate the next revision.
- Run FreeCAD and rule checks again.
- Display the new model.

Second rejection:
- Record a failed design attempt.
- Preserve both revisions, feedback, and artifacts.
- Offer restart choices.

Accept:
- Bind acceptance to the exact revision and geometry artifact.
- Proceed to analysis intake.

==================================================
14. RESTART BEHAVIOR
==================================================

Preserve two distinct snapshots:
1. Original intake and images.
2. Approved/refined brief used for model generation.

After two rejections, offer:

A. Retry from approved brief.
B. Return to brainstorming with failed-attempt feedback.
C. Start from original idea.

A restart creates a new attempt ID and resets its counters.
Do not overwrite failed attempts.

Starting from original idea prepopulates the original answers and images.

Returning to brainstorming preserves prior engineering decisions and makes
failed-model feedback available to the advisor.

==================================================
15. ANALYSIS INTAKE AND RECOMMENDATIONS
==================================================

After design acceptance, ask:
"What do you want to learn about this design?"

Use:
- Design purpose.
- Requirements.
- Material/manufacturing context.
- Accepted geometry.
- Known operating conditions.

Recommend suitable analyses with:
- Analysis name.
- Engineering question answered.
- Why relevant.
- Required inputs.
- Whether execution is currently supported.

Initial real execution:
- Linear static structural.

Recognize but mark as not yet executable:
- Modal.
- Random vibration.
- Fatigue.
- Transient structural.
- Other requested analysis types.

Example:
For an overlanding rooftop camper, potentially relevant analyses include static
loads, modal behavior, vibration response, fatigue, and mount displacement/load
cases. Do not pretend that one static solve establishes vibration durability
or fatigue life.

Do not invent excitation spectra, fatigue curves, damping, loading histories,
or mounting conditions.

==================================================
16. ANALYSIS SPECIFICATION
==================================================

Generate:
- analysis_spec.json
- analysis_spec.md

Fields:
- Schema version.
- Accepted design revision.
- Geometry hash.
- Analysis type.
- Engineering question.
- Material ID and property source.
- Unit system.
- Supports.
- Loads.
- Region selectors.
- Mesh settings.
- Requested outputs.
- Acceptance limits.
- Assumptions.
- Missing inputs.
- Supported execution status.

Require sufficient material, load, and support information before execution.

Use a small verified material allowlist initially.
Do not silently assign a default material that contradicts the design brief.

Show the proposed setup and selected geometric regions before solving.
Require user confirmation of analysis inputs.

Choosing automatic design earlier does not imply approval of invented analysis
loads or boundary conditions.

==================================================
17. GEOMETRIC REGION SELECTION
==================================================

Do not persist raw face IDs across geometry revisions or STEP imports.

Implement a limited geometric selector interface, initially supporting a
simple cantilever:
- Planar face at minimum X.
- Planar face at maximum X.

Define selectors using position, orientation, and explicit tolerances.

Resolve the selectors INSIDE FreeCAD FEM after importing the accepted STEP.
Create labeled FEM constraints bound to the resolved faces there.

Reject:
- Zero matching faces.
- Ambiguous selections.
- Invalid or overlapping support/load regions where inappropriate.

Display the actual selected regions before solving.
Do not merely display the textual selector and call it verified.

Additional bracket mounting selectors can be added after the deterministic
cantilever path works.

Check imported geometry dimensions to catch unit scaling errors.
All values passed across API boundaries require explicit unit handling.

==================================================
18. REAL FREECAD FEM EXECUTION
==================================================

Use the FreeCAD FEM Python API through FreeCADCmd to import geometry, create
the FEM analysis, mesh with Gmsh, and solve with installed CalculiX (ccx).
No commercial solver license or separate Python solver-client package is required.

Verify installed-version compatibility rather than blindly assuming the newest
package is compatible.

Implement a fixed analysis template parameterized by AnalysisSpec.
Do not have the LLM write arbitrary solver scripts.

The real adapter must:
1. Launch or connect to FreeCAD FEM.
2. Transfer/import the accepted STEP file.
3. Verify geometry and units.
4. Assign the specified verified material.
5. Resolve support/load selections.
6. Generate the mesh.
7. Apply boundary conditions and loads.
8. Add requested result objects.
9. Solve.
10. Check actual completion/errors.
11. Extract results.
12. Export contour images and logs.
13. Save the analysis project if supported.
14. Clean up owned solver sessions appropriately.

Initial outputs:
- Maximum total displacement.
- Maximum equivalent/von Mises stress.
- Reaction forces.
- Mesh information.
- Solver completion/status.
- Result images.
- Solver logs.

Prevent stale results from being attached to a revised design.
Bind every solve to geometry hash and analysis-spec version.

If FreeCAD FEM, Gmsh or CalculiX is absent, unavailable, or incompatible:
- Show BLOCKED with a useful reason.
- Preserve the rest of the workflow.
- Do not fabricate numerical results.
- Do not silently switch to a mock solver.

Mocks may exist for automated tests but must never masquerade as real execution.

==================================================
19. REPORTING
==================================================

Generate:
- results.json
- report.md
- Relevant images and downloadable artifacts.

Build numerical tables deterministically from solver results.
Use the LLM only to explain supplied results, assumptions, and limitations.

Include:
- Design revision and geometry hash.
- Analysis question.
- Material and source.
- Loads, supports, and units.
- Mesh settings and counts where available.
- Solver status.
- Displacement and equivalent stress.
- Reaction-force balance.
- Plots.
- Comparison with supplied acceptance criteria.
- Missing or unimplemented checks.
- Assumptions and limitations.

If no acceptance criterion exists, say:
"Computed; acceptance criterion not provided."

A failed or incomplete solve must produce a failure report, not a success report.

Label first-version results as preliminary single-mesh results.
Do not claim mesh convergence or validated peak stresses without testing them.

==================================================
20. STATE, PERSISTENCE, AND ARTIFACTS
==================================================

Use explicit workflow states. Include equivalents of:

INTAKE
ROUTE_SELECTION
ADVISOR_CHAT
BRIEF_READY
SPEC_GENERATION
CAD_GENERATION
CAD_EXECUTION
FREECAD_VALIDATION
RULE_CHECKS
DESIGN_REVIEW
RESTART_OFFER
ANALYSIS_INTAKE
ANALYSIS_SPEC_REVIEW
ANALYSIS_EXECUTION
REPORT_READY
BLOCKED
ERROR

Persist:
- Project/session ID.
- Original intake.
- Route selection.
- Chat messages and image references.
- Retrieved source references.
- Brief/spec versions.
- Attempt and revision IDs.
- Technical repair counts.
- User rejection counts.
- Current state.
- Feedback history.
- Accepted revision.
- Analysis configurations and runs.
- Artifact manifests.
- Errors and stage logs.

Use atomic writes/transactions where needed.
Frontend reruns must not duplicate LLM generations, CAD builds, or solver runs.
Use job IDs/statuses or another explicit idempotency mechanism.

Recover persisted sessions after application restart.
Do not automatically rerun an interrupted expensive operation without checking
its state and artifacts.

Suggested artifact layout:

data/
  knowledge/
  projects/
    <project_id>/
      intake/
      uploads/
      briefs/
      attempts/
        <attempt_id>/
          revisions/
            <revision_id>/
      analyses/
        <analysis_id>/

Use unique revision directories. Never overwrite an accepted model with a
newly generated candidate.

==================================================
21. CODE ORGANIZATION
==================================================

Use a similarly clear structure, adapting to an existing repository if needed:

app.py
config.py
schemas.py
workflow.py
storage.py

agents/
  advisor.py
  spec_writer.py
  cad_creator.py
  revision_writer.py
  analysis_planner.py
  report_writer.py

rag/
  ingest.py
  retriever.py
  sources.py

workers/
  cad_worker.py
  freecad_worker.py
  fem_worker.py

analysis/
  selectors.py
  static_structural_template.py

rules/
  registry.py
  geometry.py
  manufacturing.py

reporting.py
tests/
examples/
README.md
.env.example

Keep UI, orchestration, LLM calls, and CAD/solver execution separate.

==================================================
22. IMPLEMENTATION ORDER
==================================================

1. Inspect repository and local environment.
   Identify Python, FreeCAD, FreeCAD FEM, container runtime, and available credentials.
   Inspect configuration without printing secrets.

2. Create contracts, persistence, and workflow skeleton.

3. Prove a deterministic vertical slice:
   Hardcoded cantilever parameters
   -> CadQuery
   -> STEP/STL
   -> FreeCAD API
   -> checks
   -> FreeCAD FEM
   -> actual result extraction/report.

4. Implement initial intake and both routes.

5. Implement a small real RAG knowledge base and multimodal advisor.
   Connect it to the shared living DesignBrief.

6. Implement spec generation and LLM CadQuery creation.

7. Implement preview, feedback revision, failed attempts, and restart.

8. Implement analysis intake/recommendations and specification review.
   Connect them to the proven solver template.

9. Verify persistence, errors, stale-artifact prevention, and reporting.

If a dependency blocks step 3, report it clearly and continue independent work.
Do not abandon the application or replace missing execution with fabricated data.

==================================================
23. REQUIRED VERIFICATION
==================================================

Repeatable real reference integration: `python -m cli --data-dir data verify-fem-e2e`.
This exercises fresh repository-authored CadQuery geometry, app STL review and
artifact-bound acceptance, explicit actual-region analysis confirmation, real
FreeCAD FEM/Gmsh/CalculiX execution, in-app fields/report and numerical checks.
It does not substitute for live Vertex or generated-code sandbox verification.
See FEM_INTEGRATION_REPORT.md for actual commands/results and test boundaries.

Use focused tests for state transitions and integration boundaries.

Demonstrate:

RAG:
- Ingest an actual source.
- Retrieve a relevant passage.
- Show a cited engineering recommendation.
- Accept a choice and update the brief.
- Handle insufficient evidence honestly.

Multimodal:
- Process an actual reference image through the vision model.
- Preserve the image through restart.

CAD:
- Generate/export a real model.
- Import/save it through FreeCAD.
- Display actual preview geometry.
- Capture a failed build.
- Enforce the technical repair budget.
- Show scaffolded tests as NOT_IMPLEMENTED.

Feedback:
- First rejection produces a new revision.
- Second rejection records failure.
- All three restart choices preserve the correct information.
- Acceptance binds to the exact artifact.

Analysis:
- Import the accepted geometry.
- Resolve and display actual selected regions.
- Block missing inputs and ambiguous selections.
- Perform a real static solve when FreeCAD FEM is available.
- Confirm report values match extracted solver values.
- Reject stale results after geometry changes.

Persistence:
- Reload a session after restarting the application.
- Ensure frontend reruns do not duplicate jobs.

Numerical sanity:
- For the simple cantilever, compare displacement against the appropriate
  elementary beam-theory estimate under matching assumptions.
- Check reaction-force equilibrium.
- Do not overinterpret local peak stresses near idealized constraints.

==================================================
24. HANDOFF REQUIREMENTS
==================================================

Provide:
- Implemented source code.
- Dependency setup and tested versions.
- Configuration example with no secrets.
- Exact startup commands.
- Knowledge-base ingestion/update command.
- FreeCAD and FreeCAD FEM executable-path configuration.
- Repeatable deterministic demo.
- Repeatable assisted-design demo.
- Actual verification outcomes.
- Known limitations and blocked dependencies.

Clearly distinguish:
- Implemented and verified.
- Implemented but unverified.
- Blocked by environment.
- Planned or scaffolded.

Do not describe the complete product as working if the solver path is blocked.
Do not hide core requirements behind TODOs and call the prototype complete.

LLM provider decision (updated 2026-10-27):
Use Gemini Developer API with an AI Studio API key and a vision-capable model for the
application's advisor, specification generation, CAD code generation,
revision, analysis planning, and report explanation.
Preserve Google Cloud Vertex AI as an optional provider. Do not require an OpenAI key.

Use configurable provider and model ID. In Developer API mode, read GEMINI_API_KEY
server-side from the environment, with ignored repository-root .env loading for
local development. Do not display or persist credentials in project records.
In Vertex mode, use configurable project/location/model and local ADC.
Verify current model availability and SDK usage before implementation.
Keep the provider adapter replaceable.

Use local embeddings initially for RAG to minimize setup and recurring cost.


Proceed with reasonable implementation decisions.
Ask the user only when a missing credential, unavailable dependency, or
materially consequential ambiguity cannot be resolved from the project.

The final result should preserve the complete product journey:
initial idea -> optional RAG engineering conversation -> structured brief
-> design spec -> CadQuery -> FreeCAD model -> checks -> bounded feedback
-> accepted design -> analysis conversation/spec -> real FreeCAD FEM execution
-> evidence-based report.

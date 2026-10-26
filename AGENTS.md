# Project continuity

- Read [PROJECT_SPEC.md](./PROJECT_SPEC.md), [PLAN.md](./PLAN.md), [STATUS.md](./STATUS.md) and [BACKLOG.md](./BACKLOG.md) before changing the implementation. Continue the existing project; preserve working code and persisted sessions.
- The user-approved analysis backend is **FreeCAD FEM + Gmsh + CalculiX**, controlled by the supplied FreeCADCmd Python API. All solver requirements and future tasks refer to this backend. There is no commercial solver or license dependency.
- Support Gemini Developer API with a server-side AI Studio key from the ignored repository-root .env; preserve optional Vertex with local ADC. Never print credentials. JSON contracts are authoritative; render specifications and numerical reports from validated objects.
- Live verification is explicitly opt-in: one end-to-end smoke journey, maximum five generation requests across all roles, SDK/application retries disabled and no automatic technical repair. Preserve its durable request ledger and successful stages after any failure; obtain a new user budget before another live run. Require the user's confirmation of the actual resolved regions before its solve.
- Generated CAD must execute only inside the restricted container. AST validation and ordinary subprocesses are not security sandboxes. Missing dependencies produce explicit blocked states, never fabricated geometry or solver values.
- Preserve immutable intake, revision artifacts, accepted geometry hashes, bounded repair/rejection counters, and explicit analysis confirmation against the actual resolved regions.
- Use `.venv/Scripts/python.exe -m pytest -q` and `-m cli doctor` on Windows. Record actual evidence separately from provider/container doubles and previous-machine results in [STATUS.md](./STATUS.md).

## Learnings

FreeCAD/OpenCASCADE native STEP, STL and FCStd operations can fail on long Windows paths even when Python and `Store` accept extended paths; the native STL writer can return without producing a file. Use short private staging directories for native CAD/FEM IO, verify actual nonempty outputs, then publish them back through Python without overwriting revision artifacts. For example, export `preview.stl` in the staging directory rather than directly in a deep project/attempt/revision tree; retain the original artifact paths and hashes in manifests. The long-path pipeline regression test in [tests/test_generation.py](./tests/test_generation.py) covers the CAD/FreeCAD boundary.

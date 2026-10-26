# Real FreeCAD FEM app integration

Date: 2026-10-26. Final full suite: **163 passed, no skips**, in 122.12 seconds; two cases are marked `real_integration`. This is actual CAD/mesher/solver evidence, not a mocked solver result or a complete live-Gemini demonstration.

## Reproduce

From the repository root on Windows:

```powershell
uv sync --python 3.12 --frozen --extra test --extra cad --extra ui --extra llm --extra fem
.\.venv\Scripts\python.exe -m cli doctor
.\.venv\Scripts\python.exe -m cli --data-dir data verify-fem-e2e
```

The command drives the real Streamlit app using AppTest: generate reference cantilever → show actual STL → accept the exact STEP hash → explicitly select reference material/load → prepare actual imported faces → confirm setup → solve → display displacement/stress and report → reopen the persisted result without another solve. It scopes only the data-directory environment variable; CAD, meshing, FreeCAD, result extraction and the solver are not replaced by doubles.

The geometry is generated afresh by the repository-authored CadQuery reference generator. It is not a cached STEP, fixture mesh, LLM-generated script or proof of isolated generated-code execution. Vertex credentials and a container runtime are not required for this trusted reference path. Arbitrary generated scripts still require the restricted container.

To run just the two real FEM integration regressions:

```powershell
.\.venv\Scripts\python.exe -m pytest -q -m real_integration
```

## Executables and actual commands

| Executable | Observed version | Location relative to repository |
| --- | --- | --- |
| `python.exe` | 3.12.13 | `.venv/Scripts/python.exe` |
| CadQuery | 2.6.1 | Locked `cad` extra |
| `freecadcmd.exe` | 1.1.4 | `.tools/freecad/FreeCAD_1.1.4-Windows-x86_64-py311/bin/freecadcmd.exe` |
| `gmsh.exe` | 4.15.0 | Same FreeCAD `bin` directory |
| `ccx.exe` | 2.22 | Same FreeCAD `bin` directory |

The fixed trusted template runs `freecadcmd.exe workers/fem_script.py` for preparation and solve, with its job selected by `CAE_FEM_JOB`. The mesh command is `gmsh.exe - <native-stage>/mesh/shape2mesh.geo`. The solve command is `ccx.exe -i Mesh`, with `<native-stage>/solver` as working directory. Exact executable paths, temporary paths, versions and arguments from this run are saved in `execution.json`, `prepare_job.json`, `solve_job.json`, `gmsh.log` and `calculix.log`. Short private native IO staging avoids Windows path-length failures; outputs are retained in the persistent analysis directory.

## Physical setup and results

- Actual 100 × 20 × 10 mm rectangular solid, length along X.
- Sourced FreeCAD Steel-Generic reference material: E = 200000 MPa, Poisson ratio = 0.3, density = 7900 kg/m³.
- Fixed planar minimum-X face; resultant `(0, 0, -100)` N distributed on the actual maximum-X face.
- 3 mm target quadratic tetrahedral mesh: 7,761 nodes and 4,346 elements.
- Material and constraints are real FreeCAD FEM objects; the fixed analysis template writes the actual CalculiX input.

| Check | Observed value |
| --- | ---: |
| Maximum solver displacement | 0.09964792921575177 mm |
| Euler–Bernoulli estimate | 0.10000000000000000 mm |
| Absolute displacement difference | 0.00035207078424823 mm |
| Relative displacement difference | 0.3520707842482318% |
| Maximum extracted von Mises stress | 29.885778687934497 MPa |
| Support reaction X | 2.345342e-10 N |
| Support reaction Y | 3.102960e-10 N |
| Support reaction Z | 100.0 N |
| Reaction-balance residual magnitude | 3.8896002183468676e-10 N |
| Residual / applied force magnitude | 3.889600218346868e-12 |

The beam estimate uses `I = width × height³ / 12 = 1666.6666666667 mm⁴` and `δ = F L³ / (3 E I)`. It assumes a slender, linear-elastic rectangular cantilever with a matching tip resultant. The integration sanity gates are displacement within 12% of this elementary estimate and relative reaction residual below 1e-4. These are numerical verification gates, not design acceptance criteria.

## App and retained evidence

The persistent app run is project `86d4169f8c74414cbbe680239001c105`, analysis `70889c1e4617419cb5eac55600868b3f`, accepted revision `0d6991021fa141f1803fd50ff90b6427`. Its STEP SHA-256 is `8405e5d7f7ac5b4e064cdc70a5fde8c88989d2dbeebba415665fad437e86adde`.

Open that session in the app sidebar. The report screen displays two actual nodal result plots, displacement/stress values, beam comparison, reaction residual, the deterministic report, solver logs and downloads. Browser verification also confirmed those displayed values and plots. Reopening uses the same persisted run and does not enqueue another solve.

The local evidence directory is `data/projects/86d4169f8c74414cbbe680239001c105/analyses/70889c1e4617419cb5eac55600868b3f/`:

| File | Evidence |
| --- | --- |
| `analysis_spec.json`, `analysis_spec.md` | Reviewed inputs and explicit units |
| `regions.json`, `regions.html`, `setup.FCStd` | Actual selected faces and prepared analysis |
| `gmsh.log`, `mesh/shape2mesh.geo`, `mesh/model_Mesh.unv` | Real mesher command, output and generated mesh |
| `solver/Mesh.inp` | Material, mesh, supports, load and requested outputs written by FreeCAD FEM |
| `calculix.log`, `solver/Mesh.sta` | Actual CalculiX completion and execution evidence |
| `solver/Mesh.frd`, `solver/Mesh.dat` | Actual displacement/stress fields and extracted support reactions |
| `analysis.FCStd` | Saved FEM mesh and imported solver results |
| `solver_results.json`, `results.json` | Raw extraction and validated result contract |
| `verification.json` | Beam and equilibrium comparisons |
| `execution.json` | Exact executable names, versions and arguments |
| `integration_report.md`, `report.md` | Numerical report, assumptions, limits and evidence links |
| `displacements_mm.png`, `von_mises_mpa.png` | Actual preliminary nodal fields |
| `app_evidence.json` | App actions, displayed metrics, plot count and no-mock declaration |
| `prepare.log`, `solve.log`, `completion.json` | Owned-worker logs and hash/size completion evidence |

The database, geometry, native software and result bundle are intentionally ignored by Git. This report records reproducible evidence; another PC must restore dependencies and rerun the command, or transfer the local bundle separately.

## What is mocked, blocked or limited

- `tests/test_app_fem_e2e.py` and the marked solver case in `tests/test_fem_integration.py` use actual installed tools and no solver fallback. They skip explicitly when required tools are missing; the verification CLI instead reports that blockage as an error.
- `tests/test_review.py` uses explicitly synthetic artifacts to test transactions, acceptance, feedback limits and restart preservation. Those fixture metrics are not integration evidence.
- `tests/test_generation.py` includes provider/container doubles, including a labeled container double with actual trusted CAD/FreeCAD. Those tests do not verify a live model or a sandboxed generated build.
- Live Vertex/Gemini, LLM-generated revision execution and the actual Docker/Podman image remain blocked by missing credentials/runtime. No generated-code host-execution shortcut was introduced.
- Engineering results are preliminary single-mesh values. No convergence, certified stock properties, validated constraint peak stress, fatigue, vibration durability or design acceptance is claimed. Computed; acceptance criterion not provided.

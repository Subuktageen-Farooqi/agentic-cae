# agentic-cae

A functional local prototype that automates the mechanical design and validation pipeline from concept to final report.

## Problem Statement
Traditional Computer-Aided Engineering (CAE) workflows are fragmented and manually intensive, requiring extensive human intervention to move an initial mechanical concept through structural specification, 3D CAD modeling, validation, finite element meshing, and multi-step solver simulations. This disconnection introduces severe bottlenecks, manual verification delays, and transcription risks between raw design intents and downstream engineering feedback loops.

## Solution
This repository presents a functional local prototype that automates the entire mechanical design and validation pipeline from concept to final report. Key system features include:

*   **Automated Pipeline:** Transforms ideas into structured briefs, filters queries via local RAG engineering advice, and outputs automated CadQuery source scripts.
*   **Headless Validation:** Drives deterministic CAD modifications and imports models programmatically using FreeCAD engines.
*   **Integrated Simulation:** Coordinates open-source finite element analysis using Gmsh meshers and CalculiX linear static solvers.
*   **Result Verification:** Generates live evidence-based Streamlit reports complete with nodal displacement checks, reaction forces, and interactive 3D STL previews.

## Technology Stack
*   **Language & Infrastructure:** Python 3.12, managed with the `uv` toolchain.
*   **CAD Engines:** CadQuery API and headless FreeCAD (`freecadcmd`).
*   **FEA / Simulation Tools:** CalculiX structural solver and Gmsh finite element grid generators.
*   **AI Backend:** Google Gen AI SDK (Gemini Developer API with `gemini-3.5-flash-lite`).
*   **Isolation & State:** Restricted Podman/Docker Linux container runtime and transaction-safe SQLite databases.

## Architecture
The system functions as a modular automated pipeline using dedicated background workers to segregate trusted and untrusted executions:

```
[User Intake / Idea] ──> [Local TF-IDF / BM25 RAG Advice] ──> [Structured Brief Spec]
                                                                     │
[Streamlit Report] <── [CalculiX Solver <── FreeCAD FEM] <── [Podman CAD Sandbox]
```

The application maintains append-only transactional integrity locally. Containerized tasks operate completely isolated from local configurations, utilizing strict resource constraints and non-root users to ensure system defense-in-depth.

## Setup Instructions
To initialize the execution environment on Windows PowerShell, run:

```powershell
# Restore the frozen environment directly with uv
uv sync --python 3.12 --frozen --extra test --extra cad --extra ui --extra llm --extra fem

# Execute integration tests
.\.venv\Scripts\python.exe -m pytest -q

# Launch the Streamlit local dashboard interface
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

## Demo
You can generate a trusted cantilever structural trial locally to review system logic, interactive outputs, and numerical calculations:

```powershell
# Run the automataed end-to-end reference solver demo
.\.venv\Scripts\python.exe -m cli --data-dir data demo-cantilever
```

*Note: Successful runs export step-by-step documentation, spatial configuration files, and numerical result sets natively under your structured local directory paths.*

## Team Contributions
*   **Subuktageen Farooqi:** Core software architecture design, container sandboxing configuration, database schemas, local search integration, and automated application tooling.

## License
This project is licensed under the **MIT License** — see the full `LICENSE` file for details.

## Acknowledgements
We express our appreciation to the foundational open-source engineering packages powering this ecosystem:

*   The **FreeCAD Open-Source Community** for portable command-line modeling hooks.
*   The **CalculiX and Gmsh Projects** for robust, accessible mesh generation and structural solver systems.

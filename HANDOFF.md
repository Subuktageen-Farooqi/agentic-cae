# Laptop handoff and demo

The GitHub `main` branch contains source, tests, project instructions and curated knowledge. The saved projects, generated CAD/FEM artifacts and live-request ledgers are local data, so Git alone cannot reopen them. Transfer the **private** ZIP below to the laptop by a trusted private method; never commit it. It does not contain the AI Studio key, Python environment, FreeCAD installation, Podman machine or container image.

Current private archive on this PC: `.tools/handoff/agentic-cae-state-20261027-040337.zip` (20,110,905 bytes; SHA-256 `cb64240f400e2dfcbeae2ee2259acb5ec3283b438366cd3362cbf8fa78eb1480`). It holds a consistent SQLite snapshot, seven projects, 170 project artifact files and three request ledgers. An isolated restore reopened all seven projects and verified all ten stored artifact manifests. A GUI-saved copy of the bracket FreeCAD document and FreeCAD's backup are retained alongside the original manifest-matching document.

## On the laptop

1. Clone `https://github.com/Subuktageen-Farooqi/agentic-cae` and check out `main`. Keep the transferred ZIP outside the Git checkout or under ignored `.tools/handoff/`.
2. Install Python 3.12 and restore the locked environment from the repo root:

   ```powershell
   uv sync --python 3.12 --frozen --extra test --extra cad --extra ui --extra llm --extra fem
   .\.venv\Scripts\python.exe -m cli doctor
   ```

3. Before creating local projects in this fresh clone, check and restore the private archive. Restore refuses to overwrite existing local state:

   ```powershell
   .\.venv\Scripts\python.exe scripts\handoff_state.py inspect 'C:\path\to\agentic-cae-state-20261027-040337.zip'
   .\.venv\Scripts\python.exe scripts\handoff_state.py restore 'C:\path\to\agentic-cae-state-20261027-040337.zip'
   .\.venv\Scripts\python.exe -m cli projects
   ```

4. Install FreeCAD with `freecadcmd.exe`, Gmsh and CalculiX for CAD/FEM. The prior PC used FreeCAD 1.1.4 with bundled Gmsh 4.15.0 and CalculiX 2.22. If automatic discovery fails, set `FREECAD_CMD`, `GMSH_EXE` and `CALCULIX_CCX` in the laptop's private `.env`. For **new AI-generated CAD**, also start a Linux Docker/Podman engine and build `agentic-cae-cad:2.6.1` using `podman build -f workers/Dockerfile -t agentic-cae-cad:2.6.1 .`. See [LIVE_SMOKE.md](./LIVE_SMOKE.md) for Windows WSL2/Podman setup. Restoring saved projects and viewing their STL does not need the container.
5. Copy [.env.example](./.env.example) to an ignored `.env` and enter the laptop's `GEMINI_API_KEY` locally if new Gemini work is wanted. Set `LLM_PROVIDER=gemini_developer` and `GEMINI_MODEL_ID=gemini-3.5-flash-lite`. Never paste the key into chat or commit it. Opening saved projects does not spend Gemini quota.

The archive preserves stopped ledgers and successful stages. Do not reset or replay them. [STATUS.md](./STATUS.md) records what was actually verified and the next design-review action. A new chat on the laptop can be given: “Read AGENTS.md, PROJECT_SPEC.md, PLAN.md, STATUS.md, BACKLOG.md and HANDOFF.md. Inspect the restored repository and continue from the saved bracket design review. Preserve sessions and request ledgers; do not make a Gemini call without a fresh budget.”

## Demo

There is no packaged Windows `.exe`. Start the Streamlit app from the repo root:

```powershell
.\.venv\Scripts\python.exe -m streamlit run app.py --server.address=127.0.0.1
```

Open `http://127.0.0.1:8501`. In **Sessions**, select the saved project beginning `3440f0ca` and choose **Open selected session**. Its `DESIGN_REVIEW` screen shows the actual generated three-way bracket STL, parameters, checks and STEP/STL/FCStd downloads. Gemini generated the specification and initial CadQuery source; the first code failed and one logged **manual** correction made the real container/FreeCAD artifacts. This bracket has not been accepted or analyzed in FEM. Creating a fresh AI design requires the key and running container and spends live requests.

For a zero-Gemini-quota CAD-to-FEM demonstration, choose **Real integration example** → **Generate reference cantilever**, inspect and accept the actual solid, choose the reference analysis setup, prepare and inspect the actual selected support/load faces, explicitly confirm them, then run the FreeCAD FEM/Gmsh/CalculiX solve. The app displays plots and a report from actual solver files. The 100 × 20 × 10 mm, 100 N reference run previously yielded 0.0996479292 mm maximum displacement versus 0.1000000000 mm beam theory; see [FEM_INTEGRATION_REPORT.md](./FEM_INTEGRATION_REPORT.md). It is a preliminary single-mesh reference, not a bracket safety analysis.

The normal application uses `FreeCADCmd` in the background and **does not automatically open the FreeCAD GUI**. It shows the STL in the browser and saves/downloads STEP and FCStd files. To display the bracket in FreeCAD GUI, open a **copy** of `data/projects/3440f0cad7c94e5793a45332b4302405/attempts/74c896bc7f5841848a187ac9c72c638f/revisions/97708275aec14562a47600705f57f6c2/freecad-1/model.FCStd`. Saving the original directly from FreeCAD changes its bytes and invalidates its stored artifact hash. Use the copy for edits or demonstration; the original remains an immutable evidence artifact.

The same-account chat may be visible on another device, but the app/agent host operates on that computer's local files and software. The Git checkout plus this private archive and handoff record are the reliable transfer path; seeing the conversation alone does not transfer the SQLite database, CAD files, key, FreeCAD or Podman.

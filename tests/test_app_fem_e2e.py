"""Real app-level integration, without mocked geometry, provider or solver."""
import json
from pathlib import Path
import pytest
from config import Config
from examples.integration_run import run
from workers.fem_worker import availability


@pytest.mark.real_integration
def test_real_cad_to_app_confirmation_solver_results_report_and_restart(tmp_path):
    config=Config.from_env()
    if not availability(config.freecad_cmd,config.calculix_exe,config.gmsh_exe)[0]:
        pytest.skip("Real FreeCAD FEM/Gmsh/CalculiX are required; no mock fallback")
    evidence=run(tmp_path/"real-e2e")
    assert evidence["mocked_components"]==[] and evidence["result_provenance"]=="actual_solver"
    assert evidence["displayed_result_charts"]>=2
    directory=Path(evidence["directory"])
    execution=json.loads((directory/"execution.json").read_text(encoding="utf-8"))
    assert execution["freecad"]["version"] and execution["gmsh"]["version"] and execution["calculix"]["version"]
    assert "Job finished" in (directory/"calculix.log").read_text(encoding="utf-8")
    assert "Computed; acceptance criterion not provided." in (directory/"integration_report.md").read_text(encoding="utf-8")

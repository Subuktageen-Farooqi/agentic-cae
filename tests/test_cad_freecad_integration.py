import json
from pathlib import Path

import pytest

from config import Config
from rules.geometry import bounding_dimension_rules, core_geometry_rules, mandatory_geometry_passes
from schemas import RuleStatus
from workers.cad_worker import CAD_ROLES, run_trusted_build
from workers.freecad_worker import FREECAD_ROLES, run_freecad_validation


def _cad(tmp_path):
    root = tmp_path / "data"
    revision = root / "projects" / "test-project" / "attempts" / "a" / "revisions" / "r"
    manifest = run_trusted_build(project_id="test-project", job_id="cad-job",
                                 model_source=Path("examples/cantilever_model.py"),
                                 params={"length_mm": 100, "width_mm": 20, "height_mm": 10, "fillet_mm": 0},
                                 output_dir=revision, project_root=root)
    return root, revision, manifest


def test_real_cadquery_exports_all_expected_outputs(tmp_path):
    root, revision, manifest = _cad(tmp_path)
    assert {item.role for item in manifest.artifacts} == CAD_ROLES
    assert all((root / item.relative_path).stat().st_size == item.size_bytes > 0 for item in manifest.artifacts)
    assert json.loads((revision / "generation.json").read_text())["completed"] is True
    assert "trusted_deterministic" in (revision / "generation.json").read_text()


def test_cad_output_is_immutable(tmp_path):
    root, revision, _ = _cad(tmp_path)
    with pytest.raises(FileExistsError):
        run_trusted_build(project_id="test-project", job_id="other",
                          model_source=Path("examples/cantilever_model.py"),
                          params={"length_mm": 100, "width_mm": 20, "height_mm": 10},
                          output_dir=revision, project_root=root)


def test_failed_cad_build_does_not_claim_completion(tmp_path):
    root = tmp_path / "data"
    revision = root / "projects" / "test-project" / "bad"
    with pytest.raises(KeyError):
        run_trusted_build(project_id="test-project", job_id="bad", model_source=Path("examples/cantilever_model.py"),
                          params={"width_mm": 20, "height_mm": 10}, output_dir=revision, project_root=root)
    assert not (revision / "generation.json").exists()


def test_real_freecad_import_metrics_fcstd_and_geometry_rules(tmp_path):
    config = Config.from_env()
    if not config.freecad_cmd:
        pytest.skip("FreeCADCmd is not configured or discovered")
    root, revision, _ = _cad(tmp_path)
    metrics, manifest = run_freecad_validation(
        freecad_cmd=config.freecad_cmd, project_id="test-project", job_id="freecad-job",
        revision_id="r", step_path=revision / "model.step", output_dir=revision,
        project_root=root, timeout_seconds=120)
    assert {item.role for item in manifest.artifacts} == FREECAD_ROLES
    assert (revision / "model.FCStd").stat().st_size > 0
    assert metrics.step_import_succeeded and metrics.shape_valid and metrics.shape_nonempty
    assert metrics.solid_count == 1 and metrics.volume_mm3 == pytest.approx(20000, rel=1e-7)
    rules = core_geometry_rules(metrics) + bounding_dimension_rules(
        metrics, {"x": (100, 0.01), "y": (20, 0.01), "z": (10, 0.01)})
    assert all(rule.status == RuleStatus.PASS for rule in rules)
    assert mandatory_geometry_passes(rules)


def test_freecad_failure_requires_outputs_not_exit_code_alone(tmp_path):
    root, revision, _ = _cad(tmp_path)
    with pytest.raises((FileNotFoundError, OSError)):
        run_freecad_validation(freecad_cmd=str(tmp_path / "missing-freecad.exe"), project_id="test-project",
                               job_id="freecad-job", revision_id="r", step_path=revision / "model.step",
                               output_dir=revision / "other", project_root=root, timeout_seconds=10)
    assert not (revision / "other" / "model.FCStd").exists()

"""Real FreeCAD FEM tests when available; fixtures never substitute for a solve."""
import hashlib
from pathlib import Path

import pytest

from analysis.materials import reference_steel, validate_material
from analysis.sanity import cantilever_tip_displacement_mm, rectangular_second_moment_mm4, vector_magnitude
from config import Config
from schemas import AnalysisSpec, BoundingBox, Load, MeshSettings, RegionSelector, Support
from workers.cad_worker import run_trusted_build
from workers.fem_worker import (FEMUnavailable, availability, execute_static_or_block,
                                parse_reaction_totals, prepare_static)


def test_dat_reactions_are_extracted_from_support_totals_not_inferred_equilibrium():
    raw = "total force (fx,fy,fz) for set CAE_SUPPORT_NODES and time 1.0\n\n 1.0D-08 0.0 9.99999E+01\n"
    assert parse_reaction_totals(raw) == pytest.approx((1e-8, 0, 99.9999))
    with pytest.raises(ValueError, match="no finite"):
        parse_reaction_totals("Job finished; no requested support output")


def test_unknown_material_is_not_silently_substituted():
    steel = reference_steel()
    validate_material(steel)
    with pytest.raises(ValueError, match="allowlist"):
        validate_material(steel.model_copy(update={"name": "Aluminum"}))


def test_real_fem_cantilever_prepare_confirmation_solve_and_stale_checks(tmp_path):
    config = Config.from_env()
    if not availability(config.freecad_cmd, config.calculix_exe, config.gmsh_exe)[0]:
        pytest.skip("Real FreeCAD FEM, CalculiX and Gmsh are not installed/configured")
    root = tmp_path / "data"
    revision = root / "cad"
    run_trusted_build(project_id="integration", job_id="cad", model_source=Path("examples/cantilever_model.py"),
                      params={"length_mm": 100, "width_mm": 20, "height_mm": 10},
                      output_dir=revision, project_root=root)
    step = revision / "model.step"
    spec = AnalysisSpec(accepted_revision_id="integration", geometry_hash=hashlib.sha256(step.read_bytes()).hexdigest(),
        analysis_type="linear_static_structural", engineering_question="Deflection of the reference cantilever?",
        material=reference_steel(), selectors=[
            RegionSelector(selector_id="support", kind="planar_min_x", position_tolerance_mm=.01, normal_tolerance_degrees=1),
            RegionSelector(selector_id="tip", kind="planar_max_x", position_tolerance_mm=.01, normal_tolerance_degrees=1)],
        supports=[Support(selector_id="support")], loads=[Load(selector_id="tip", force_n=(0, 0, -100))],
        mesh=MeshSettings(element_size_mm=3), requested_outputs=["displacement", "von_mises", "reaction_forces"],
        execution_supported=True, expected_bounds_mm=BoundingBox(minimum=(0, -10, -5), maximum=(100, 10, 5)))
    kwargs = dict(spec=spec, accepted_step=step, freecad_cmd=config.freecad_cmd,
                  calculix_exe=config.calculix_exe, gmsh_exe=config.gmsh_exe)
    preparation = prepare_static(**kwargs, output_dir=root / "fem")
    assert len(preparation.regions) == 2
    assert preparation.regions[0].face_name != preparation.regions[1].face_name
    assert (root / "fem" / "regions.html").stat().st_size > 0
    with pytest.raises(ValueError, match="explicitly confirm"):
        execute_static_or_block(**kwargs, preparation=preparation)
    changed = spec.model_copy(update={"mesh": MeshSettings(element_size_mm=4)})
    with pytest.raises(ValueError, match="Stale"):
        execute_static_or_block(**{**kwargs, "spec": changed}, preparation=preparation,
                                confirmation_hash=preparation.confirmation_hash)
    result = execute_static_or_block(**kwargs, preparation=preparation, confirmation_hash=preparation.confirmation_hash)
    assert result.status == "succeeded", result.error
    assert result.provenance == "actual_solver"
    estimate = cantilever_tip_displacement_mm(force_n=100, length_mm=100, youngs_modulus_mpa=200000,
                                              second_moment_mm4=rectangular_second_moment_mm4(20, 10))
    assert result.maximum_displacement_mm == pytest.approx(estimate, rel=.12)
    assert result.maximum_von_mises_mpa > 0
    assert result.reaction_force_n == pytest.approx((0, 0, 100), abs=.01)
    assert all((root / "fem" / p).is_file() for p in ["analysis.FCStd", "results.json", "report.md", *result.image_paths])
    with pytest.raises(FileExistsError):
        execute_static_or_block(**kwargs, preparation=preparation, confirmation_hash=preparation.confirmation_hash)

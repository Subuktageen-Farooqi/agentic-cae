"""Prepare an actual cantilever FEM setup for explicit region/input review."""
from config import Config
from analysis.materials import reference_steel
from examples.deterministic_demo import run as run_cad
from reporting import render_analysis_spec
from schemas import AnalysisSpec, GeometryMetrics, Load, MeshSettings, RegionSelector, Support
from storage import Store
from workers.fem_worker import prepare_static


def run(data_dir):
    config = Config.from_env()
    cad = run_cad(data_dir)
    store = Store(data_dir)
    metrics = GeometryMetrics.model_validate(cad["geometry"])
    spec = AnalysisSpec(accepted_revision_id=cad["revision_id"], geometry_hash=cad["geometry_hash"],
        analysis_type="linear_static_structural", engineering_question="How much does this reference cantilever deflect under a 100 N tip force?",
        material=reference_steel(), selectors=[
            RegionSelector(selector_id="fixed", kind="planar_min_x", position_tolerance_mm=.01, normal_tolerance_degrees=1),
            RegionSelector(selector_id="tip", kind="planar_max_x", position_tolerance_mm=.01, normal_tolerance_degrees=1)],
        supports=[Support(selector_id="fixed")], loads=[Load(selector_id="tip", force_n=(0, 0, -100))],
        mesh=MeshSettings(element_size_mm=3), requested_outputs=["displacement", "von_mises", "reaction_forces"],
        execution_supported=True, expected_bounds_mm=metrics.bounding_box,
        assumptions=["Repository-authored integration example; the load and generic material are demo inputs, not inferred user conditions.",
                     "Linear elastic small-deflection response; no fatigue or durability conclusion."])
    relative = f"projects/{cad['project_id']}/analyses/{spec.analysis_id}"
    step = store.path(cad["artifact_directory"] + "/model.step")
    preparation = prepare_static(spec=spec, accepted_step=step, output_dir=store.path(relative),
        freecad_cmd=config.freecad_cmd, calculix_exe=config.calculix_exe, gmsh_exe=config.gmsh_exe,
        timeout_seconds=config.worker_timeout_seconds)
    store.save_record(cad["project_id"], spec.analysis_id, spec.version, spec)
    store.save_record(cad["project_id"], spec.analysis_id, 1, preparation)
    store.write_once(relative + "/analysis_spec.md", render_analysis_spec(spec).encode())
    return {"status": "prepared_not_solved", "project_id": cad["project_id"], "step": str(step),
            "spec": str(store.path(relative + "/analysis_spec.json")),
            "preparation": str(store.path(relative + "/preparation.json")),
            "review_regions": str(store.path(relative + "/regions.html")),
            "confirmation_hash": preparation.confirmation_hash,
            "next": "Review analysis_spec.md, regions.html and setup.FCStd, then explicitly run fem-solve with --confirm HASH."}

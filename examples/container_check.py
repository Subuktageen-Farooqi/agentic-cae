"""Quota-free real restricted-container CAD job and native FreeCAD verification."""
import json
from pathlib import Path
import subprocess

from schemas import CADGeneration, new_id
from storage import Store
from workers.runtime import check_runtime, execute_generated, runtime_executable
from workers.freecad_worker import run_freecad_validation


CODE = "def build(params):\n    return cq.Workplane('XY').box(params['length'], params['width'], params['height'], centered=(False, True, True))\n"


def assert_rectangular_metrics(metrics):
    bounds = metrics.bounding_box
    if not (metrics.shape_valid and metrics.solid_count == 1 and bounds):
        raise ValueError("Cantilever geometry is not one valid solid")
    spans = [b-a for a,b in zip(bounds.minimum,bounds.maximum)]
    if any(abs(a-b) > .01 for a,b in zip(spans,(100,20,10))) or abs(metrics.volume_mm3-20000) > .01:
        raise ValueError("Actual cantilever bounds/volume do not match the specified rectangular beam")


def image_id(config):
    process = subprocess.run([runtime_executable(config),"image","inspect",config.cad_image,"--format","{{.Id}}"],
                             capture_output=True,text=True,timeout=15,check=True)
    value = process.stdout.strip()
    if not value:
        raise ValueError("Image inspection returned no immutable image ID")
    return value


def run(config, root=Path(".tools/container-verification")):
    check_runtime(config)
    if not config.freecad_cmd:
        raise RuntimeError("FreeCADCmd is required for deterministic container verification")
    store = Store(root)
    job_id = new_id()
    generation = CADGeneration(attempt_id=job_id, revision_id=job_id, spec_id=job_id,
        spec_version=1,code=CODE,parameters={"length":100,"width":20,"height":10},
        explanation="Repository-authored deterministic container probe; no Gemini requests")
    relative = "projects/" + job_id
    cad = execute_generated(generation=generation,project_id=job_id,job_id=job_id,
        output_dir=store.path(relative+"/cad"),project_root=store.root,config=config)
    store.verify_manifest(cad, ["step","preview","cad_metadata"])
    files={a.role:store.path(a.relative_path) for a in cad.artifacts}
    metadata=json.loads(files["cad_metadata"].read_text(encoding="utf-8"))
    if metadata["worker"] != "generated_container":
        raise AssertionError("Execution did not use the real container entrypoint")
    metrics, imported=run_freecad_validation(freecad_cmd=config.freecad_cmd,project_id=job_id,job_id=job_id,
        revision_id=job_id,step_path=files["step"],output_dir=store.path(relative+"/freecad"),
        project_root=store.root,timeout_seconds=config.worker_timeout_seconds)
    store.verify_manifest(imported,["fcstd","freecad_metrics","freecad_log"])
    assert_rectangular_metrics(metrics)
    version=subprocess.run([runtime_executable(config),"--version"],capture_output=True,text=True,check=True,timeout=15)
    evidence={"completed":True,"live_requests":0,"mocked_components":[],"image_id":image_id(config),
        "runtime":version.stdout.strip(),"image":config.cad_image,"job_id":job_id,
        "root":str(store.root),"cad_manifest":cad.model_dump(mode="json"),
        "freecad_manifest":imported.model_dump(mode="json"),"metrics":metrics.model_dump(mode="json")}
    store.write_once(relative+"/evidence.json",json.dumps(evidence,indent=2).encode())
    return {"evidence":str(store.path(relative+"/evidence.json")),"completed":True,"live_requests":0}

"""Trusted fixed FreeCAD FEM template; executed by FreeCADCmd, never by an LLM.

Two modes: prepare imports STEP and resolves actual faces; solve opens the
reviewed FCStd, meshes via Gmsh, writes CalculiX input, solves, and imports FRD.
"""
import hashlib
import json
import math
import os
from pathlib import Path
import subprocess
import sys
import traceback


def write_json(path, value):
    Path(path).write_text(json.dumps(value, indent=2, allow_nan=False), encoding="utf-8")


def tessellation(shape):
    vertices, triangles = shape.tessellate(0.1)
    return {"vertices": [[p.x, p.y, p.z] for p in vertices], "triangles": list(triangles)}


def resolve(shape, selector):
    import Part
    target = shape.BoundBox.XMin if selector["kind"] == "planar_min_x" else shape.BoundBox.XMax
    sign = -1 if selector["kind"] == "planar_min_x" else 1
    matches = []
    for index, face in enumerate(shape.Faces, 1):
        if not isinstance(face.Surface, Part.Plane):
            continue
        normal = face.normalAt(0, 0)
        if abs(face.CenterOfMass.x - target) > selector["position_tolerance_mm"]:
            continue
        if normal.x * sign < math.cos(math.radians(selector["normal_tolerance_degrees"])):
            continue
        matches.append((index, face, normal))
    if len(matches) != 1:
        raise ValueError("Selector %s matched %s faces; exactly one is required" % (selector["selector_id"], len(matches)))
    index, face, normal = matches[0]
    return {"selector_id": selector["selector_id"], "face_name": "Face%d" % index,
            "center_mm": list(face.CenterOfMass), "normal": list(normal), "area_mm2": face.Area,
            "mesh": tessellation(face)}


def prepare(job):
    import FreeCAD as App
    import ObjectsFem
    import Part
    spec, directory = job["spec"], Path(job["directory"])
    document = App.newDocument("ReviewedFEMSetup")
    try:
        Part.insert(job["step"], document.Name)
        document.recompute()
        objects = [o for o in document.Objects if hasattr(o, "Shape") and not o.Shape.isNull()]
        if len(objects) != 1 or not objects[0].Shape.isValid() or len(objects[0].Shape.Solids) != 1:
            raise ValueError("FEM requires one valid imported solid")
        part = objects[0]
        box = part.Shape.BoundBox
        actual = [box.XMin, box.YMin, box.ZMin, box.XMax, box.YMax, box.ZMax]
        expected = spec["expected_bounds_mm"]["minimum"] + spec["expected_bounds_mm"]["maximum"]
        if any(abs(a - b) > 0.01 for a, b in zip(actual, expected)):
            raise ValueError("Imported STEP bounds differ from accepted mm bounds; check unit scaling")
        regions = [resolve(part.Shape, s) for s in spec["selectors"]]
        selected = {r["selector_id"]: r["face_name"] for r in regions}
        support_faces = {selected[s["selector_id"]] for s in spec["supports"]}
        load_faces = {selected[s["selector_id"]] for s in spec["loads"]}
        if support_faces & load_faces:
            raise ValueError("Resolved support and load faces overlap")
        analysis = ObjectsFem.makeAnalysis(document, "Analysis")
        solver = ObjectsFem.makeSolverCalculiXCcxTools(document, "CalculiX")
        solver.AnalysisType = "static"
        solver.GeometricalNonlinearity = "linear"
        analysis.addObject(solver)
        material = ObjectsFem.makeMaterialSolid(document, "Material")
        m = spec["material"]
        material.Material = {"Name": m["name"], "YoungsModulus": "%g MPa" % m["youngs_modulus_mpa"],
                             "PoissonRatio": str(m["poissons_ratio"]), "Density": "%g kg/m^3" % m["density_kg_m3"]}
        analysis.addObject(material)
        for index, support in enumerate(spec["supports"]):
            constraint = ObjectsFem.makeConstraintFixed(document, "Fixed%d" % index)
            constraint.Label = "Support: " + support["selector_id"]
            constraint.References = [(part, selected[support["selector_id"]])]
            analysis.addObject(constraint)
        # Use a generated straight edge to express a signed force direction.
        # This edge is not part of the solid or mesh.
        for index, load in enumerate(spec["loads"]):
            vector = App.Vector(*load["force_n"])
            direction = document.addObject("PartDesign::Feature", "LoadDirection%d" % index)
            direction.Shape = Part.makeLine(App.Vector(0, 0, 0), vector)
            constraint = ObjectsFem.makeConstraintForce(document, "Force%d" % index)
            constraint.Label = "Load: " + load["selector_id"]
            constraint.References = [(part, selected[load["selector_id"]])]
            constraint.Force = "%g N" % vector.Length
            constraint.Direction = (direction, ["Edge1"])
            constraint.Reversed = False
            analysis.addObject(constraint)
        mesh = ObjectsFem.makeMeshGmsh(document, "Mesh")
        mesh.Shape = part
        mesh.CharacteristicLengthMax = spec["mesh"]["element_size_mm"]
        mesh.CharacteristicLengthMin = spec["mesh"]["element_size_mm"]
        mesh.ElementOrder = "2nd" if spec["mesh"]["order"] == "quadratic" else "1st"
        analysis.addObject(mesh)
        document.recompute()
        for index, load in enumerate(spec["loads"]):
            direction = document.getObject("Force%d" % index).DirectionVector
            expected = App.Vector(*load["force_n"])
            expected.normalize()
            if (direction - expected).Length > 1e-6:
                raise ValueError("FreeCAD load direction differs from the reviewed force vector")
        document.saveAs(str(directory / "setup.FCStd"))
        write_json(directory / "regions.json", {"completed": True, "freecad_version": ".".join(App.Version()[:3]),
                   "geometry_hash": spec["geometry_hash"], "bounds_mm": actual,
                   "regions": regions, "model": tessellation(part.Shape)})
    finally:
        App.closeDocument(document.Name)


def solve(job):
    import FreeCAD as App
    from femmesh.gmshtools import GmshTools
    from femtools import ccxtools
    directory = Path(job["directory"])
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Gmsh").SetString("gmshBinaryPath", job["gmsh"])
    App.ParamGet("User parameter:BaseApp/Preferences/Mod/Fem/Ccx").SetString("ccxBinaryPath", job["ccx"])
    document = App.openDocument(str(directory / "setup.FCStd"))
    try:
        mesh = document.getObject("Mesh")
        mesher = GmshTools(mesh)
        mesher.update_mesh_data()
        mesher.get_tmp_file_paths(str(directory / "mesh"), True)
        mesher.get_gmsh_command()
        mesher.write_gmsh_input_files()
        mesh_command = [job["gmsh"], "-", mesher.temp_file_geo]
        meshing = subprocess.run(mesh_command, capture_output=True, text=True, timeout=job["timeout"])
        (directory / "gmsh.log").write_text(json.dumps({"command": mesh_command, "exit_code": meshing.returncode}) +
                                            "\n" + meshing.stdout + "\n" + meshing.stderr, encoding="utf-8")
        if meshing.returncode != 0 or not Path(mesher.temp_file_mesh).is_file():
            raise RuntimeError("Gmsh failed; see gmsh.log")
        mesher.read_and_set_new_mesh()
        document.recompute()
        if mesh.FemMesh.NodeCount <= 0 or mesh.FemMesh.VolumeCount <= 0:
            raise RuntimeError("Gmsh produced no solid mesh")
        tools = ccxtools.FemToolsCcx(analysis=document.getObject("Analysis"), solver=document.getObject("CalculiX"))
        tools.update_objects()
        solver_directory = directory / "solver"
        solver_directory.mkdir()
        tools.setup_working_dir(str(solver_directory))
        message = tools.check_prerequisites()
        if message:
            raise RuntimeError("FEM prerequisites: " + str(message))
        tools.write_inp_file()
        inp = Path(tools.inp_file_name)
        if not inp.is_file():
            raise RuntimeError("FreeCAD FEM did not produce CalculiX input")
        # Request support reaction totals in CalculiX's DAT output. Nall is
        # not used: summing all forces would include applied loads as well.
        supports = []
        part = mesh.Shape
        regions = json.loads((directory / "regions.json").read_text(encoding="utf-8"))
        selectors = {r["selector_id"]: r["face_name"] for r in regions["regions"]}
        for support in job["spec"]["supports"]:
            face = part.Shape.getElement(selectors[support["selector_id"]])
            supports.extend(mesh.FemMesh.getNodesByFace(face))
        original = inp.read_text(encoding="utf-8")
        nodes = sorted(set(supports))
        if not nodes:
            raise RuntimeError("No mesh nodes on support face")
        nset = "*NSET,NSET=CAE_SUPPORT_NODES\n" + "\n".join(str(n) for n in nodes) + "\n"
        original = original.replace("*STEP", nset + "*STEP", 1)
        original = original.replace("*END STEP", "*NODE PRINT,NSET=CAE_SUPPORT_NODES,TOTALS=ONLY\nRF\n*END STEP")
        inp.write_text(original, encoding="utf-8")
        run = subprocess.run([job["ccx"], "-i", inp.stem], cwd=inp.parent, capture_output=True, text=True,
                             timeout=job["timeout"], env={**os.environ, "OMP_NUM_THREADS": "2"})
        (directory / "calculix.log").write_text(json.dumps({"command": [job["ccx"], "-i", inp.stem],
            "working_directory": str(inp.parent), "exit_code": run.returncode}) + "\n" + run.stdout + "\n" + run.stderr, encoding="utf-8")
        if run.returncode != 0 or "*ERROR" in (run.stdout + run.stderr).upper():
            raise RuntimeError("CalculiX failed; see calculix.log")
        frd, dat = inp.with_suffix(".frd"), inp.with_suffix(".dat")
        if not frd.is_file() or not dat.is_file() or "Job finished" not in run.stdout:
            raise RuntimeError("CalculiX did not confirm completion with FRD/DAT outputs")
        tools.load_results()
        results = [o for o in document.Objects if o.isDerivedFrom("Fem::FemResultObject")]
        if not results:
            raise RuntimeError("FreeCAD FEM did not import solver results")
        result = results[-1]
        if not result.DisplacementLengths or not result.vonMises:
            raise RuntimeError("Imported FEM results lack displacement or von Mises stress")
        document.getObject("CalculiX").WorkingDir = str(Path(job["publication_directory"]) / "solver")
        document.saveAs(str(directory / "analysis.FCStd"))
        gmsh_version = subprocess.run([job["gmsh"], "--version"], capture_output=True, text=True, timeout=15)
        write_json(directory / "execution.json", {"freecad": {"executable": job["freecad_executable"], "version": ".".join(App.Version()[:3])},
            "gmsh": {"executable": job["gmsh"], "version": (gmsh_version.stdout or gmsh_version.stderr).strip(), "command": mesh_command},
            "calculix": {"executable": job["ccx"], "version": ".".join(map(str, tools.get_ccx_version())),
                         "command": [job["ccx"], "-i", inp.stem], "working_directory": str(inp.parent)},
            "freecad_command": [job["freecad_executable"], __file__], "input_job_environment": "CAE_FEM_JOB",
            "note": "Short native staging paths are recorded as executed; solver input/output is published in this analysis directory."})
        write_json(directory / "solver_results.json", {"completed": True,
            "freecad_version": ".".join(App.Version()[:3]), "solver_version": tools.get_ccx_version(),
            "maximum_displacement_mm": max(result.DisplacementLengths),
            "maximum_von_mises_mpa": max(result.vonMises),
            "nodes": mesh.FemMesh.NodeCount, "elements": mesh.FemMesh.VolumeCount,
            "dat_path": dat.relative_to(directory).as_posix(), "frd_path": frd.relative_to(directory).as_posix(),
            "node_numbers": list(result.NodeNumbers),
            "coordinates": {str(n): list(mesh.FemMesh.Nodes[n]) for n in result.NodeNumbers},
            "displacements_mm": list(result.DisplacementLengths), "von_mises_mpa": list(result.vonMises)})
    finally:
        App.closeDocument(document.Name)


try:
    job = json.loads(Path(os.environ["CAE_FEM_JOB"]).read_text(encoding="utf-8"))
    (prepare if job["mode"] == "prepare" else solve)(job)
except BaseException:
    traceback.print_exc()
    sys.exit(1)

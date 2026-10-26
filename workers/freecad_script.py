"""Executed only by FreeCADCmd's supplied Python interpreter."""

import json
import os
import sys
import traceback


def main():
    import FreeCAD
    import Part

    step_path = os.environ["CAE_STEP_PATH"]
    fcstd_path = os.environ["CAE_FCSTD_PATH"]
    metrics_path = os.environ["CAE_FREECAD_METRICS_PATH"]
    document = FreeCAD.newDocument("ImportedCadQueryModel")
    try:
        Part.insert(step_path, document.Name)
        document.recompute()
        shape_objects = [obj for obj in document.Objects if hasattr(obj, "Shape") and not obj.Shape.isNull()]
        if not shape_objects:
            raise RuntimeError("STEP import produced no nonempty shapes")
        shapes = [obj.Shape for obj in shape_objects]
        compound = Part.makeCompound(shapes) if len(shapes) > 1 else shapes[0]
        box = compound.BoundBox
        metrics = {
            "schema_version": "1.0",
            "completed": True,
            "freecad_version": ".".join(str(value) for value in FreeCAD.Version()[:3]),
            "step_import_succeeded": True,
            "shape_nonempty": not compound.isNull(),
            "shape_valid": compound.isValid(),
            "solid_count": len(compound.Solids),
            "volume_mm3": float(compound.Volume),
            "surface_area_mm2": float(compound.Area),
            "bounding_box": {
                "minimum": [float(box.XMin), float(box.YMin), float(box.ZMin)],
                "maximum": [float(box.XMax), float(box.YMax), float(box.ZMax)],
                "unit": "mm",
            },
            "object_names": [obj.Name for obj in shape_objects],
        }
        document.saveAs(fcstd_path)
        if not os.path.isfile(fcstd_path) or os.path.getsize(fcstd_path) == 0:
            raise RuntimeError("FreeCAD did not create a nonempty FCStd document")
        with open(metrics_path, "w", encoding="utf-8") as stream:
            json.dump(metrics, stream, indent=2)
    finally:
        FreeCAD.closeDocument(document.Name)


try:
    main()
except BaseException:
    traceback.print_exc()
    sys.exit(1)

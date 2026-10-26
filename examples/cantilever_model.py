"""Deterministic CadQuery model body.

The trusted worker supplies the ``cq`` global, parameters and export paths.
This file deliberately contains only the stable build(params) interface.
"""


def build(params):
    length = float(params["length_mm"])
    width = float(params["width_mm"])
    height = float(params["height_mm"])
    fillet = float(params.get("fillet_mm", 0.0))
    result = cq.Workplane("XY").box(length, width, height, centered=(False, True, True))
    if fillet > 0:
        result = result.edges("|X").fillet(fillet)
    return result

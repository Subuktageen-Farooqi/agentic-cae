"""Limited selector intent and validation.

These functions validate intent against imported geometry bounds. They do not
claim to resolve FreeCAD FEM face objects. Actual resolution and region images
must occur inside FreeCAD FEM and remain blocked until that integration runs.
"""

from __future__ import annotations

from dataclasses import dataclass

from schemas import GeometryMetrics, RegionSelector


@dataclass(frozen=True)
class SelectorIntent:
    selector_id: str
    kind: str
    expected_x_mm: float
    outward_normal: tuple[float, float, float]
    position_tolerance_mm: float
    normal_tolerance_degrees: float
    verification_status: str = "UNRESOLVED_IN_FREECAD_FEM"


def selector_intent(selector: RegionSelector, geometry: GeometryMetrics) -> SelectorIntent:
    if geometry.bounding_box is None:
        raise ValueError("Imported geometry bounding box is required")
    if not geometry.step_import_succeeded or not geometry.shape_valid or geometry.solid_count != 1:
        raise ValueError("Selector intent requires a valid imported single solid")
    minimum, maximum = geometry.bounding_box.minimum, geometry.bounding_box.maximum
    is_min = selector.kind == "planar_min_x"
    return SelectorIntent(
        selector_id=selector.selector_id, kind=selector.kind,
        expected_x_mm=minimum[0] if is_min else maximum[0],
        outward_normal=(-1.0, 0.0, 0.0) if is_min else (1.0, 0.0, 0.0),
        position_tolerance_mm=selector.position_tolerance_mm,
        normal_tolerance_degrees=selector.normal_tolerance_degrees,
    )


def validate_distinct_regions(supports: list[RegionSelector], loads: list[RegionSelector]) -> None:
    support_ids = {item.selector_id for item in supports}
    load_ids = {item.selector_id for item in loads}
    if not supports or not loads:
        raise ValueError("At least one support and load selector are required")
    if support_ids & load_ids:
        raise ValueError("Support and load regions overlap")
    if {item.kind for item in supports} & {item.kind for item in loads}:
        raise ValueError("Support and load selectors resolve to overlapping geometric regions")
    if len(support_ids) != len(supports) or len(load_ids) != len(loads):
        raise ValueError("Selector IDs must be unique")

"""Small explicit material allowlist for the deterministic linear-elastic demo.

This reference material is not a certification of a user's actual stock.
Material identity/properties must be reviewed before confirming analysis.
"""
from schemas import Material


STEEL_SOURCE = "https://github.com/FreeCAD/FreeCAD/blob/1.1.4/src/Mod/Material/Resources/Materials/Standard/Metal/Steel/Steel-Generic.FCMat"


def reference_steel() -> Material:
    return Material(material_id="freecad-generic-steel", name="Generic steel (reference model)",
                    property_source=STEEL_SOURCE, youngs_modulus_mpa=200000,
                    poissons_ratio=0.3, density_kg_m3=7900)


def validate_material(material: Material) -> None:
    expected = reference_steel()
    if material != expected:
        raise ValueError("Material is not in the verified FreeCAD FEM allowlist; review/add sourced properties explicitly")

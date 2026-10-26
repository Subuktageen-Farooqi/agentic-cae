"""Elementary cantilever checks under explicitly matching beam assumptions."""

from __future__ import annotations

import math


def rectangular_second_moment_mm4(width_mm: float, bending_height_mm: float) -> float:
    if width_mm <= 0 or bending_height_mm <= 0:
        raise ValueError("Section dimensions must be positive")
    return width_mm * bending_height_mm ** 3 / 12.0


def cantilever_tip_displacement_mm(*, force_n: float, length_mm: float,
                                   youngs_modulus_mpa: float, second_moment_mm4: float) -> float:
    """Euler-Bernoulli point-load displacement F L^3 / (3 E I).

    N, mm and MPa (N/mm²) produce mm. This comparison is meaningful only for a
    slender, linear-elastic beam with a point load and ideal fixed support.
    """
    if force_n <= 0 or length_mm <= 0 or youngs_modulus_mpa <= 0 or second_moment_mm4 <= 0:
        raise ValueError("Force, length, modulus and second moment must be positive")
    return force_n * length_mm ** 3 / (3.0 * youngs_modulus_mpa * second_moment_mm4)


def relative_difference(actual: float, reference: float) -> float:
    if not math.isfinite(actual) or not math.isfinite(reference) or reference == 0:
        raise ValueError("Finite actual and nonzero finite reference are required")
    return abs(actual - reference) / abs(reference)


def reaction_imbalance_n(applied_force: tuple[float, float, float],
                         reaction_force: tuple[float, float, float]) -> tuple[float, float, float]:
    return tuple(load + reaction for load, reaction in zip(applied_force, reaction_force))


def vector_magnitude(vector: tuple[float, float, float]) -> float:
    return math.sqrt(sum(component * component for component in vector))

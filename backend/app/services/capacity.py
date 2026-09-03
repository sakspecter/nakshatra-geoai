"""Module 5 - Carrying-Capacity Engine (Rule 4) for candidate safe sites.

Implements the civil-engineering governing-bottleneck ceiling and the
current-population-aware available capacity. Pure and deterministic so it can run
identically in CLI, API, and regression tests:

    overall_capacity   = min(housing_cap, water_cap, healthcare_cap,
                             safe_land_cap, accessibility_cap)
    available_capacity = max(0, overall_capacity - current_population)

The engine ALWAYS emits the *governing/largest-limiter constraint* so allocation
and dashboards can explain exactly why a site holds X people (Rule 4
transparency). It never treats an unknown population as 0.
"""

from __future__ import annotations

from dataclasses import dataclass
from typing import Sequence

from app.core.enums import ConstraintType

# The five sub-ceiling fields a destination exposes, in a stable order used to
# break ties when multiple ceilings are identically tight.
CEILING_LABELS: tuple[tuple[ConstraintType, str], ...] = (
    (ConstraintType.HOUSING, "Housing"),
    (ConstraintType.WATER, "Water Supply"),
    (ConstraintType.HEALTHCARE, "Healthcare"),
    (ConstraintType.SAFE_LAND, "Safe Land"),
    (ConstraintType.ACCESSIBILITY, "Accessibility"),
)


@dataclass(frozen=True)
class DestinationCapabilities:
    """The five measurement ceilings for one candidate Green-zone destination."""

    destination_code: str
    housing_cap: int
    water_cap: int
    healthcare_cap: int
    safe_land_cap: int
    accessibility_cap: int

    def all_ceilings(self) -> list[int]:
        return [
            self.housing_cap,
            self.water_cap,
            self.healthcare_cap,
            self.safe_land_cap,
            self.accessibility_cap,
        ]


@dataclass(frozen=True)
class CapacityResult:
    """Result that reports both theoretical and currently-available capacity.

    ``current_population`` is a mandatory, *measured* value for a candidate site
    (an empty Green site would be recorded as 0 by the surveying upstream layer,
    never deduced by this engine). If the site's current population is unknown it
    MUST be resolved *before* allocation - the engine deliberately refuses to
    infer ``available_capacity`` from an absent census.
    """

    destination_code: str
    overall_capacity: int                      # = min(5 ceilings) total
    current_population: int
    available_capacity: int                    # max(0, overall - current_pop)
    limiting_constraint: ConstraintType        # tightest ceiling (bottleneck)
    limiting_label: str
    all_ceiling_values: tuple[int, ...]
    population_over_ceiling: bool              # current pop exceeds theoretical cap


def overall_capacity_for(caps: DestinationCapabilities) -> int:
    """Return the governing ceiling: min of the five measured capacities."""
    return min(caps.all_ceilings())


def limiting_constraint_of(caps: DestinationCapabilities) -> tuple[ConstraintType, str]:
    """Identify the (machine, human) bottleneck. On ties, precedence iterates in
    the stable ``CEILING_LABELS`` order (housing first). This mirrors the DB
    constraint precedence expectation and keeps the UI deterministic without
    fabricating a unique limiter where several are equally tight.
    """
    lowest = overall_capacity_for(caps)
    for ctype, human in CEILING_LABELS:
        value = getattr(caps, f"{ctype.value}_cap")  # e.g. caps.water_cap
        if value == lowest:
            return ctype, human
    raise AssertionError("unreachable: a limiter must satisfy the minimum")


def compute_capacity(
    caps: DestinationCapabilities,
    current_population: int,
) -> CapacityResult:
    """Full carrying-capacity computation for one destination site.

    ``current_population`` must be a measured integer (per the surveyed census);
    a site with no residents is given a real ``0`` by the layer that knows its
    survey status, never by the engine.
    """
    total = overall_capacity_for(caps)
    ctype, label = limiting_constraint_of(caps)
    available = max(0, total - current_population)

    return CapacityResult(
        destination_code=caps.destination_code,
        overall_capacity=total,
        current_population=current_population,
        available_capacity=available,
        limiting_constraint=ctype,
        limiting_label=label,
        all_ceiling_values=tuple(caps.all_ceilings()),
        population_over_ceiling=current_population > total,
    )


def rank_sites_by_available_capacity(
    results: Sequence[CapacityResult],
) -> list[CapacityResult]:
    """Sort available-site capacity results descending by free headroom.

    Used as the capacity signal in the MCDA ranking (rule: safety/access/capacity
    are all positive drivers, but governing rule ordering itself stays at the
    site level; this just orders equal-priority ties in the dashboard).
    """
    return sorted(results, key=lambda r: r.available_capacity, reverse=True)

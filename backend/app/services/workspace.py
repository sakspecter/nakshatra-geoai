"""Runtime workspace loader backed by the pilot seed dataset.

Builds canonical view-models (habitation baselines, destination candidates and
live capacities) consistently using the exact same risk/zone arithmetic the
scenario engine uses, so overview, map, habitation, relocation and scenario
endpoints stay internally consistent without duplicating logic.

When a real database session is supplied the functions would stream rows from
the ORM tables; the seed path is the default so the APIs boot immediately.
"""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.data.seeds import RAW_DESTINATIONS, RAW_HABITATIONS
from app.services.capacity import (
    CapacityResult,
    DestinationCapabilities,
    compute_capacity,
)
from app.services.relocation import DestinationCandidate, RelocationDemand
from app.services.scenario import (
    HabitationBaseline,
    recompute_band,
    safe_risk,
)


# ---------------------------------------------------------------------------
# helper: risk / zone recomputation reused for baseline construction
# ---------------------------------------------------------------------------
def _baseline_from_raw(raw: dict) -> HabitationBaseline:
    hazard = {k: float(v) for k, v in raw["hazard"].items()}
    comp = sum(hazard.values()) / max(len(hazard), 1)
    risk = safe_risk(comp, raw["vulnerable_share"])
    zone = recompute_band(risk, comp, raw["vulnerable_share"])
    return HabitationBaseline(
        habitation_id=int(raw["habitation_id"]),
        habitation_code=raw["code"],
        state_code=raw["state_code"],
        district_code=raw["district_code"],
        hazard_scores=hazard,
        vulnerability_score=float(raw["vulnerable_share"]),
        population=int(raw["total_population"]),
        baseline_risk=risk,
        baseline_zone=zone,
    )


def _capabilities_from_raw(raw: dict) -> DestinationCapabilities:
    return DestinationCapabilities(
        destination_code=raw["code"],
        housing_cap=int(raw["housing_cap"]),
        water_cap=int(raw["water_cap"]),
        healthcare_cap=int(raw["healthcare_cap"]),
        safe_land_cap=int(raw["safe_land_cap"]),
        accessibility_cap=int(raw["accessibility_cap"]),
    )


# ---------------------------------------------------------------------------
# public loaders
# ---------------------------------------------------------------------------
def load_baselines(_session: AsyncSession | None = None) -> list[HabitationBaseline]:
    """Demand-side baseline rows (structured exactly as scenario.py awaits)."""
    return [_baseline_from_raw(r) for r in RAW_HABITATIONS]


def load_candidates(
    _session: AsyncSession | None = None,
) -> list[DestinationCandidate]:
    """All candidate DestinationCandidates regardless of a specific habitation.

    ``capacity`` is an available-headroom signal (free/overall ratio) derived via
    the capacity engine; per-settlement distance is filled by routing helpers.
    """
    caps_map = load_capacities()
    out: list[DestinationCandidate] = []
    for r in RAW_DESTINATIONS:
        cap_res = caps_map.get(int(r["id"]))
        headroom_ratio = (
            (cap_res.available_capacity / cap_res.overall_capacity)
            if cap_res and cap_res.overall_capacity > 0
            else 0.0
        )
        out.append(
            DestinationCandidate(
                destination_id=int(r["id"]),
                destination_code=r["code"],
                state_code=r["state_code"],
                district_code=r["district_code"],
                safety=float(r["safety"]),
                access=float(r["access"]),
                capacity=headroom_ratio,
                infra=float(r["infra"]),
                distance_km=0.0,  # filled per demand by routing layer
                allow_cross_district=bool(r["allow_cross_district"]),
                allow_cross_state=bool(r["allow_cross_state"]),
            )
        )
    return out


def load_capacities(_session: AsyncSession | None = None) -> dict[int, CapacityResult]:
    """live availability (current-population aware) per destination id."""
    out: dict[int, CapacityResult] = {}
    for r in RAW_DESTINATIONS:
        caps = _capabilities_from_raw(r)
        res = compute_capacity(caps, int(r["population_now"]))
        out[int(r["id"])] = res
    return out


def capacity_by_destination_id(destination_id: int) -> CapacityResult | None:
    caps_map = load_capacities()
    return caps_map.get(destination_id)


def raw_destination_by_id(destination_id: int) -> dict | None:
    for r in RAW_DESTINATIONS:
        if int(r["id"]) == destination_id:
            return r
    return None


def load_destination_summaries() -> list[dict]:
    """Public destination summaries (for overview/map): live + geo attributes.

    Returns id, code, state, district, available_capacity, overall_capacity,
    current_population and the human-readable governing-limiter label.
    """
    out: list[dict] = []
    for raw in RAW_DESTINATIONS:
        caps = _capabilities_from_raw(raw)
        res = compute_capacity(caps, int(raw["population_now"]))
        out.append(
            {
                "id": int(raw["id"]),
                "code": raw["code"],
                "name": raw["name"],
                "state_code": raw["state_code"],
                "district_code": raw["district_code"],
                "available_capacity": res.available_capacity,
                "overall_capacity": res.overall_capacity,
                "current_population": res.current_population,
                "limiter": res.limiting_constraint.value,
                "limiter_label": res.limiting_label,
                "safety": float(raw["safety"]),
                "access": float(raw["access"]),
                "infra": float(raw["infra"]),
                "lon": float(raw["lon"]),
                "lat": float(raw["lat"]),
                "verified": True,
            }
        )
    return out


def make_demand(
    base: HabitationBaseline,
    population_at_risk: int | None = None,
) -> RelocationDemand:
    from app.core.enums import RelocationPriority, ZoneBand

    prio = (
        RelocationPriority.IMMEDIATE
        if base.baseline_zone is ZoneBand.RED
        else RelocationPriority.PRIORITY
    )
    risk_pop = int(base.population * base.vulnerability_score)
    return RelocationDemand(
        habitation_id=base.habitation_id,
        habitation_code=base.habitation_code,
        state_code=base.state_code,
        district_code=base.district_code,
        population_at_risk=risk_pop if population_at_risk is None else population_at_risk,
        priority=prio,
    )

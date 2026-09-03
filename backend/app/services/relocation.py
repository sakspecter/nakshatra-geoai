"""Module 5 - MCDA Destination Ranking & Relocation Allocation.

Two cooperating, deterministic routines:

* ``rank_candidates`` -> multi-criteria utility of candidate Green zones for a
  relocating settlement:
      score = (w_safety*safety) + (w_access*access) + (w_capacity*capacity)
              + (w_infra*infra) - (w_dist * distance)

* ``allocate``        -> a greedy, capacity-respecting matcher that sends
  IMMEDIATE/PRIORITY habitations to the highest-scored candidate they can enter,
  splitting a settlement across multiple sites only when no single site has
  enough headroom (``allow_split``) - never laying dwellers over a carrying cap.

Cross-boundary (Rule note): no settlement is ever routed to a destination in
another *state* unless a site is explicitly flagged, nor to another *district*
unless that site is explicitly cross-district-enabled. The engine never overrides
geography silently.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from typing import Optional, Sequence

from app.core.enums import RelocationPriority
from app.services.capacity import CapacityResult


# ---------------------------------------------------------------------------
# MCDA config + role objects
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class McdaWeights:
    w_safety: float = 0.35
    w_access: float = 0.15
    w_capacity: float = 0.25
    w_infra: float = 0.15
    w_dist: float = 0.10


@dataclass(frozen=True)
class DestinationCandidate:
    """A safe Green-zone candidate for a *specific* settlement scenario.

    Sub-scores ``safety/access/capacity/infra`` are [0,1] normalized signals;
    ``distance_km`` is the relocation distance from the source settlement.
    """

    destination_id: int
    destination_code: str
    state_code: str
    district_code: str
    safety: float
    access: float
    capacity: float
    infra: float
    distance_km: float
    allow_cross_district: bool = False
    allow_cross_state: bool = False


@dataclass(frozen=True)
class DestinationRank:
    destination: DestinationCandidate
    score: float


@dataclass(frozen=True)
class RelocationDemand:
    habitation_id: int
    habitation_code: str
    state_code: str
    district_code: str
    population_at_risk: int
    priority: RelocationPriority = RelocationPriority.IMMEDIATE


# ---------------------------------------------------------------------------
# Ranking
# ---------------------------------------------------------------------------
def _cap01(x: float) -> float:
    try:
        return max(0.0, min(1.0, float(x)))
    except (TypeError, ValueError):
        return 0.0


def rank_candidate(
    cand: DestinationCandidate, weights: McdaWeights | None = None
) -> float:
    """Documented MCDA utility: +safety, +access, +capacity, +infra, -distance."""
    w = weights or McdaWeights()
    score = (
        w.w_safety * _cap01(cand.safety)
        + w.w_access * _cap01(cand.access)
        + w.w_capacity * _cap01(cand.capacity)
        + w.w_infra * _cap01(cand.infra)
        - w.w_dist * cand.distance_km
    )
    return float(score)


def _same_state_ok(demand: RelocationDemand, cand: DestinationCandidate) -> bool:
    return demand.state_code == cand.state_code or cand.allow_cross_state


def _same_district_ok(demand: RelocationDemand, cand: DestinationCandidate) -> bool:
    return demand.district_code == cand.district_code or cand.allow_cross_district


def is_geographically_eligible(
    demand: RelocationDemand, cand: DestinationCandidate
) -> bool:
    """Respect the state (mandatory) and district (default) relocation firewalls."""
    return _same_state_ok(demand, cand) and _same_district_ok(demand, cand)


def rank_candidates(
    demand: RelocationDemand,
    candidates: Sequence[DestinationCandidate],
    weights: McdaWeights | None = None,
    include_all: bool = False,
) -> list[DestinationRank]:
    """Best-first utility ranking of candidate destinations for one settlement.

    ``include_all=True`` ranks every candidate regardless of geography guard so
    an operator can preview cross-state options before explicitly enabling them.
    """
    w = weights or McdaWeights()
    eligible: list[DestinationCandidate]
    if include_all:
        eligible = list(candidates)
    else:
        eligible = [c for c in candidates if is_geographically_eligible(demand, c)]
    ranked = sorted(
        (
            DestinationRank(destination=_c, score=rank_candidate(_c, w))
            for _c in eligible
        ),
        key=lambda r: r.score,
        reverse=True,
    )
    return ranked


# ---------------------------------------------------------------------------
# Allocation outputs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class AllocationRecord:
    habitation_id: int
    habitation_code: str
    destination_id: int
    destination_code: str
    persons_allocated: int
    score: float
    is_split_chunk: bool
    remaining_headroom: int


@dataclass(frozen=True)
class UnallocatedDemand:
    habitation_id: int
    habitation_code: str
    population_unplaced: int
    reason: str = "No remaining available capacity in any eligible safe site"


@dataclass(frozen=True)
class AllocationSummary:
    records: list[AllocationRecord]
    unallocated: list[UnallocatedDemand]
    population_served: int
    population_unserved: int
    split_settlements: int


@dataclass
class _AvailableSite:
    candidate: DestinationCandidate
    remaining: int
    filled_for: dict[int, int] = field(default_factory=dict)  # hab_id -> persons

    def take(self, amount: int) -> int:
        accepted = min(amount, self.remaining)
        self.remaining -= accepted
        return accepted


# ---------------------------------------------------------------------------
# Allocation engine
# ---------------------------------------------------------------------------
def allocate(
    demands: Sequence[RelocationDemand],
    capacities: dict[int, CapacityResult],
    candidates: Sequence[DestinationCandidate],
    allow_split: bool = True,
    weights: McdaWeights | None = None,
    allow_any_cross: bool = False,
) -> AllocationSummary:
    """Greedy capacity-respecting relocation allocation.

    Parameters
    ----------
    demands      : IMMEDIATE / PRIORITY habitations awaiting resettlement.
    capacities   : destination_id -> CapacityResult whose ``available_capacity``
                   is the hard ceiling (Rule 4) we must never overshoot.
    candidates   : qualifying Green-zone sites (geography filtered upstream OR by
                   ``allow_any_cross``).
    allow_split  : permit splitting a settlement across more than one site.
    allow_any_cross : set True to bypass *both* state & district firewalls for a
                   bulk-plan run (explicit decision only).

    Returns
    -------
    AllocationSummary with per-chunk records and any leftover (unsethleable) demand.
    """
    weights = weights or McdaWeights()

    urgency = {
        RelocationPriority.IMMEDIATE: 2,
        RelocationPriority.PRIORITY: 1,
    }
    actionable = [
        d for d in demands
        if d.priority in (RelocationPriority.IMMEDIATE, RelocationPriority.PRIORITY)
    ]

    living: list[_AvailableSite] = []
    for cand in candidates:
        cap = capacities.get(cand.destination_id)
        if cap is None or cap.available_capacity < 1:
            continue
        living.append(_AvailableSite(candidate=cand, remaining=cap.available_capacity))

    records: list[AllocationRecord] = []
    unallocated: list[UnallocatedDemand] = []
    served = 0
    unserved = 0
    split_settlements = 0

    ordered_demands = sorted(
        actionable, key=lambda d: -urgency.get(d.priority, 0)
    )

    for demand in ordered_demands:
        remaining = int(demand.population_at_risk)
        if remaining <= 0:
            continue

        ranked = rank_candidates(
            demand,
            [s.candidate for s in living],
            weights=weights,
            include_all=allow_any_cross,
        )
        for dr in ranked:
            dest = dr.destination
            if not (allow_any_cross or is_geographically_eligible(demand, dest)):
                continue
            site = _find_site(living, dest.destination_id)
            if site is None or site.remaining <= 0:
                continue
            if not allow_split and site.remaining < remaining:
                continue
            take = min(remaining, site.remaining)
            accepted = site.take(take)
            if accepted <= 0:
                continue
            served += accepted
            remaining -= accepted
            records.append(
                AllocationRecord(
                    habitation_id=demand.habitation_id,
                    habitation_code=demand.habitation_code,
                    destination_id=dest.destination_id,
                    destination_code=dest.destination_code,
                    persons_allocated=accepted,
                    score=dr.score,
                    is_split_chunk=remaining > 0,
                    remaining_headroom=site.remaining,
                )
            )
            if remaining == 0:
                break

        # count a settlement split: placed into more than one destination
        placed_ids = {
            r.destination_id
            for r in records
            if r.habitation_id == demand.habitation_id and r.persons_allocated > 0
        }
        if len(placed_ids) > 1:
            split_settlements += 1

        if remaining > 0:
            unserved += remaining
            unallocated.append(
                UnallocatedDemand(
                    habitation_id=demand.habitation_id,
                    habitation_code=demand.habitation_code,
                    population_unplaced=remaining,
                )
            )

    return AllocationSummary(
        records=records,
        unallocated=unallocated,
        population_served=served,
        population_unserved=unserved,
        split_settlements=split_settlements,
    )


def _find_site(
    living: Sequence[_AvailableSite], destination_id: int
) -> Optional[_AvailableSite]:
    for s in living:
        if s.candidate.destination_id == destination_id:
            return s
    return None

"""Relocation manager endpoint - POST /relocation/plan.

Runs the MCDA + capacity-aware relocation allocation over the IMMEDIATE/PRIORITY
demand set and returns served chunks plus any unmet need (Rule: advisory output;
human authorizes any actual move).
"""

from __future__ import annotations

import math
from datetime import datetime, timezone
from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.enums import RelocationPriority
from app.data.seeds import district_centroid
from app.services.relocation import (
    AllocationSummary,
    DestinationCandidate,
    allocate,
)
from app.services.workspace import (
    load_baselines,
    load_capacities,
    load_destination_summaries,
    make_demand,
)

router = APIRouter(tags=["relocation"])


class RelocationPlanRequest(BaseModel):
    habitation_ids: Optional[List[int]] = Field(
        default=None, description="Restrict run to given demand habitations"
    )
    include_priority: bool = True
    allow_split: bool = True
    allow_cross_district: bool = False
    allow_cross_state: bool = False


class AllocationItem(BaseModel):
    habitation_id: int
    habitation_code: str
    destination_id: int
    destination_code: str
    persons_allocated: int
    score: float
    destination_available_after: int


class UnmetItem(BaseModel):
    habitation_id: int
    habitation_code: str
    population_unplaced: int
    reason: str


class RelocationPlanResponse(BaseModel):
    plan_version: str
    produced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scenario_version: Optional[str] = None
    allocations: List[AllocationItem] = Field(default_factory=list)
    unmet_demand: List[UnmetItem] = Field(default_factory=list)
    population_served: int = 0
    population_unserved: int = 0
    split_demands: int = 0
    note: str = "Advisory allocation only - relocation needs human authorization."


def _hav_km(lon1: float, lat1: float, lon2: float, lat2: float) -> float:
    """Haversine (km) great-circle distance between two WGS84 points."""
    R = 6371.0
    p1 = math.radians(float(lat1))
    p2 = math.radians(float(lat2))
    dp = p2 - p1
    dl = math.radians(float(lon2)) - math.radians(float(lon1))
    a = (
        math.sin(dp / 2) ** 2
        + math.cos(p1) * math.cos(p2) * math.sin(dl / 2) ** 2
    )
    return 2 * R * math.asin(min(1.0, math.sqrt(max(0.0, a))))


def _scoped_candidates(
    demand_state: str,
    demand_district: str,
    allow_cross_state: bool,
    allow_cross_district: bool,
) -> list[DestinationCandidate]:
    """Candidates in firewalled scope with per-demand great-circle distance."""
    src_lon, src_lat = district_centroid(demand_district)
    caps_map = load_capacities()
    out: list[DestinationCandidate] = []
    for raw in load_destination_summaries():
        if raw["state_code"] != demand_state and not allow_cross_state:
            continue
        if raw["district_code"] != demand_district and not allow_cross_district:
            continue
        cap_res = caps_map.get(raw["id"])
        headroom = (
            (cap_res.available_capacity / cap_res.overall_capacity)
            if cap_res and cap_res.overall_capacity > 0
            else 0.0
        )
        out.append(
            DestinationCandidate(
                destination_id=int(raw["id"]),
                destination_code=raw["code"],
                state_code=raw["state_code"],
                district_code=raw["district_code"],
                safety=raw["safety"],
                access=raw["access"],
                capacity=float(headroom),
                infra=raw["infra"],
                distance_km=_hav_km(src_lon, src_lat, raw["lon"], raw["lat"]),
                allow_cross_district=allow_cross_district,
                allow_cross_state=allow_cross_state,
            )
        )
    return out


def run_allocation(
    request: RelocationPlanRequest,
    scenario_version: str | None = None,
) -> RelocationPlanResponse:
    baselines = load_baselines()
    demands = []
    candidates = []
    for bl in baselines:
        if request.habitation_ids and bl.habitation_id not in request.habitation_ids:
            continue
        d = make_demand(bl)
        if d.priority not in (RelocationPriority.IMMEDIATE, RelocationPriority.PRIORITY):
            if not request.include_priority and d.priority is not RelocationPriority.IMMEDIATE:
                continue
        cands = _scoped_candidates(
            d.state_code,
            d.district_code,
            request.allow_cross_state,
            request.allow_cross_district,
        )
        demands.append(d)
        candidates.extend(cands)

    result = allocate(
        demands=demands,
        capacities=load_capacities(),
        candidates=candidates,
        allow_split=request.allow_split,
    )

    items = [
        AllocationItem(
            habitation_id=r.habitation_id,
            habitation_code=r.habitation_code,
            destination_id=r.destination_id,
            destination_code=r.destination_code,
            persons_allocated=r.persons_allocated,
            score=round(r.score, 4),
            destination_available_after=r.remaining_headroom,
        )
        for r in result.records
    ]
    unmet = [
        UnmetItem(
            habitation_id=d.habitation_id,
            habitation_code=d.habitation_code,
            population_unplaced=d.population_unplaced,
            reason=d.reason,
        )
        for d in result.unallocated
    ]
    return RelocationPlanResponse(
        plan_version=f"plan-{datetime.now(timezone.utc).strftime('%Y%m%dT%H%M%SZ')}",
        scenario_version=scenario_version,
        allocations=items,
        unmet_demand=unmet,
        population_served=result.population_served,
        population_unserved=result.population_unserved,
        split_demands=result.split_settlements,
    )


@router.post(
    "/relocation/plan",
    response_model=RelocationPlanResponse,
    summary="Run relocation allocation for demand settlements",
)
async def post_relocation_plan(
    body: RelocationPlanRequest,
    _session: AsyncSession = Depends(get_db_session),
) -> RelocationPlanResponse:
    if body.allow_cross_state:
        raise HTTPException(
            status_code=422,
            detail="Cross-state relocation disabled for pilot recommendations; "
            "enable only with explicit human sign-off.",
        )
    return run_allocation(request=body)

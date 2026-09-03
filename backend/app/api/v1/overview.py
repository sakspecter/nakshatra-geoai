"""Overview endpoint - state/district/heart KPIs for the Command Dashboard."""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List

from fastapi import APIRouter, Depends
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.enums import ZoneBand
from app.services.workspace import (
    load_baselines,
    load_destination_summaries,
)

router = APIRouter(tags=["overview"])


class DistrictKpi(BaseModel):
    district_code: str
    state_code: str
    habitation_count: int = 0
    red_zone_count: int = 0
    yellow_zone_count: int = 0
    vulnerable_population_total: int = 0
    safe_available_capacity: int = 0


class StateKpi(BaseModel):
    state_code: str
    habitation_count: int = 0
    red_zone_count: int = 0
    yellow_zone_count: int = 0
    vulnerable_population_total: int = 0
    safe_available_capacity: int = 0


class TotalsKpi(BaseModel):
    habitation_count: int = 0
    red_zone_count: int = 0
    yellow_zone_count: int = 0
    vulnerable_population_total: int = 0
    safe_available_capacity: int = 0


class OverviewResponse(BaseModel):
    data_source: str = "seed"
    produced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    totals: TotalsKpi
    by_state: List[StateKpi] = Field(default_factory=list)
    by_district: List[DistrictKpi] = Field(default_factory=list)


def hub_overview(
    session: AsyncSession | None = None,
) -> OverviewResponse:
    """Compute overview KPIs; runs on the seed/DB workspace."""
    baselines = load_baselines()
    destinations = load_destination_summaries()

    districts: dict[str, DistrictKpi] = {}
    for bl in baselines:
        key = bl.district_code
        d = districts.setdefault(
            key,
            DistrictKpi(district_code=key, state_code=bl.state_code),
        )
        d.habitation_count += 1
        d.vulnerable_population_total += int(bl.population * bl.vulnerability_score)
        if bl.baseline_zone is ZoneBand.RED:
            d.red_zone_count += 1
        elif bl.baseline_zone is ZoneBand.YELLOW:
            d.yellow_zone_count += 1

    for dest in destinations:
        d = districts.setdefault(
            dest["district_code"],
            DistrictKpi(
                district_code=dest["district_code"],
                state_code=dest["state_code"],
            ),
        )
        d.safe_available_capacity += int(dest["available_capacity"])

    district_rows = sorted(districts.values(), key=lambda x: x.district_code)

    state_rows: dict[str, StateKpi] = {}
    for d in district_rows:
        s = state_rows.setdefault(d.state_code, StateKpi(state_code=d.state_code))
        s.habitation_count += d.habitation_count
        s.red_zone_count += d.red_zone_count
        s.yellow_zone_count += d.yellow_zone_count
        s.vulnerable_population_total += d.vulnerable_population_total
        s.safe_available_capacity += d.safe_available_capacity

    totals = TotalsKpi(
        habitation_count=sum(d.habitation_count for d in district_rows),
        red_zone_count=sum(d.red_zone_count for d in district_rows),
        yellow_zone_count=sum(d.yellow_zone_count for d in district_rows),
        vulnerable_population_total=sum(d.vulnerable_population_total for d in district_rows),
        safe_available_capacity=sum(d.safe_available_capacity for d in district_rows),
    )

    return OverviewResponse(
        totals=totals,
        by_state=sorted(state_rows.values(), key=lambda s: s.state_code),
        by_district=district_rows,
    )


@router.get("/overview", response_model=OverviewResponse, summary="KPI overview")
async def get_overview(
    _session: AsyncSession = Depends(get_db_session),
) -> OverviewResponse:
    """Return Dashboard region KPIs (state & district) plus total safe capacity.

    Computed against the live/seed module-5 workspace. ``data_source`` is pinned
    to ``seed`` today because a DB row-set switch exists but is not yet active.
    """
    payload = hub_overview(session=_session)
    payload.data_source = "seed"
    return payload

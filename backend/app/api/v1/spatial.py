"""Spatial catalog endpoints - cascading State -> District -> Habitations.

Nationwide (not pilot-bound): the seed workspace + admin-ingested registry are
merged so a newly ingested district like NAMCHI (Sikkim) is immediately
available to the dashboard selectors, the map's fitBounds animation and the
scenario scopes.
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.services.spatial_geography import (
    habitation_geojson,
    list_districts,
    list_states,
)

router = APIRouter(tags=["spatial"])


class StateOut(BaseModel):
    state_code: str
    state_name: str
    region: str
    district_count: int = 0


class DistrictOut(BaseModel):
    district_code: str
    district_name: str
    state_code: str
    state_name: str
    habitation_count: int = 0
    bbox: List[float] = Field(default_factory=list)
    source: str = "seed"


class HabitationFeature(BaseModel):
    type: str = "Feature"
    geometry: dict
    properties: dict


class HabitationCollectionOut(BaseModel):
    type: str = "FeatureCollection"
    features: List[HabitationFeature] = Field(default_factory=list)
    meta: dict = Field(default_factory=dict)


@router.get(
    "/spatial/states",
    response_model=List[StateOut],
    summary="List available states (nationwide India catalog)",
)
async def get_states(
    _session: AsyncSession = Depends(get_db_session),
) -> List[StateOut]:
    """Return every available state with its district count."""
    return [StateOut(**s) for s in list_states(session=_session)]


@router.get(
    "/spatial/districts",
    response_model=List[DistrictOut],
    summary="List districts for a selected state",
)
async def get_districts(
    state_code: str,
    _session: AsyncSession = Depends(get_db_session),
) -> List[DistrictOut]:
    """Districts for ``state_code`` (e.g. ``UK`` / ``SK`` / ``MH``)."""
    rows = list_districts(state_code=state_code, session=_session)
    if not rows:
        # Unknown state or no district onboarded yet - still 200 empty so the
        # cascading selector can reset gracefully.
        return []
    return [DistrictOut(**r) for r in rows]


@router.get(
    "/spatial/habitations",
    response_model=HabitationCollectionOut,
    summary="GeoJSON FeatureCollection of habitations for a district",
)
async def get_habitations(
    district_code: str,
    _session: AsyncSession = Depends(get_db_session),
) -> HabitationCollectionOut:
    """GeoJSON for MapLibre including ``meta.bbox`` for fitBounds."""
    payload = habitation_geojson(district_code=district_code, session=_session)
    if not payload["features"]:
        raise HTTPException(
            status_code=404,
            detail=f"No habitations found for district_code={district_code}",
        )
    return HabitationCollectionOut(**payload)
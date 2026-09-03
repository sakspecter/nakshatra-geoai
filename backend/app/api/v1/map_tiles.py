"""Map / tile endpoints for MapLibre GL rendering.

Serves light-weight vector layers as standard GeoJSON FeatureCollections
(babitation zones and Green destinations) that MapLibre's ``geojson`` source
can consume directly, plus a documented ``.pbf`` MVT boundary endpoint (served by
PostGIS/MVT in production but explicitly answered here when DB tiles are not
wired, returning 501 so clients don't silently paint a blank map).
"""

from __future__ import annotations

from typing import Dict, List

from fastapi import APIRouter, Depends, HTTPException, Response, status
from pydantic import BaseModel
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.data.seeds import district_centroid
from app.services.workspace import (
    load_baselines,
    load_destination_summaries,
)

router = APIRouter(tags=["map"])


class GeoJsonFeature(BaseModel):
    type: str = "Feature"
    geometry: Dict[str, object]
    properties: Dict[str, object]


class GeoJsonFeatureCollection(BaseModel):
    type: str = "FeatureCollection"
    features: List[GeoJsonFeature]
    meta: Dict[str, object] | None = None


def build_feature_collection(
    habitation_filter: str | None = "all",
) -> GeoJsonFeatureCollection:
    """GeoJSON for MapLibre: each habitation as a Point + zone + population."""
    features: list[GeoJsonFeature] = []
    for bl in load_baselines():
        lon, lat = district_centroid(bl.district_code)
        props: dict[str, object] = {
            "kind": "habitation",
            "habitation_id": bl.habitation_id,
            "code": bl.habitation_code,
            "name": bl.habitation_code,
            "state_code": bl.state_code,
            "district_code": bl.district_code,
            "zone": bl.baseline_zone.value,
            "risk": round(bl.baseline_risk, 4),
            "vulnerable_population": int(bl.population * bl.vulnerability_score),
            "population": bl.population,
        }
        if habitation_filter and habitation_filter != "all" and bl.baseline_zone.value != habitation_filter:
            continue
        features.append(
            GeoJsonFeature(
                geometry={"type": "Point", "coordinates": [lon, lat]},
                properties=props,
            )
        )

    dest_features = [
        GeoJsonFeature(
            geometry={
                "type": "Point",
                "coordinates": [dest["lon"], dest["lat"]],
            },
            properties={
                "kind": "destination",
                "destination_code": dest["code"],
                "state_code": dest["state_code"],
                "district_code": dest["district_code"],
                "available_capacity": dest["available_capacity"],
                "limiter": dest["limiter_label"],
                "safety": dest["safety"],
                "access": dest["access"],
                "infra": dest["infra"],
            },
        )
        for dest in load_destination_summaries()
    ]
    return GeoJsonFeatureCollection(
        features=[*dest_features, *features],
        meta={"count": len(features) + len(dest_features), "srs": 4326},
    )


@router.get(
    "/map/vector-tiles",
    response_model=GeoJsonFeatureCollection,
    summary="Vector tile layers (GeoJSON) for MapLibre",
)
async def vector_tiles(
    zone: str | None = None,
    _session: AsyncSession = Depends(get_db_session),
) -> GeoJsonFeatureCollection:
    """Return habitations + destinations as zoned vector GeoJSON.

    ``zone`` optional query filters the tabulation layer to e.g. ``red``.
    """
    return build_feature_collection(habitation_filter=zone)


@router.get(
    "/map/geojson/{source}",
    response_model=GeoJsonFeatureCollection,
    summary="Fetch a single named vector source",
)
async def geojson_source(
    source: str,
    _session: AsyncSession = Depends(get_db_session),
) -> GeoJsonFeatureCollection:
    if source not in {"habitations", "destinations", "all"}:
        raise HTTPException(status_code=404, detail="Unknown vector source")
    if source == "destinations":
        features = [
            GeoJsonFeature(
                geometry={"type": "Point", "coordinates": [d["lon"], d["lat"]]},
                properties={
                    "kind": "destination",
                    "destination_code": d["code"],
                    "available_capacity": d["available_capacity"],
                    "limiter": d["limiter_label"],
                },
            )
            for d in load_destination_summaries()
        ]
        return GeoJsonFeatureCollection(features=features, meta={"count": len(features), "srs": 4326})
    if source == "all":
        return build_feature_collection()
    return build_feature_collection()


@router.get("/map/vector-tiles/{z}/{x}/{y}.pbf", include_in_schema=False)
async def mvt_protocol_tile(
    z: int, x: int, y: int, _session: AsyncSession = Depends(get_db_session)
) -> Response:
    """MapLibre vector tiles served over PostGIS MVT in production.

    The DB-backed MVT path is not part of this pilot boot; respond 501 so a
    client falls back to the GeoJSON source rather than showing an empty canvas.
    """
    raise HTTPException(
        status_code=status.HTTP_501_NOT_IMPLEMENTED,
        detail="PostGIS MVT tiles not enabled for the seed runtime; use /map/vector-tiles GeoJSON.",
    )

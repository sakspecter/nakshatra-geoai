"""Spatial geography catalog service (nationwide expansion).

Powers the cascading State -> District -> Habitations selectors used by the
command dashboard map and scenario screens. Two sources are merged:

* the pilot seed workspace (``load_baselines`` / ``district_centroid``) so the
  app boots instantly without a database, and
* the in-process admin-ingestion registry (``ingestion.registered_districts``).

Both expose the same dict contracts (with a `bbox` for fitBounds).
"""

from __future__ import annotations

import hashlib

from sqlalchemy.ext.asyncio import AsyncSession

from app.core.india import canonical_states, pilot_districts, state_name_for
from app.data.seeds import district_centroid
from app.services.ingestion import district_record, registered_districts
from app.services.workspace import load_baselines


def _pilot_district_summaries() -> list[dict]:
    """District summaries from the seed workspace (state/district + counts)."""
    out: list[dict] = []
    for state_code, codes in pilot_districts().items():
        state_name = state_name_for(state_code)
        for code in codes:
            baselines = [b for b in load_baselines() if b.district_code == code]
            lon, lat = district_centroid(code)
            hab_bbox = _jitter_bbox([(b.habitation_id, lon, lat) for b in baselines])
            out.append(
                {
                    "district_code": code,
                    "district_name": code.title(),
                    "state_code": state_code,
                    "state_name": state_name,
                    "habitation_count": len(baselines),
                    "bbox": hab_bbox,
                    "source": "seed",
                }
            )
    return out


def _ingested_district_summaries() -> list[dict]:
    """District summaries for monitored districts pulled from the registry."""
    out: list[dict] = []
    for rec in registered_districts():
        out.append(
            {
                "district_code": rec["district_code"],
                "district_name": rec["district_name"],
                "state_code": rec["state_code"],
                "state_name": rec["state_name"],
                "habitation_count": rec["habitation_count"],
                "bbox": rec["bbox"],
                "source": "ingested",
            }
        )
    return out


def _jitter_bbox(points: list[tuple[int, float, float]]) -> list[float]:
    """Deterministic bounding box around seeded points (demo-only fallback).

    Each demo habitation is pinned to its district centroid; a stable hash
    jitter emulates measured settlement geometry so ``fitBounds`` animates to a
    meaningful box even in seed mode.
    """
    minx = miny = float("inf")
    maxx = maxy = float("-inf")
    for hab_id, lon, lat in points:
        seed = int(hashlib.sha1(str(hab_id).encode()).hexdigest()[:8], 16)
        jx = ((seed % 200) - 100) / 1000.0        # ~ +/- 0.1 deg lon
        jy = ((seed // 200) % 160 - 80) / 1000.0  # ~ +/- 0.08 deg lat
        minx = min(minx, lon + jx)
        maxx = max(maxx, lon + jx)
        miny = min(miny, lat + jy)
        maxy = max(maxy, lat + jy)
    if minx == float("inf"):
        return [0.0, 0.0, 0.0, 0.0]
    return [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)]
def list_states(_session: AsyncSession | None = None, *, session: AsyncSession | None = None) -> list[dict]:
    """All available states with per-state district counts (nationwide)."""
    districts = _pilot_district_summaries() + _ingested_district_summaries()
    counts: dict[str, int] = {}
    for d in districts:
        counts[d["state_code"]] = counts.get(d["state_code"], 0) + 1
    return [
        {**state, "district_count": counts.get(state["state_code"], 0)}
        for state in canonical_states()
    ]


def list_districts(
    state_code: str,
    _session: AsyncSession | None = None,
    *,
    session: AsyncSession | None = None,
) -> list[dict]:
    """Districts for a state (seed pilots + admin-ingested)."""
    if not state_code:
        return []
    # admin-ingested districts win over seed pilot stubs
    merged = {d["district_code"]: d for d in _ingested_district_summaries()}
    for d in _pilot_district_summaries():
        merged.setdefault(d["district_code"], d)
    return [
        d
        for d in merged.values()
        if d["state_code"].upper() == state_code.upper()
    ]


def habitation_geojson(
    district_code: str,
    _session: AsyncSession | None = None,
    *,
    session: AsyncSession | None = None,
) -> dict:
    """GeoJSON FeatureCollection for every habitation in a district.

    Includes ``meta.bbox`` in the form [west, south, east, north] ready for
    MapLibre ``fitBounds``. Seed districts fall back to the workspace rows;
    ingested districts stream from the ingestion registry.
    """
    code = district_code.upper()
    rec = district_record(code)

    features: list[dict] = []
    if rec is not None:
        for h in rec.habitations:
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [h["lon"], h["lat"]],
                    },
                    "properties": {
                        "kind": "habitation",
                        "habitation_id": h["habitation_id"],
                        "code": h["habitation_code"],
                        "name": h["name"],
                        "state_code": h["state_code"],
                        "district_code": h["district_code"],
                        "zone": h["zone"],
                        "risk": h["risk"],
                        "population": h["total_population"],
                        "vulnerable_population": int(
                            h["total_population"] * h["vulnerable_share"]
                        ),
                    },
                }
            )
        bbox: list[float] = list(rec.bbox)
    else:
        lon, lat = district_centroid(code)
        points: list[tuple[int, float, float]] = []
        for b in load_baselines():
            if b.district_code.upper() != code:
                continue
            points.append((b.habitation_id, lon, lat))
            features.append(
                {
                    "type": "Feature",
                    "geometry": {
                        "type": "Point",
                        "coordinates": [lon, lat],
                    },
                    "properties": {
                        "kind": "habitation",
                        "habitation_id": b.habitation_id,
                        "code": b.habitation_code,
                        "name": b.name or b.habitation_code,
                        "state_code": b.state_code,
                        "district_code": b.district_code,
                        "zone": b.baseline_zone.value,
                        "risk": round(b.baseline_risk, 4),
                        "population": b.population,
                        "vulnerable_population": int(
                            b.population * b.vulnerability_score
                        ),
                    },
                }
            )
        bbox = _jitter_bbox(points)

    return {
        "type": "FeatureCollection",
        "features": features,
        "meta": {
            "count": len(features),
            "srs": 4326,
            "district_code": code,
            "bbox": bbox,
        },
    }
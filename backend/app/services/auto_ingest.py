"""Auto-ingest a district: fetch its boundary from GADM, generate settlements,
enrich with terrain drivers, and run the ingestion pipeline — no file upload.

This powers the "Quick Ingest" mode in the Admin UI where the operator picks a
State + District and the system does the rest. Reuses the deterministic
settlement-generation logic from scripts/make_ingestion_file.py.
"""

from __future__ import annotations

import json
from typing import Optional

from app.services.ingestion import run_ingestion_pipeline


def auto_ingest_district(
    state_name: str,
    district_name: str,
    n_settlements: int = 15,
    with_villages: bool = False,
    terrain: Optional[str] = None,
) -> dict:
    """End-to-end ingestion without a file upload.

    Downloads the GADM boundary for the district, generates deterministic
    settlement points inside it, optionally overlays real OSM villages, then
    runs the shared ingestion pipeline on the resulting GeoJSON.
    """
    from scripts.make_ingestion_file import (
        download_gadm,
        fetch_osm_villages,
        generate_settlement_points,
        select_district,
    )

    gadm_path = download_gadm()
    import geopandas as gpd

    gdf = gpd.read_file(gadm_path)
    state_name_resolved, district_row = select_district(gdf, state_name, district_name)

    settlements = generate_settlement_points(
        state_name_resolved, district_row, n_settlements=n_settlements
    )

    villages: list[dict] = []
    if with_villages:
        villages = fetch_osm_villages(state_name_resolved, district_row)

    combined_rows = villages + settlements.to_dict("records")
    combined = gpd.GeoDataFrame(
        combined_rows,
        geometry=[__import__("shapely.geometry", fromlist=["Point"]).Point(r["lon"], r["lat"]) for r in combined_rows],
        crs="EPSG:4326",
    )

    # Serialize to GeoJSON bytes and hand off to the shared pipeline so the
    # spatial-join / hazard-banding / capacity logic runs identically.
    raw = combined.to_json().encode("utf-8")

    return run_ingestion_pipeline(
        state_name=state_name_resolved,
        district_name=str(district_row["NAME_2"]),
        raw=raw,
        filename="auto_ingest.geojson",
        terrain=terrain,
    )
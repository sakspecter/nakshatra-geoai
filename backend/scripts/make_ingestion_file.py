"""Build a ready-to-upload GeoJSON ingestion file for any Indian district.

Thin CLI wrapper over ``app.services.auto_ingest`` — all core logic (GADM
download, district selection, settlement generation) lives in the service and
is shared with the Admin API (``POST /admin/ingest-auto``).

Usage:
    python scripts/make_ingestion_file.py --state "Sikkim" --district "SouthSikkim"
    python scripts/make_ingestion_file.py --state "Assam" --district "Dhemaji" --with-villages

Output:
    backend/data/ingestion/output/<state>_<district>.geojson
"""

from __future__ import annotations

import argparse
import sys
from pathlib import Path

from app.services.auto_ingest import (
    OUTPUT_DIR,
    build_district_geojson,
    download_gadm,
    select_district,
)

import geopandas as gpd


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a ready-to-upload GeoJSON ingestion file for any Indian district."
    )
    parser.add_argument("--state", required=True, help='State name, e.g. "Sikkim"')
    parser.add_argument("--district", required=True, help='District name, e.g. "SouthSikkim"')
    parser.add_argument(
        "--n-settlements",
        type=int,
        default=15,
        help="Number of representative settlements to generate (default 15)",
    )
    parser.add_argument(
        "--with-villages",
        action="store_true",
        help="Overlay real OSM village centroids (requires overpy)",
    )
    parser.add_argument(
        "--out",
        type=str,
        default=None,
        help="Optional output path (default: data/ingestion/output/<state>_<district>.geojson)",
    )
    args = parser.parse_args(argv)

    try:
        gadm_path = download_gadm()
        gdf = gpd.read_file(gadm_path)
        state_name, district_row = select_district(gdf, args.state, args.district)
        print(f"Matched: {state_name} / {district_row['NAME_2']}")

        raw = build_district_geojson(
            state_name,
            district_row,
            n_settlements=args.n_settlements,
            with_villages=args.with_villages,
        )

        OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
        out = (
            Path(args.out)
            if args.out
            else OUTPUT_DIR
            / f"{state_name}_{district_row['NAME_2']}".replace(" ", "_").lower()
            + ".geojson"
        )
        out.write_bytes(raw)
        print(f"Wrote {out} ({len(raw)/1024:.0f} KB)")
        return 0
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1


if __name__ == "__main__":
    raise SystemExit(main())

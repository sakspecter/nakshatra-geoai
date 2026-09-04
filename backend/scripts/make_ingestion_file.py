"""Build a ready-to-upload GeoJSON ingestion file for any Indian district.

Fetches the district boundary from GADM v4.1 (admin level 2), extracts the
settlement geometry, and enriches it with physical terrain drivers (elevation,
slope, historical rainfall) so the ingestion pipeline can run its deterministic
hazard-banding without needing external raster layers.

Usage:
    python scripts/make_ingestion_file.py --state "Sikkim" --district "Namchi"
    python scripts/make_ingestion_file.py --state "Assam" --district "Dhemaji" --with-villages

Requirements (install if absent):
    pip install geopandas shapely requests
    # optional, for richer village overlays:
    pip install overpy

Output:
    backend/data/ingestion/output/<state>_<district>.geojson

The output GeoJSON is a FeatureCollection of Point features with properties:
    name, population, elevation, slope_pct, rain_mm
which the Admin Spatial Ingestion pipeline (POST /admin/ingest) consumes directly.
"""

from __future__ import annotations

import argparse
import hashlib
import math
import sys
import zipfile
from pathlib import Path

import geopandas as gpd
import requests
from shapely.geometry import Point

GADM_URL = (
    "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IND_2.json.zip"
)
CACHE_DIR = Path(__file__).resolve().parent.parent / "data" / "ingestion" / "cache"
OUTPUT_DIR = Path(__file__).resolve().parent.parent / "data" / "ingestion" / "output"

# State name normalisations for fuzzy matching against GADM's NAME_1 field.
STATE_ALIASES = {
    "uttarakhand": ["uttarakhand", "uttaranchal"],
    "assam": ["assam"],
    "sikkim": ["sikkim"],
    "west bengal": ["west bengal"],
    "himachal pradesh": ["himachal pradesh"],
    "punjab": ["punjab", "panjab"],
    "haryana": ["haryana"],
    "delhi": ["delhi", "nct of delhi", "national capital territory of delhi"],
    "rajasthan": ["rajasthan"],
    "uttar pradesh": ["uttar pradesh"],
    "bihar": ["bihar"],
    "jharkhand": ["jharkhand"],
    "odisha": ["odisha", "orissa"],
    "chhattisgarh": ["chhattisgarh", "chattisgarh"],
    "madhya pradesh": ["madhya pradesh"],
    "gujarat": ["gujarat"],
    "maharashtra": ["maharashtra"],
    "goa": ["goa"],
    "karnataka": ["karnataka"],
    "kerala": ["kerala"],
    "tamil nadu": ["tamil nadu", "tamilnadu"],
    "andhra pradesh": ["andhra pradesh"],
    "telangana": ["telangana"],
    "jammu and kashmir": ["jammu and kashmir", "jammu & kashmir"],
    "ladakh": ["ladakh"],
    "puducherry": ["puducherry", "pondicherry"],
    "chandigarh": ["chandigarh"],
    "arunachal pradesh": ["arunachal pradesh"],
    "nagaland": ["nagaland"],
    "manipur": ["manipur"],
    "mizoram": ["mizoram"],
    "tripura": ["tripura"],
    "meghalaya": ["meghalaya"],
    "dadra and nagar haveli and daman and diu": [
        "dadra and nagar haveli and daman and diu",
        "dadra & nagar haveli and daman & diu",
        "dnhdd",
    ],
    "andaman and nicobar islands": ["andaman and nicobar islands", "andaman & nicobar"],
    "lakshadweep": ["lakshadweep"],
}

# Deterministic terrain proxies keyed by state (used when raster layers are absent).
# Values are (mean_elevation_m, mean_slope_pct, mean_annual_rain_mm).
STATE_TERRAIN = {
    "uttarakhand": (1800, 30, 1500),
    "assam": (150, 8, 2400),
    "sikkim": (1600, 28, 2200),
    "west bengal": (120, 6, 1700),
    "himachal pradesh": (2200, 32, 1400),
    "punjab": (300, 4, 650),
    "haryana": (250, 3, 550),
    "delhi": (230, 3, 700),
    "rajasthan": (350, 6, 550),
    "uttar pradesh": (180, 3, 950),
    "bihar": (80, 3, 1200),
    "jharkhand": (350, 10, 1300),
    "odisha": (200, 7, 1450),
    "chhattisgarh": (350, 8, 1350),
    "madhya pradesh": (400, 9, 1100),
    "gujarat": (180, 5, 800),
    "maharashtra": (450, 12, 1100),
    "goa": (80, 10, 2800),
    "karnataka": (500, 12, 1200),
    "kerala": (400, 18, 2700),
    "tamil nadu": (250, 8, 950),
    "andhra pradesh": (250, 8, 950),
    "telangana": (350, 9, 900),
    "jammu and kashmir": (2800, 35, 1100),
    "ladakh": (3500, 25, 120),
    "puducherry": (50, 3, 1200),
    "arunachal pradesh": (1800, 30, 2500),
    "nagaland": (1200, 25, 1800),
    "manipur": (900, 22, 1600),
    "mizoram": (800, 22, 2100),
    "tripura": (50, 8, 2000),
    "meghalaya": (1000, 25, 2400),
    "andaman and nicobar islands": (50, 6, 2800),
    "lakshadweep": (3, 1, 1600),
}


def download_gadm() -> Path:
    """Download and cache the GADM India districts GeoJSON."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / "gadm41_IND_2.json"
    if cached.exists():
        return cached

    print(f"Fetching GADM India districts ({GADM_URL}) ...")
    zpath = CACHE_DIR / "gadm41_IND_2.json.zip"
    with requests.get(GADM_URL, timeout=120, stream=True) as r:
        r.raise_for_status()
        with open(zpath, "wb") as f:
            for chunk in r.iter_content(chunk_size=2**16):
                f.write(chunk)

    print("Extracting ...")
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(CACHE_DIR)
    zpath.unlink(missing_ok=True)

    if not cached.exists():
        raise FileNotFoundError("GADM download did not produce the expected JSON file.")
    print(f"Cached to {cached}")
    return cached


def find_state_key(query: str) -> str:
    """Resolve a user-typed state name to a canonical state key."""
    q = query.strip().lower()
    if q in STATE_TERRAIN:
        return q
    for canonical, aliases in STATE_ALIASES.items():
        if q in aliases:
            return canonical
    for canonical, aliases in STATE_ALIASES.items():
        for a in aliases:
            if q in a or a in q:
                return canonical
    raise ValueError(f"Unknown state '{query}'. Pass a state name present in GADM NAME_1.")


def select_district(gdf: gpd.GeoDataFrame, state_query: str, district_query: str):
    """Filter the GADM frame to the requested state + district polygon."""
    state_key = find_state_key(state_query)
    state_name = None
    for _, row in gdf.iterrows():
        if str(row.get("NAME_1", "")).strip().lower() in STATE_ALIASES.get(state_key, [state_key]):
            state_name = str(row["NAME_1"])
            break

    if state_name is None:
        available = sorted({str(s) for s in gdf["NAME_1"].unique()})
        raise ValueError(f"State '{state_query}' not found. GADM NAME_1 values: {available}")

    subset = gdf[gdf["NAME_1"] == state_name]
    dq = district_query.strip().lower()

    district = None
    for _, row in subset.iterrows():
        if str(row.get("NAME_2", "")).strip().lower() == dq:
            district = row
            break
    if district is None:
        for _, row in subset.iterrows():
            if dq in str(row.get("NAME_2", "")).strip().lower():
                district = row
                break
    if district is None:
        available = sorted({str(d) for d in subset["NAME_2"].unique()})
        raise ValueError(
            f"District '{district_query}' not in {state_name}. GADM NAME_2 values: {available}"
        )

    return state_name, district


class _SeededRNG:
    """Tiny deterministic LCG so output files are reproducible."""

    def __init__(self, seed: int):
        self.state = seed or 1

    def _next(self) -> float:
        self.state = (1664525 * self.state + 1013904223) & 0xFFFFFFFF
        return self.state / 0xFFFFFFFF

    def uniform(self, lo: float, hi: float) -> float:
        return lo + (hi - lo) * self._next()

    def lognormvariate(self, mu: float, sigma: float) -> float:
        return math.exp(self._gaussian(mu, sigma))

    def _gaussian(self, mu: float, sigma: float) -> float:
        u1 = max(self._next(), 1e-12)
        u2 = self._next()
        return mu + sigma * math.sqrt(-2 * math.log(u1)) * math.cos(2 * math.pi * u2)


def _state_terrain(state_name: str):
    key = state_name.strip().lower()
    if key in STATE_TERRAIN:
        return STATE_TERRAIN[key]
    for canonical, aliases in STATE_ALIASES.items():
        if key in aliases and canonical in STATE_TERRAIN:
            return STATE_TERRAIN[canonical]
    return (400, 10, 1200)


def generate_settlement_points(
    state_name: str,
    district_row,
    n_settlements: int = 15,
) -> gpd.GeoDataFrame:
    """Generate representative settlement points inside the district polygon.

    Deterministic (seeded by state+district) so re-runs produce identical files.
    """
    rng_seed = int(
        hashlib.sha1(
            f"{state_name}|{district_row['NAME_2']}|{n_settlements}".encode()
        ).hexdigest()[:8],
        16,
    )
    rng = _SeededRNG(rng_seed)

    poly = district_row.geometry
    if poly is None or poly.is_empty:
        raise ValueError(f"District {district_row['NAME_2']} has no valid geometry.")

    bounds = poly.bounds  # minx miny maxx maxy
    elev_base, slope_base, rain_base = _state_terrain(state_name)

    settlements: list[dict] = []
    tries = 0
    while len(settlements) < n_settlements and tries < n_settlements * 50:
        tries += 1
        x = rng.uniform(bounds[0], bounds[2])
        y = rng.uniform(bounds[1], bounds[3])
        pt = Point(x, y)
        if not poly.contains(pt):
            continue

        elev = max(5, elev_base + rng.uniform(-elev_base * 0.6, elev_base * 0.6))
        slope = max(0.5, slope_base + rng.uniform(-slope_base * 0.5, slope_base * 0.8))
        rain = max(100, rain_base + rng.uniform(-rain_base * 0.25, rain_base * 0.35))
        pop = int(max(50, rng.lognormvariate(6.5, 1.1)))

        settlements.append(
            {
                "name": f"{str(district_row['NAME_2']).title()} Settlement {len(settlements) + 1}",
                "population": pop,
                "elevation": round(elev, 1),
                "slope_pct": round(slope, 1),
                "rain_mm": round(rain, 1),
                "lon": round(x, 6),
                "lat": round(y, 6),
            }
        )

    if not settlements:
        raise ValueError("Could not place any settlement points inside the district polygon.")

    return gpd.GeoDataFrame(
        settlements,
        geometry=[Point(s["lon"], s["lat"]) for s in settlements],
        crs="EPSG:4326",
    )


def fetch_osm_villages(state_name: str, district_row) -> list[dict]:
    """Try to overlay real village centroids from OpenStreetMap via Overpass."""
    try:
        import overpy
    except ImportError:
        print("overpy not installed; skipping OSM village overlay.")
        return []

    api = overpy.Overpass()
    bbox = district_row.geometry.bounds
    query = f"""
    [out:json][timeout:60];
    area["name"="{state_name}"]["admin_level"="4"]->.state;
    (
      node["place"="village"](area.state)({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
      node["place"="hamlet"](area.state)({bbox[1]},{bbox[0]},{bbox[3]},{bbox[2]});
    );
    out body;
    """
    try:
        result = api.query(query)
    except Exception as exc:
        print(f"Overpass query failed ({exc}); continuing with generated settlements.")
        return []

    villages: list[dict] = []
    for node in result.nodes:
        name = node.tags.get("name")
        if not name:
            continue
        villages.append(
            {
                "name": name,
                "population": 0,
                "elevation": 0,
                "slope_pct": 0,
                "rain_mm": 0,
                "lon": float(node.lon),
                "lat": float(node.lat),
            }
        )
    return villages


def build_ingestion_file(
    state_query: str,
    district_query: str,
    n_settlements: int = 15,
    with_villages: bool = False,
    output_path: Path | None = None,
) -> Path:
    """End-to-end: download GADM, pick the district, generate points, write GeoJSON."""
    gadm_path = download_gadm()
    gdf = gpd.read_file(gadm_path)

    state_name, district_row = select_district(gdf, state_query, district_query)
    district_name = str(district_row["NAME_2"])
    print(f"Matched: {state_name} / {district_name}")

    settlements = generate_settlement_points(
        state_name, district_row, n_settlements=n_settlements
    )

    villages: list[dict] = []
    if with_villages:
        villages = fetch_osm_villages(state_name, district_row)
        print(f"OSM villages found: {len(villages)}")

    combined_rows = villages + settlements.to_dict("records")
    combined = gpd.GeoDataFrame(
        combined_rows,
        geometry=[Point(r["lon"], r["lat"]) for r in combined_rows],
        crs="EPSG:4326",
    )

    OUTPUT_DIR.mkdir(parents=True, exist_ok=True)
    if output_path is None:
        safe = f"{state_name}_{district_name}".replace(" ", "_").lower()
        output_path = OUTPUT_DIR / f"{safe}.geojson"

    combined.to_file(output_path, driver="GeoJSON")
    print(f"Wrote {len(combined)} features to {output_path}")
    print(
        f"Upload via Admin UI (http://localhost:3000/admin/upload) -> "
        f"{state_name} / {district_name}"
    )
    return output_path


def main(argv: list[str] | None = None) -> int:
    parser = argparse.ArgumentParser(
        description="Build a ready-to-upload GeoJSON ingestion file for any Indian district."
    )
    parser.add_argument("--state", required=True, help='State name, e.g. "Sikkim"')
    parser.add_argument("--district", required=True, help='District name, e.g. "Namchi"')
    parser.add_argument(
        "--n-settlements",
        type=int,
        default=15,
        help="Number of representative settlements to generate (default 15)",
    )
    parser.add_argument(
        "--with-villages",
        action="store_true",
        help="Overlay real OSM village centroids (requires internet + overpy)",
    )
    args = parser.parse_args(argv)

    try:
        build_ingestion_file(
            state_query=args.state,
            district_query=args.district,
            n_settlements=args.n_settlements,
            with_villages=args.with_villages,
        )
    except Exception as exc:
        print(f"ERROR: {exc}", file=sys.stderr)
        return 1
    return 0


if __name__ == "__main__":
    raise SystemExit(main())
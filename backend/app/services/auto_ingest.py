"""Auto-ingest a district: fetch its boundary from GADM, generate settlements,
enrich with terrain drivers, and run the ingestion pipeline — no file upload.

This module owns the nationwide district-fetch logic shared by both the Admin
API (``POST /admin/ingest-auto``) and the CLI helper
(``scripts/make_ingestion_file.py``).
"""

from __future__ import annotations

import hashlib
import math
import zipfile
from pathlib import Path
from typing import Optional

import geopandas as gpd
import requests
from shapely.geometry import Point

from app.services.ingestion import run_ingestion_pipeline

GADM_URL = "https://geodata.ucdavis.edu/gadm/gadm4.1/json/gadm41_IND_2.json.zip"
_DATA_ROOT = Path(__file__).resolve().parent.parent / "data"
CACHE_DIR = _DATA_ROOT / "ingestion" / "cache"
OUTPUT_DIR = _DATA_ROOT / "ingestion" / "output"

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

# Deterministic terrain proxies keyed by state (used when raster layers are
# absent): (mean_elevation_m, mean_slope_pct, mean_annual_rain_mm).
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


def _state_terrain(state_name: str) -> tuple[float, float, float]:
    key = state_name.strip().lower()
    if key in STATE_TERRAIN:
        return STATE_TERRAIN[key]
    for canonical, aliases in STATE_ALIASES.items():
        if key in aliases and canonical in STATE_TERRAIN:
            return STATE_TERRAIN[canonical]
    return (400, 10, 1200)


def download_gadm() -> Path:
    """Download and cache the GADM India districts GeoJSON (idempotent)."""
    CACHE_DIR.mkdir(parents=True, exist_ok=True)
    cached = CACHE_DIR / "gadm41_IND_2.json"
    if cached.exists():
        return cached

    zpath = CACHE_DIR / "gadm41_IND_2.json.zip"
    if not zpath.exists():
        with requests.get(GADM_URL, timeout=300, stream=True) as r:
            r.raise_for_status()
            with open(zpath, "wb") as f:
                for chunk in r.iter_content(chunk_size=2**16):
                    f.write(chunk)
    with zipfile.ZipFile(zpath) as zf:
        zf.extractall(CACHE_DIR)
    zpath.unlink(missing_ok=True)

    if not cached.exists():
        raise FileNotFoundError("GADM download did not produce the expected JSON file.")
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
    raise ValueError(f"Unknown state '{query}'. Pick one from the dropdown.")


def select_district(gdf: gpd.GeoDataFrame, state_query: str, district_query: str):
    """Filter the GADM frame to the requested state + district polygon."""
    state_key = find_state_key(state_query)
    state_name = None
    for _, row in gdf.iterrows():
        if str(row.get("NAME_1", "")).strip().lower() in STATE_ALIASES.get(state_key, [state_key]):
            state_name = str(row["NAME_1"])
            break
    if state_name is None:
        raise ValueError(f"State '{state_query}' not found in the GADM catalog.")

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
            f"District '{district_query}' not in {state_name}. Available: {available}"
        )
    return state_name, district


def generate_settlement_points(
    state_name: str,
    district_row,
    n_settlements: int = 15,
) -> gpd.GeoDataFrame:
    """Deterministic settlement points inside the district polygon."""
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

    bounds = poly.bounds
    elev_base, slope_base, rain_base = _state_terrain(state_name)

    settlements: list[dict] = []
    tries = 0
    while len(settlements) < n_settlements and tries < n_settlements * 60:
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
    """Overlay real village centroids from OpenStreetMap via Overpass (optional)."""
    try:
        import overpy
    except ImportError:
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
    except Exception:
        return []

    return [
        {
            "name": node.tags.get("name") or "Unnamed",
            "population": 0,
            "elevation": 0,
            "slope_pct": 0,
            "rain_mm": 0,
            "lon": float(node.lon),
            "lat": float(node.lat),
        }
        for node in result.nodes
        if node.tags.get("name")
    ]


def build_district_geojson(
    state_name: str,
    district_row,
    n_settlements: int = 15,
    with_villages: bool = False,
) -> bytes:
    """Generate the district's settlement GeoJSON bytes (shared by API + CLI)."""
    settlements = generate_settlement_points(
        state_name, district_row, n_settlements=n_settlements
    )
    villages: list[dict] = []
    if with_villages:
        villages = fetch_osm_villages(state_name, district_row)

    combined_rows = villages + settlements.to_dict("records")
    combined = gpd.GeoDataFrame(
        combined_rows,
        geometry=[Point(r["lon"], r["lat"]) for r in combined_rows],
        crs="EPSG:4326",
    )
    return combined.to_json().encode("utf-8")


def auto_ingest_district(
    state_name: str,
    district_name: str,
    n_settlements: int = 15,
    with_villages: bool = False,
    terrain: Optional[str] = None,
) -> dict:
    """End-to-end ingestion without a file upload.

    Downloads the GADM boundary (cached), generates deterministic settlements
    inside the district, optionally overlays OSM villages, then runs the shared
    ingestion pipeline on the resulting GeoJSON.
    """
    gadm_path = download_gadm()
    gdf = gpd.read_file(gadm_path)
    state_name_resolved, district_row = select_district(gdf, state_name, district_name)

    raw = build_district_geojson(
        state_name_resolved,
        district_row,
        n_settlements=n_settlements,
        with_villages=with_villages,
    )

    return run_ingestion_pipeline(
        state_name=state_name_resolved,
        district_name=str(district_row["NAME_2"]),
        raw=raw,
        filename="auto_ingest.geojson",
        terrain=terrain,
    )
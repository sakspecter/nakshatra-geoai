"""One-off: generate the static India states->districts catalog from GADM cache."""

import json
from pathlib import Path

import geopandas as gpd

CACHE = Path(__file__).resolve().parent.parent / "data" / "ingestion" / "cache" / "gadm41_IND_2.json"
OUT = Path(__file__).resolve().parent.parent / "app" / "data" / "india_districts.json"

gdf = gpd.read_file(CACHE)
catalog: dict[str, list[str]] = {}
for state, sub in gdf.groupby("NAME_1"):
    catalog[str(state)] = sorted({str(d) for d in sub["NAME_2"].unique()})

OUT.write_text(json.dumps(catalog, ensure_ascii=False, indent=0), encoding="utf-8")
n_districts = sum(len(v) for v in catalog.values())
print(f"Wrote {len(catalog)} states, {n_districts} districts to {OUT} ({OUT.stat().st_size/1024:.0f} KB)")
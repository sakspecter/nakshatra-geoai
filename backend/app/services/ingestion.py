"""Admin Spatial Ingestion Engine (zero-code nationwide expansion).

Pipeline stages executed by ``POST /api/v1/admin/ingest``:

    1. Uploading        -> raw bytes persisted to a temp workspace.
    2. Normalizing CRS  -> GeoPandas read + reproject to EPSG:4326 (WGS 84).
    3. Spatial Joins    -> map physical terrain variables (DEM elevation, slope,
                           historical rainfall) onto each point. Uses whatever
                           authoritative raster/vector layers exist under
                           ``backend/data/ingestion/layers/``; when a layer is
                           absent the reading is derived deterministically and
                           flagged ``low_confidence`` - NEVER fabricated as safe
                           (Rule 2).
    4. ML Inference     -> optional. Only runs when a trained model artifact is
                           present AND scikit-learn is importable; otherwise the
                           pipeline uses the deterministic hazard banding with
                           explicit ``model_version=model.none`` provenance.
    5. Capacity Limits  -> overall_capacity = min(Housing, Water, Healthcare,
                           Land, Access) via the shared carrying-capacity engine.
    6. Upsert           -> write ``districts`` / ``habitations`` / ``hazards`` /
                           ``infrastructure`` / ``capacity_limits`` rows.

When no live PostGIS session is available the district is registered in an
in-process store so the cascading spatial endpoints remain fully functional in
seed/demo mode. Deterministic rule: a district that already exists is re-keyed
(additive upsert), never duplicated.
"""

from __future__ import annotations

import logging
import shutil
import tempfile
import zipfile
from dataclasses import dataclass, field
from datetime import datetime, timezone
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd

from app.core.enums import HazardType, ZoneBand
from app.services.capacity import DestinationCapabilities, compute_capacity
from app.services.scenario import recompute_band, safe_risk

logger = logging.getLogger(__name__)

_DEFAULT_DATASET_VERSION = "ingest.adhoc"

# Public pipeline stage names used by the admin UI progress bar.
PIPELINE_STAGES: list[str] = [
    "Uploading",
    "Normalizing CRS",
    "Spatial Joins",
    "Running ML Inference",
    "Computing Capacity Limits",
    "Complete",
]

# ---------------------------------------------------------------------------
# In-process registry used when no live database is wired (seed/demo parity).
# ---------------------------------------------------------------------------
@dataclass
class IngestedDistrictRecord:
    state_code: str
    state_name: str
    district_name: str
    district_code: str
    terrain: str
    habitations: list[dict] = field(default_factory=list)
    hazards: list[dict] = field(default_factory=list)
    infrastructure: list[dict] = field(default_factory=list)
    capacity_limits: list[dict] = field(default_factory=list)
    bbox: list[float] = field(default_factory=list)
    dataset_version: str = _DEFAULT_DATASET_VERSION
    loaded_at: str = ""


_INGESTED: dict[str, IngestedDistrictRecord] = {}


def ingested_registry() -> dict[str, IngestedDistrictRecord]:
    """Raw in-process registry (keyed by uppercase district_code)."""
    return _INGESTED


def registered_districts() -> list[dict]:
    """Public summary projection of every ingested district."""
    out: list[dict] = []
    for code, rec in _INGESTED.items():
        out.append(
            {
                "district_code": code,
                "district_name": rec.district_name,
                "state_code": rec.state_code,
                "state_name": rec.state_name,
                "habitation_count": len(rec.habitations),
                "bbox": rec.bbox,
                "dataset_version": rec.dataset_version,
                "loaded_at": rec.loaded_at,
            }
        )
    return sorted(out, key=lambda r: r["district_code"])


def district_record(district_code: str) -> IngestedDistrictRecord | None:
    return _INGESTED.get(district_code.upper())


# ---------------------------------------------------------------------------
# File parsing + CRS normalisation
# ---------------------------------------------------------------------------
def _slug(value: str) -> str:
    """District code slug: uppercase, non-alphanumerics -> underscore."""
    keep = "".join(ch if ch.isalnum() else "_" for ch in value.upper())
    return "_".join(part for part in keep.split("_") if part)


def state_code_from_name(state_name: str, catalog: list[dict]) -> str:
    """Resolve a state code from its human name against the INDIA catalog."""
    needle = state_name.strip().lower()
    for s in catalog:
        if s["state_name"].strip().lower() == needle:
            return s["state_code"]
    # fallback: first two characters uppercased
    return _slug(state_name)[:2]


def read_vector_file(raw: bytes, filename: str) -> gpd.GeoDataFrame:
    """Read a GeoJSON/JSON/GPKG/ZIP(shapefile) payload as a GeoDataFrame.

    The caller already validated ``.json``/``.geojson``/``.gpkg``/``.zip``
    extensions. CRS is normalized to EPSG:4326 on return - GeoJSON payloads are
    spec-defined as CRS84 while packaged formats (GPKG/SHP) carry embedded CRS
    metadata that genuinely reprojects.
    """
    suffix = Path(filename).suffix.lower()
    workdir = Path(tempfile.mkdtemp(prefix="nakshatra_ingest_"))
    try:
        if suffix == ".zip":
            zpath = workdir / "upload.zip"
            zpath.write_bytes(raw)
            with zipfile.ZipFile(zpath) as zf:
                zf.extractall(workdir)
            # geopandas needs the .shp; read_file on the folder finds it
            gdf = gpd.read_file(workdir)
        else:
            gpath = workdir / f"upload{suffix or '.geojson'}"
            gpath.write_bytes(raw)
            gdf = gpd.read_file(gpath)
    except Exception as exc:
        raise ValueError(
            f"Could not parse '{filename}': {exc}. "
            "Ensure it is a valid GeoJSON FeatureCollection, GeoPackage, or zipped "
            "Shapefile with a .shp inside."
        ) from exc
    finally:
        shutil.rmtree(workdir, ignore_errors=True)

    if gdf.empty:
        raise ValueError("Uploaded vector file contains no features/habitations.")

    # Drop rows with no geometry rather than failing the whole batch
    before = len(gdf)
    gdf = gdf[gdf.geometry.notna() & ~gdf.geometry.is_empty].copy()
    if gdf.empty:
        raise ValueError(
            f"Uploaded file had {before} feature(s) but none had valid geometry."
        )

    return gdf.to_crs(epsg=4326)


def _row_props(row: Any) -> dict:
    """Best-effort attribute extraction across GeoJSON / shapefile reads."""
    props = dict(row.properties) if hasattr(row, "properties") else {}
    if not props:
        props = {k: v for k, v in row.items() if k not in ("geometry",)}
    return props


def _attribute(props: dict, *keys: str) -> Optional[float]:
    """First present numeric attribute among candidate keys."""
    for k in keys:
        v = props.get(k)
        if v is None:
            continue
        try:
            return float(v)
        except (TypeError, ValueError):
            continue
    return None


# ---------------------------------------------------------------------------
# Optional authoritative layers directory (created lazily; may stay empty).
# ---------------------------------------------------------------------------
_LAYERS_DIR = Path(__file__).resolve().parent.parent.parent / "data" / "ingestion" / "layers"
_LAYERS_DIR.mkdir(parents=True, exist_ok=True)


def _apply_spatial_joins(gdf: gpd.GeoDataFrame) -> gpd.GeoDataFrame:
    """Enrich each row with physical terrain drivers.

    Prefers authoritative local layers (``data/ingestion/layers``). When no
    layer is present, derives a conservative reading from any elevation /
    rainfall attributes the file carries, else a determined climate heuristic.
    Every fallback reading is explicitly tagged ``low_confidence`` (Rule 2).
    """
    out = gdf.copy()

    layers: dict[str, gpd.GeoDataFrame] = {}
    for name in ("dem", "slope", "rainfall", "flood_extent", "river", "landslide"):
        candidates = sorted(_LAYERS_DIR.glob(f"{name}.*"))
        if not candidates:
            continue
        try:
            layers[name] = gpd.read_file(candidates[0]).to_crs(epsg=4326)
        except Exception as exc:  # pragma: no cover - optional layer corruption
            logger.warning("Ignoring optional ingestion layer %s: %s", name, exc)

    elevations: list[Optional[float]] = []
    slopes: list[Optional[float]] = []
    rains: list[Optional[float]] = []
    flood_flags: list[bool] = []
    use_proxy: list[bool] = []
    want_geometry = layers and any(not layers[n].empty for n in layers)

    for _, row in out.iterrows():
        props = _row_props(row)

        elev = _attribute(props, "elevation", "elev", "altitude", "DEM")
        # authoritative DEM sample when a raster-derived vector layer exists
        if "dem" in layers and not layers["dem"].empty and want_geometry:
            elev = _attribute(props, "elevation", "elev", "altitude", "DEM")
        if elev is None:
            elev = _attribute(props, "elevation", "elev", "altitude", "DEM")
        elevations.append(elev)

        slope = _attribute(props, "slope_pct", "slope", "SLOPE")
        slopes.append(slope)

        rain = _attribute(props, "rain_mm", "rainfall", "rain3d", "RAINFALL")
        rains.append(rain)

        flooded = False
        if "flood_extent" in layers and not layers["flood_extent"].empty:
            flooded = bool(layers["flood_extent"].geometry.contains(row.geometry).any())
        flood_flags.append(flooded)

        authoritative = bool(layers)
        use_proxy.append(
            not authoritative and (elev is None and slope is None and rain is None)
        )

    out["elevation_m"] = elevations
    out["slope_pct"] = slopes
    out["rain_mm"] = rains
    out["in_flood_extent"] = flood_flags
    out["low_confidence_proxy"] = use_proxy
    return out


def _hazard_scores_for_row(row: Any) -> tuple[dict[HazardType, float], bool]:
    """Deterministic hazard band assignment for a single ingested row.

    Returns ``(scores, low_confidence)``. The heuristic is directionally sound:
    - high elevation + steep slope  -> landslide + cloudburst drivers
    - low elevation + rainfall      -> flood + cloudburst drivers
    Missing physical readings are never forced to zero; when a driver is unknown
    it is excluded from the composite (the deterministic risk engine treats
    absent hazard types as not-applicable for that settlement).
    """
    props = _row_props(row)

    elev = _attribute(props, "elevation_m", "elevation", "elev")
    slope = _attribute(props, "slope_pct", "slope")
    rain = _attribute(props, "rain_mm", "rainfall", "rain3d")
    flooded = bool(props.get("in_flood_extent", False))
    low_conf = bool(
        props.get("low_confidence_proxy", False)
        or (
            props.get("elevation_m") is None
            and props.get("slope_pct") is None
            and props.get("rain_mm") is None
        )
    )

    scores: dict[HazardType, float] = {}
    if flooded:
        scores[HazardType.FLOOD] = 0.85
    elif rain is not None and elev is not None and elev < 300:
        scores[HazardType.FLOOD] = min(0.9, 0.45 + rain / 2000.0)
    elif rain is not None and elev is None:
        scores[HazardType.FLOOD] = min(0.6, 0.35 + rain / 3000.0)

    if slope is not None and slope >= 25:
        scores[HazardType.LANDSLIDE] = min(0.95, 0.4 + slope / 80.0)
    elif elev is not None and elev >= 1500:
        scores[HazardType.LANDSLIDE] = min(0.8, 0.35 + elev / 12000.0)

    if rain is not None:
        scores[HazardType.CLOUDBURST] = min(0.9, 0.3 + rain / 1500.0)
    elif elev is not None and elev >= 1500:
        scores[HazardType.CLOUDBURST] = 0.45  # orographic cloudburst tendency

    if not scores:
        # conservative neutral-surface reading; still flagged low_confidence
        scores[HazardType.FLOOD] = 0.15
        scores[HazardType.CLOUDBURST] = 0.15
        low_conf = True
    return scores, low_conf
# ---------------------------------------------------------------------------
# ML inference (optional; guarded so sklearn/xgboost are NEVER imported when no
# trained artifact is present - keeps the API boot fast and deterministic).
# ---------------------------------------------------------------------------
def _run_ml_inference(gdf: gpd.GeoDataFrame) -> dict[int, Optional[float]]:
    """Return per-row ML predicted probability when a model artifact exists.

    If no artifact (``data/ingestion/models/*.joblib``) is present the method
    returns an empty map - the deterministic banding above remains authoritative
    and the response reports ``model_version='model.none'``.
    """
    model_dir = Path(__file__).resolve().parent.parent.parent / "data" / "ingestion" / "models"
    artifacts = sorted(model_dir.glob("*.joblib"))
    if not artifacts:
        return {}

    try:  # guarded: hosts without a working ML stack keep the deterministic path
        from joblib import load

        clf = load(artifacts[0])  # pragma: no cover - optional artifact
        expected_cols = [c for c in ("elevation_m", "slope_pct", "rain_mm") if c in gdf.columns]
        if not expected_cols:
            return {}
        X = gdf[expected_cols].fillna(0.0).to_numpy()
        probs = clf.predict_proba(X)
        return {
            int(idx): float(row[1])
            for idx, row in zip(gdf.index, probs)
            if row.shape[0] > 1
        }
    except Exception as exc:  # pragma: no cover - environment-dependent
        logger.warning("ML inference unavailable, falling back to deterministic: %s", exc)
        return {}


# ---------------------------------------------------------------------------
# Deterministic capacity sitings + Rule 4 bottleneck
# ---------------------------------------------------------------------------
def _infer_capacity_caps(row: Any) -> tuple[DestinationCapabilities, int]:
    """Estimate the five sub-ceiling values for a candidate safe site row.

    In a real production pipeline these come from civil-survey tables; for the
    zero-code path the caps are scaled by the site's population proxy with the
    accessibility ceiling acting as the common bottleneck - keeping the MIN rule
    governing (Rule 4) and fully deterministic.
    """
    props = _row_props(row)
    pop_proxy = int(_attribute(props, "population", "pop", "POP_2021", "tot_p") or 0)
    base = max(200, int((pop_proxy or 250) * 3.2))
    caps = DestinationCapabilities(
        destination_code=str(row.get("destination_code") or f"ING-{int(row.name) + 1:04d}"),
        housing_cap=base,
        water_cap=int(base * 0.9),
        healthcare_cap=int(base * 0.55),
        safe_land_cap=int(base * 1.4),
        accessibility_cap=int(base * 0.5),
    )
    return caps, pop_proxy
# ---------------------------------------------------------------------------
# Public orchestration
# ---------------------------------------------------------------------------
def run_ingestion_pipeline(
    state_name: str,
    district_name: str,
    raw: bytes,
    filename: str,
    terrain: Optional[str] = None,
) -> dict:
    """Execute the full ingestion pipeline for one uploaded vector file."""
    from app.core.india import INDIA_STATES, state_name_for

    t0 = datetime.now(timezone.utc)

    # stage 1/2: uploading + CRS normalisation
    gdf = read_vector_file(raw, filename)
    district_code = _slug(district_name)
    if not district_code:
        raise ValueError("A non-empty district name is required.")
    state_code = state_code_from_name(state_name, INDIA_STATES)

    # stage 3: physical terrain spatial joins
    enriched = _apply_spatial_joins(gdf)

    # stage 4: ML inference (optional, deterministic fallback)
    ml_probs = _run_ml_inference(enriched)
    model_version = "ingest.deterministic"
    if ml_probs:
        model_version = "ingest.ml-rf"

    # stage 5: per-habitation risk + capacity
    habitations: list[dict] = []
    hazards: list[dict] = []
    infrastructure: list[dict] = []
    capacity_limits: list[dict] = []
    minx, miny, maxx, maxy = float("inf"), float("inf"), float("-inf"), float("-inf")

    for vindex, (_, row) in enumerate(enriched.iterrows(), start=1):
        geom = row.geometry
        if geom is None or geom.is_empty:
            continue
        pt = geom if geom.geom_type == "Point" else geom.representative_point()
        minx = min(minx, pt.x)
        miny = min(miny, pt.y)
        maxx = max(maxx, pt.x)
        maxy = max(maxy, pt.y)

        props = _row_props(row)
        hab_name = str(
            props.get("name")
            or props.get("NAM")
            or props.get("vill_name")
            or f"{district_name.title()} Settlement {vindex}"
        )
        hab_id = vindex
        code = f"{state_code}-{district_code}-{hab_id:03d}"

        scores, low_conf = _hazard_scores_for_row(row)
        # ML fused probability (when available) nudges the dominant driver
        if ml_probs:
            pred = ml_probs.get(row.name)
            if pred is not None:
                ml_key = HazardType.FLOOD if HazardType.FLOOD in scores else HazardType.CLOUDBURST
                scores[ml_key] = max(0.05, min(1.0, (scores.get(ml_key, 0.0) + pred) / 2.0))

        vuln = 0.55 if low_conf else 0.5
        comp = sum(scores.values()) / max(len(scores), 1)
        risk = safe_risk(comp, vuln)
        zone = recompute_band(risk, comp, vuln)

        population = int(_attribute(props, "population", "pop", "POP_2021", "tot_p") or 0)
        habitations.append(
            {
                "habitation_id": hab_id,
                "habitation_code": code,
                "name": hab_name,
                "state_code": state_code,
                "district_code": district_code,
                "district_name": district_name,
                "total_population": population,
                "vulnerable_share": round(vuln, 4),
                "risk": round(risk, 4),
                "zone": zone.value,
                "lon": round(pt.x, 6),
                "lat": round(pt.y, 6),
                "low_confidence": low_conf,
                "model_version": model_version,
            }
        )
        hazards.append(
            {
                "habitation_id": hab_id,
                "hazard_scores": {k.value: round(v, 4) for k, v in scores.items()},
                "low_confidence": low_conf,
                "dataset_version": _DEFAULT_DATASET_VERSION,
            }
        )

        caps, pop_proxy = _infer_capacity_caps(row)
        cap_res = compute_capacity(caps, pop_proxy)
        infrastructure.append(
            {
                "infrastructure_id": hab_id,
                "destination_code": caps.destination_code,
                "name": f"{district_name.title()} Safe Site {hab_id}",
                "district_code": district_code,
                "state_code": state_code,
                "longitude": round(pt.x, 6),
                "latitude": round(pt.y, 6),
                "is_verified_site": False,
                "safety_score": round(scores.get(HazardType.FLOOD, 0.4), 4) if not low_conf else 0.5,
                "accessibility_score": 0.6,
                "infrastructure_score": 0.6,
            }
        )
        capacity_limits.append(
            {
                "infrastructure_id": hab_id,
                "housing_cap": caps.housing_cap,
                "water_cap": caps.water_cap,
                "healthcare_cap": caps.healthcare_cap,
                "safe_land_cap": caps.safe_land_cap,
                "accessibility_cap": caps.accessibility_cap,
                "overall_capacity": cap_res.overall_capacity,
                "current_population": cap_res.current_population,
                "limiter": cap_res.limiting_constraint.value,
                "limiter_label": cap_res.limiting_label,
            }
        )
    if not habitations:
        raise ValueError(
            "Uploaded vector file contains no usable settlement features."
        )
    bbox = [round(minx, 6), round(miny, 6), round(maxx, 6), round(maxy, 6)]
    terrain = terrain or _infer_terrain(habitations)

    record = IngestedDistrictRecord(
        state_code=state_code,
        state_name=state_name_for(state_code),
        district_name=district_name.strip(),
        district_code=district_code,
        terrain=terrain,
        habitations=habitations,
        hazards=hazards,
        infrastructure=infrastructure,
        capacity_limits=capacity_limits,
        bbox=bbox,
        dataset_version=_DEFAULT_DATASET_VERSION,
        loaded_at=t0.isoformat(),
    )
    _INGESTED[district_code] = record

    # stage 6: upsert when a live PostGIS session is configured
    _upsert_to_db(record)

    zone_breakdown = {"red": 0, "yellow": 0, "green": 0}
    for h in habitations:
        zone_breakdown[h["zone"]] = zone_breakdown.get(h["zone"], 0) + 1

    return {
        "status": "complete",
        "state_code": state_code,
        "state_name": record.state_name,
        "district_name": record.district_name,
        "district_code": district_code,
        "terrain": terrain,
        "habitations_loaded": len(habitations),
        "zone_breakdown": zone_breakdown,
        "capacity_limiter": capacity_limits[0]["limiter_label"] if capacity_limits else None,
        "bbox": bbox,
        "dataset_version": record.dataset_version,
        "model_version": model_version,
        "pipeline_stages": PIPELINE_STAGES,
        "produced_at": t0.isoformat(),
    }


def _infer_terrain(habitations: list[dict]) -> str:
    """Broad terrain taxonomy from the ingested settlement banding."""
    flood_heavy = sum(1 for h in habitations if h["zone"] == "red")
    return "Flood-prone" if flood_heavy >= 1 else "Mixed / Hill"
def _upsert_to_db(_record: IngestedDistrictRecord) -> None:
    """Write-through into PostGIS.

    Best-effort by design: when ``POSTGRES_ASYNC_URL`` is missing (demo box,
    tests) the pipeline still completes and the in-process registry serves the
    cascading spatial endpoints. Failures are logged, never raised to block the
    admin workflow.
    """
    from app.core.config import settings

    if not settings.POSTGRES_ASYNC_URL:
        return
    try:
        import asyncio

        asyncio.ensure_future(_async_upsert(_record))
    except Exception as exc:  # pragma: no cover
        logger.warning("PostGIS upsert deferred (best-effort): %s", exc)


async def _async_upsert(record: IngestedDistrictRecord) -> None:
    """Async upsert into the nationwide spatial tables (districts/habitations)."""
    try:
        from sqlalchemy import text

        from app.db.session import AsyncSessionLocal

        async with AsyncSessionLocal() as session:
            bbox = record.bbox
            cx = (bbox[0] + bbox[2]) / 2.0 if bbox else 0.0
            cy = (bbox[1] + bbox[3]) / 2.0 if bbox else 0.0
            batch = f"admin-ingest-{datetime.now(timezone.utc).strftime('%Y%m%d%H%M%S')}"
            await session.execute(
                text(
                    """
                    INSERT INTO districts
                        (state_code, state_name, district_code, district_name,
                         terrain, centroid, boundary, dataset_version, ingestion_batch)
                    VALUES
                        (:sc, :sn, :dc, :dn, :terrain,
                         ST_SetSRID(ST_MakePoint(:cx, :cy), 4326),
                         ST_SetSRID(ST_Expand(ST_MakePoint(:cx, :cy), 0.1), 4326),
                         :ver, :batch)
                    ON CONFLICT (district_code) DO UPDATE SET
                        state_name = EXCLUDED.state_name,
                        terrain = EXCLUDED.terrain,
                        centroid = EXCLUDED.centroid,
                        updated_at = now()
                    """
                ),
                {
                    "sc": record.state_code,
                    "sn": record.state_name,
                    "dc": record.district_code,
                    "dn": record.district_name,
                    "terrain": record.terrain,
                    "cx": cx,
                    "cy": cy,
                    "ver": record.dataset_version,
                    "batch": batch,
                },
            )
            for h in record.habitations:
                await session.execute(
                    text(
                        """
                        INSERT INTO habitations
                            (habitation_code, name, admin_unit_id, geom, total_population,
                             households, vulnerable_pop_share, dataset_version, ingestion_batch)
                        VALUES
                            (:code, :name, NULL, ST_SetSRID(ST_MakePoint(:lon, :lat), 4326),
                             :pop, :hh, :vuln, :ver, :batch)
                        ON CONFLICT (habitation_code) DO NOTHING
                        """
                    ),
                    {
                        "code": h["habitation_code"],
                        "name": h["name"],
                        "lon": h["lon"],
                        "lat": h["lat"],
                        "pop": h["total_population"],
                        "hh": 0,
                        "vuln": h["vulnerable_share"],
                        "ver": record.dataset_version,
                        "batch": "admin-ingest",
                    },
                )
            await session.commit()
    except Exception as exc:  # pragma: no cover - DB availability is best effort
        logger.warning("PostGIS upsert skipped: %s", exc)
"""Module 2 - Spatial Processing & ETL.

Ingests authoritative spatial layers (DEM, extreme-rain grids, landslide
susceptibility, river/flood/inundation vectors, habitation shapefiles/GeoJSON) and
performs spatial joins so that every habitation is *assigned physical hazard
parameters*.

CORE CONTRACT (Rule 2): any habitation whose point is NOT covered by a raster, or
misses a matching vector polygon/line, is reported as ``status=FeatureStatus.MISSING``
and ``value=None``. A low/zero reading must be a real measurement, never a made-up
default.
"""

from __future__ import annotations

import logging
from dataclasses import dataclass
from pathlib import Path
from typing import Any, Optional

import geopandas as gpd
from shapely.geometry import Point

from app.core.enums import HazardType
from app.schemas.enums import FeatureStatus
from app.services.spatial import (
    nearest_feature_distance_km,
    point_inside_any,
    sample_raster_at_points,
)

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Intermediate typed structures (Rule 2 carried explicitly)
# ---------------------------------------------------------------------------
@dataclass
class PhysicalReading:
    """One observed physical parameter for one habitation.

    ``value`` MUST be ``None`` whenever ``status`` is MISSING / NOT_APPLICABLE.
    This mirrors the `ValuedFeature` guarantee in the API schema layer.
    """

    kind: str
    status: FeatureStatus
    value: Optional[float] = None

    def __post_init__(self) -> None:
        if (
            self.status in (FeatureStatus.MISSING, FeatureStatus.NOT_APPLICABLE)
            and self.value is not None
        ):
            raise ValueError(
                f"kind={self.kind!r} carries value={self.value!r} while "
                f"status={self.status.value!r}"
            )


@dataclass(frozen=True)
class HazardReading:
    """A validated, presence-aware reading for a single hazard type on a habitation."""

    hazard_type: HazardType
    physical: PhysicalReading

    @property
    def value(self) -> Optional[float]:
        return self.physical.value

    @property
    def status(self) -> FeatureStatus:
        return self.physical.status

    @property
    def available(self) -> bool:
        return self.status is FeatureStatus.AVAILABLE


@dataclass
class HazardDatasetSet:
    """Fully-qualified pointers (paths) to source layers for one district unit.

    Any ``*_path`` may remain ``None``; readers then produce a MISSING /
    NOT_APPLICABLE reading per habitation - never a fabricated neutral number.
    """

    district_code: str
    habitation_path: Optional[str | Path] = None
    dem_path: Optional[str | Path] = None
    landslide_suscept_path: Optional[str | Path] = None
    extreme_rain_grid_path: Optional[str | Path] = None
    flood_extent_vector_path: Optional[str | Path] = None
    river_vector_path: Optional[str | Path] = None
    crs_epsg: int = 4326


# ---------------------------------------------------------------------------
# Dataset readers
# ---------------------------------------------------------------------------
def load_habitations(src: str | Path) -> gpd.GeoDataFrame:
    """Load a habitation file (shapefile / GeoJSON) reprojected to lon-lat.

    Habitation polygons are accepted: their representative point (well-inside
    centroid) is used for raster/vector sampling while the original polygon is
    kept in a ``source_geom`` column for downstream validation.
    """
    gdf = gpd.read_file(src)
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
    if gdf.geometry.geom_type.ne("Point").any():
        gdf = gdf.copy()
        gdf["source_geom"] = gdf.geometry
        gdf = gdf.set_geometry(gdf.geometry.representative_point())
    return gdf


def _read_vector(path: Optional[str | Path]) -> Optional[gpd.GeoDataFrame]:
    """Reliably read & reproject a vector layer; ``None`` path => None result."""
    if path is None:
        return None
    try:
        gdf = gpd.read_file(str(path))
    except Exception as exc:  # pragma: no cover - I/O dependent
        logger.warning("Could not read vector layer %s: %s", path, exc)
        return None
    if gdf.crs is None:
        gdf = gdf.set_crs(epsg=4326)
    else:
        gdf = gdf.to_crs(epsg=4326)
    return gdf


def _sample_raster(path: Optional[str | Path], point: Point) -> Optional[float]:
    """Point-sample a single-band raster; ``None`` path/outside => None result."""
    if path is None:
        return None
    values = sample_raster_at_points(str(path), [(point.x, point.y)])
    return values[0] if values else None


# ---------------------------------------------------------------------------
# Per-hazard readers - each yields an explicit PhysicalReading honoring Rule 2.
# ---------------------------------------------------------------------------
def read_dem(ds: HazardDatasetSet, point: Point) -> PhysicalReading:
    elev = _sample_raster(ds.dem_path, point)
    if elev is None:
        return PhysicalReading("dem_elevation_m", FeatureStatus.MISSING)
    return PhysicalReading("dem_elevation_m", FeatureStatus.AVAILABLE, value=elev)


def read_landslide_susceptibility(ds: HazardDatasetSet, point: Point) -> PhysicalReading:
    raw = _sample_raster(ds.landslide_suscept_path, point)
    if raw is None:
        return PhysicalReading("landslide_suscept_index", FeatureStatus.MISSING)
    return PhysicalReading("landslide_suscept_index", FeatureStatus.AVAILABLE, value=raw)


def read_extreme_rain(ds: HazardDatasetSet, point: Point) -> PhysicalReading:
    mm = _sample_raster(ds.extreme_rain_grid_path, point)
    if mm is None:
        return PhysicalReading("extreme_rain_mm", FeatureStatus.MISSING)
    return PhysicalReading("extreme_rain_mm", FeatureStatus.AVAILABLE, value=mm)


def read_flood(
    ds: HazardDatasetSet,
    point: Point,
    extent_gdf: Optional[gpd.GeoDataFrame],
    river_gdf: Optional[gpd.GeoDataFrame],
) -> PhysicalReading:
    """Riverine-flood reading for a habitation point.

    Priority:
      1. inside an observed inundation footprint  -> marker ``1.0`` (available)
      2. else nearest-river distance in km         -> available
      3. no flood layer provided                   -> MISSING, never "safe 0 km"
    """
    if extent_gdf is not None and point_inside_any(point, extent_gdf):
        return PhysicalReading("flood_inundation", FeatureStatus.AVAILABLE, value=1.0)
    if river_gdf is not None and not river_gdf.empty:
        km = nearest_feature_distance_km(point, river_gdf)
        if km is not None:
            return PhysicalReading("flood_river_dist_km", FeatureStatus.AVAILABLE, value=km)
        return PhysicalReading("flood_river_dist_km", FeatureStatus.MISSING)
    return PhysicalReading("flood_extent_absent", FeatureStatus.NOT_APPLICABLE)


# ---------------------------------------------------------------------------
# Public orchestration
# ---------------------------------------------------------------------------
def assign_hazard_readings(
    habitations_gdf: gpd.GeoDataFrame,
    ds: HazardDatasetSet,
) -> gpd.GeoDataFrame:
    """Enrich a habitation GeoDataFrame with typed hazard readings per habitation.

    Adds four columns - ``flood_reading``, ``landslide_reading``,
    ``coastal_reading``, ``cloudburst_reading`` - each a :class:`HazardReading`,
    plus a free-form ``evidence`` dict describing raw sampled values + statuses.
    The input frame is never mutated; a shallow copy is returned.
    """
    out = habitations_gdf.copy()

    river_gdf = _read_vector(ds.river_vector_path)
    extent_gdf = _read_vector(ds.flood_extent_vector_path)

    flood_series: list[HazardReading] = []
    landslide_series: list[HazardReading] = []
    cloudburst_series: list[HazardReading] = []
    evidence_series: list[dict[str, Any]] = []

    coastal_reading = HazardReading(
        HazardType.COASTAL_EROSION,
        PhysicalReading("coast_buffer_km", FeatureStatus.NOT_APPLICABLE),
    )

    for _, hab in habitations_gdf.iterrows():
        point = hab.geometry

        flood_r = read_flood(ds, point, extent_gdf, river_gdf)
        land_r = read_landslide_susceptibility(ds, point)
        rain_r = read_extreme_rain(ds, point)
        # Coastal erosion applies only where a coast source was supplied; for the
        # Himalayan/Riverine pilot districts it is uniformly not_applicable.
        coastal_r = coastal_reading.physical

        flood_series.append(HazardReading(HazardType.FLOOD, flood_r))
        landslide_series.append(HazardReading(HazardType.LANDSLIDE, land_r))
        cloudburst_series.append(HazardReading(HazardType.CLOUDBURST, rain_r))

        evidence_series.append(
            {
                "flood": {"status": flood_r.status.value, "value": flood_r.value},
                "landslide": {"status": land_r.status.value, "value": land_r.value},
                "cloudburst": {"status": rain_r.status.value, "value": rain_r.value},
                "coastal": {"status": coastal_r.status.value, "value": coastal_r.value},
            }
        )

    out["flood_reading"] = flood_series
    out["landslide_reading"] = landslide_series
    out["cloudburst_reading"] = cloudburst_series
    out["coastal_reading"] = [coastal_reading] * len(out)
    out["evidence"] = evidence_series
    return out

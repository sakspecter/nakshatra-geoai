"""Spatial I/O and geospatial processing helpers used by the ETL pipeline and the
scoring service.

Kept separate from the orchestration module (``etl``) so the raster/vector
mechanics can be unit-tested independently and re-used by scenario code later.
The helpers intentionally return ``Tuple[name, RawValue | None]`` - never a 0.0
default - so the Rule 2 status is decided by the caller, not silently invented
here.
"""

from __future__ import annotations

import logging
import math
from pathlib import Path
from typing import Iterable, Optional

import geopandas as gpd
import numpy as np
import rasterio
from rasterio.transform import rowcol
from shapely.geometry import Point
from shapely.ops import nearest_points

logger = logging.getLogger(__name__)


# ---------------------------------------------------------------------------
# Raster point sampling
# ---------------------------------------------------------------------------
def sample_raster_at_points(
    raster_path: str | Path,
    points: Iterable[tuple[float, float]],
) -> list[Optional[float]]:
    """Sample a single-band raster at a list of (lon, lat).

    Returns a value where the pixel is inside the raster and is not the dataset
    nodata value; returns ``None`` otherwise. **A ``None`` here does NOT mean
    "0 hazard"** - it signals missing coverage which the caller must encode as
    ``status=FeatureStatus.MISSING``.
    """
    values: list[Optional[float]] = []
    with rasterio.open(raster_path) as src:
        if src.count < 1:
            raise ValueError(f"raster {raster_path} has no bands; single band expected.")
        band = src.read(1)
        nodata = src.nodata
        transform = src.transform
        for lon, lat in points:
            try:
                r, c = rowcol(transform, lon, lat)
            except Exception:
                values.append(None)
                continue
            if r < 0 or c < 0 or r >= band.shape[0] or c >= band.shape[1]:
                values.append(None)
                continue
            raw = band[r, c]
            if raw is None or (nodata is not None and raw == nodata):
                values.append(None)
                continue
            if not math.isfinite(float(raw)):
                values.append(None)
                continue
            values.append(float(raw))
    return values


def sample_raster_window_mean(
    raster_path: str | Path,
    point: tuple[float, float],
    radius_degrees: float = 0.002,
) -> Optional[float]:
    """Return the mean value over a small window centred on (lon, lat).

    Primarily used for habitation polygon-level hazard extraction. None returned
    if the window has zero valid (non-nodata) pixels.
    """
    with rasterio.open(raster_path) as src:
        left, bottom, right, top = (
            point[0] - radius_degrees,
            point[1] - radius_degrees,
            point[0] + radius_degrees,
            point[1] + radius_degrees,
        )
        # window from geography to pixel coordinates
        wx_window = ((left, bottom), (right, top))
        try:
            window = rasterio.windows.from_bounds(
                left, bottom, right, top, transform=src.transform
            )
        except Exception:
            return None
        data = src.read(1, window=window)
    nodata = src.nodata
    finite = data[np.isfinite(data)]
    if nodata is not None:
        finite = finite[finite != nodata]
    if finite.size == 0:
        return None
    return float(np.mean(finite))


# ---------------------------------------------------------------------------
# Shapely/proximity helpers for vector features
# ---------------------------------------------------------------------------
def distance_km(a: Point, b: Point) -> float:
    """Great-circle distance between two lon/lat Points in kilometres."""
    # Cheap spherical approximation sufficient for ranking inputs upstream.
    lon1, lat1 = math.radians(a.x), math.radians(a.y)
    lon2, lat2 = math.radians(b.x), math.radians(b.y)
    dlon = lon2 - lon1
    dlat = lat2 - lat1
    a_ = math.sin(dlat / 2) ** 2 + math.cos(lat1) * math.cos(lat2) * math.sin(dlon / 2) ** 2
    c = 2 * math.asin(math.sqrt(a_))
    return 6371.0 * c


def nearest_feature_distance_km(
    point_geom: Point,
    feature_gdf: gpd.GeoDataFrame,
) -> Optional[float]:
    """Return great-circle distance (km) to the closest geometry in ``feature_gdf``.

    The nearest location is found geometrically (shapely ops in lon-lat space) and
    then measured in kilometres with a spherical approximation, which is neutral to
    whether the input CRS is geographic or a projection. Returns None when the
    layer is absent/empty (caller encodes that as MISSING rather than a 0 km).
    """
    if feature_gdf is None or feature_gdf.empty or point_geom is None:
        return None
    try:
        _, nearest = nearest_points(point_geom, feature_gdf.geometry.unary_union)
    except Exception:  # pragma: no cover - empty/geometry edge cases
        return None
    return distance_km(point_geom, nearest)


# ---------------------------------------------------------------------------
# Vector rule for "is point inside an inundation / hazard polygon?"
# ---------------------------------------------------------------------------
def point_inside_any(point: Point, gdf: gpd.GeoDataFrame) -> bool:
    """Membership test against a hazard polygon layer for a single point."""
    if gdf is None or gdf.empty:
        return False
    return bool(gdf.geometry.contains(point).any())


def buffered_overlap_area(
    point: Point,
    gdf: gpd.GeoDataFrame,
    buffer_degrees: float = 0.01,
) -> float:
    """Pixel/share of buffer intersecting features; used for local exposure."""
    buf_geom = point.buffer(buffer_degrees)
    if gdf is None or gdf.empty or buf_geom is None:
        return 0.0
    try:
        inter = gdf.geometry.intersection(buf_geom).area.sum()
    except Exception:
        return 0.0
    return float(inter)

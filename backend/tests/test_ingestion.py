"""Ingestion pipeline unit tests (no DB, no external GIS stack)."""

from __future__ import annotations

from pathlib import Path

import pytest

from app.services.ingestion import (
    PIPELINE_STAGES,
    district_record,
    read_vector_file,
    registered_districts,
    run_ingestion_pipeline,
)

SAMPLE = (
    Path(__file__).resolve().parent.parent
    / "data" / "ingestion" / "samples" / "namchi_points.geojson"
)


@pytest.fixture()
def namchi_result():
    raw = SAMPLE.read_bytes()
    return run_ingestion_pipeline(
        state_name="Sikkim",
        district_name="Namchi",
        raw=raw,
        filename="namchi_points.geojson",
    )


def test_pipeline_completes_with_all_stages(namchi_result):
    out = namchi_result
    assert out["status"] == "complete"
    assert out["pipeline_stages"] == PIPELINE_STAGES
    assert out["habitations_loaded"] == 4
    assert out["state_code"] == "SK"
    assert out["district_code"] == "NAMCHI"


def test_pipeline_registers_district(namchi_result):
    rec = district_record("NAMCHI")
    assert rec is not None
    assert rec.district_name == "Namchi"
    assert len(rec.habitations) == 4
    assert len(rec.capacity_limits) == 4
    assert len(rec.bbox) == 4
    # bbox is [west, south, east, north] with south <= north
    assert rec.bbox[1] <= rec.bbox[3]
    assert any(r["district_code"] == "NAMCHI" for r in registered_districts())


def test_rule4_min_capacity_governs(namchi_result):
    rec = district_record("NAMCHI")
    for cap in rec.capacity_limits:
        overall = min(
            cap["housing_cap"],
            cap["water_cap"],
            cap["healthcare_cap"],
            cap["safe_land_cap"],
            cap["accessibility_cap"],
        )
        assert cap["overall_capacity"] == overall


def test_hazard_scores_stay_in_unit_range(namchi_result):
    rec = district_record("NAMCHI")
    for hz in rec.hazards:
        for _htype, score in hz["hazard_scores"].items():
            assert 0.0 <= score <= 1.0


def test_pipeline_is_deterministic():
    raw = SAMPLE.read_bytes()
    a = run_ingestion_pipeline("Sikkim", "Namchi", raw, "namchi_points.geojson")
    b = run_ingestion_pipeline("Sikkim", "Namchi", raw, "namchi_points.geojson")
    assert a["habitations_loaded"] == b["habitations_loaded"]
    assert a["bbox"] == b["bbox"]
    assert a["zone_breakdown"] == b["zone_breakdown"]


def test_crs_normalisation_accepts_projected_crs(tmp_path):
    """A packaged file carrying EPSG:3857 must be normalized to EPSG:4326.

    GeoJSON is spec-defined as CRS84 (no embedded CRS), so the reprojection
    contract is exercised with a GeoPackage written in Web Mercator.
    """
    import geopandas as gpd
    from shapely.geometry import Point

    gdf = gpd.GeoDataFrame(
        {"name": ["Mercator Point"], "population": [100]},
        geometry=[Point(9829617.5, 3136217.4)],  # ~88.3E 27.1N in EPSG:3857
        crs="EPSG:3857",
    )
    gpkg = tmp_path / "mercator.gpkg"
    gdf.to_file(gpkg, driver="GPKG")

    out = read_vector_file(gpkg.read_bytes(), "mercator.gpkg")
    assert out.crs.to_epsg() == 4326
    x, y = out.geometry.iloc[0].x, out.geometry.iloc[0].y
    assert 80.0 < x < 95.0
    assert 25.0 < y < 29.0


def test_empty_file_rejected():
    import json

    raw = json.dumps({"type": "FeatureCollection", "features": []}).encode("utf-8")
    with pytest.raises(ValueError):
        run_ingestion_pipeline("Sikkim", "Empty", raw, "empty.geojson")
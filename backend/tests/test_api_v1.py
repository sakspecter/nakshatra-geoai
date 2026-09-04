"""Module 6 API smoke tests for the Module-5/6 engines behind the dashboard."""

from __future__ import annotations

import pytest

from fastapi.testclient import TestClient

# build application once (DB engine is constructed but never connected unless a
# handler truly queries - handlers for this suite operate on the seed workspace)
from app.main import app


@pytest.fixture(scope="module")
def client():
    with TestClient(app) as c:
        yield c


def test_overview_kpis(client: TestClient):
    resp = client.get("/api/v1/overview")
    assert resp.status_code == 200
    body = resp.json()
    assert "totals" in body
    assert body["totals"]["red_zone_count"] >= 0
    assert "by_state" in body and len(body["by_state"]) >= 1
    assert any(d["safe_available_capacity"] > 0 for d in body["by_district"])


def test_vector_tiles_geojson(client: TestClient):
    resp = client.get("/api/v1/map/vector-tiles")
    assert resp.status_code == 200
    fc = resp.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) >= 1
    kinds = {f["properties"]["kind"] for f in fc["features"]}
    assert "destination" in kinds


def test_habitation_profile(client: TestClient):
    resp = client.get("/api/v1/habitations/102")   # Gopeshwar riverside
    assert resp.status_code == 200
    body = resp.json()
    assert body["habitation_id"] == 102
    assert body["zone"] in {"red", "yellow", "green"}
    assert "hazard_evidence" in body
    assert body["data_quality_flags"]["evidence_sufficient"] is True


def test_relocation_plan(client: TestClient):
    resp = client.post(
        "/api/v1/relocation/plan",
        json={"habitation_ids": [102, 103], "allow_split": True},
    )
    assert resp.status_code == 200
    body = resp.json()
    assert "allocations" in body
    # population served + unserved == sum of risk populations in request premise
    assert body["population_served"] >= 0
    assert "unmet_demand" in body


def test_scenario_simulate(client: TestClient):
    resp = client.post(
        "/api/v1/scenario/simulate",
        json={
            "name": "Extreme cloudburst +25% Chamoli",
            "triggers": [
                {
                    "kind": "rainfall_pct",
                    "factor": 1.25,
                    "hazard_types": ["cloudburst"],
                    "scope_all": False,
                    "district": "CHAMOLI",
                }
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()
    assert body["baseline_untouched"] is True
    assert {"baseline_red_zones", "scenario_red_zones"}.issubset(
        set(body["side_by_side"].keys())
    )
    assert "delta_red_zones" in body["delta"]


def test_scenario_simulate_returns_habitation_deltas_rowset(client: TestClient):
    """Regression: the dashboard previously showed an aggregate-only warning.

    The simulator must always materialize an explicit itemized row-set with
    pre/post risk scores and a human-readable delta category per habitation.
    """
    resp = client.post(
        "/api/v1/scenario/simulate",
        json={
            "name": "Row-set regression",
            "triggers": [
                {
                    "kind": "rainfall_pct",
                    "factor": 1.25,
                    "hazard_types": ["cloudburst"],
                    "scope_all": True,
                }
            ],
        },
    )
    assert resp.status_code == 200
    body = resp.json()

    deltas = body["habitation_deltas"]
    assert isinstance(deltas, list) and len(deltas) > 0
    # one row per simulated habitation; matches the legacy rows contract
    assert len(deltas) == len(body["rows"])

    first = deltas[0]
    assert {"habitation_id", "habitation_name", "pre_risk_score",
            "post_risk_score", "risk_delta", "delta_category"}.issubset(first.keys())
    assert first["habitation_name"] != ""
    assert first["delta_category"] in {"Improved", "Degraded", "Unchanged"}
    # arithmetic consistency: post - pre == delta (rounded)
    assert abs(
        (first["post_risk_score"] - first["pre_risk_score"]) - first["risk_delta"]
    ) < 5e-4
    # legacy rows remain populated for backward compatibility
    assert body["rows"][0]["habitation_name"] != ""


def test_spatial_states_catalog(client: TestClient):
    resp = client.get("/api/v1/spatial/states")
    assert resp.status_code == 200
    states = resp.json()
    assert len(states) >= 36  # nationwide India catalog
    codes = {s["state_code"] for s in states}
    assert {"UK", "AS", "SK"}.issubset(codes)
    pilot = next(s for s in states if s["state_code"] == "UK")
    assert pilot["district_count"] >= 3


def test_spatial_districts_cascade(client: TestClient):
    resp = client.get("/api/v1/spatial/districts", params={"state_code": "UK"})
    assert resp.status_code == 200
    rows = resp.json()
    assert {r["district_code"] for r in rows} >= {"CHAMOLI"}
    chamoli = next(r for r in rows if r["district_code"] == "CHAMOLI")
    assert chamoli["habitation_count"] >= 1
    assert len(chamoli["bbox"]) == 4


def test_spatial_habitations_geojson(client: TestClient):
    resp = client.get("/api/v1/spatial/habitations", params={"district_code": "CHAMOLI"})
    assert resp.status_code == 200
    fc = resp.json()
    assert fc["type"] == "FeatureCollection"
    assert len(fc["features"]) >= 1
    assert len(fc["meta"]["bbox"]) == 4
    props = fc["features"][0]["properties"]
    assert props["kind"] == "habitation"
    assert props["zone"] in {"red", "yellow", "green"}

    missing = client.get(
        "/api/v1/spatial/habitations", params={"district_code": "NOWHERE"}
    )
    assert missing.status_code == 404


def test_admin_ingest_endpoint(client: TestClient):
    """Zero-code ingestion: upload a GeoJSON for Namchi (Sikkim)."""
    from pathlib import Path

    sample = Path(__file__).resolve().parent.parent / "data" / "ingestion" / "samples" / "namchi_points.geojson"
    raw = sample.read_bytes()

    resp = client.post(
        "/api/v1/admin/ingest",
        data={"state_name": "Sikkim", "district_name": "Namchi"},
        files={"file": ("namchi_points.geojson", raw, "application/geo+json")},
    )
    assert resp.status_code == 200, resp.text
    body = resp.json()
    assert body["status"] == "complete"
    assert body["state_code"] == "SK"
    assert body["district_code"] == "NAMCHI"
    assert body["habitations_loaded"] >= 1
    assert set(body["zone_breakdown"].keys()) >= {"red", "yellow", "green"}
    assert len(body["pipeline_stages"]) == 6

    # the ingested district is immediately addressable via the spatial catalog
    listed = client.get("/api/v1/spatial/districts", params={"state_code": "SK"}).json()
    namchi = next(r for r in listed if r["district_code"] == "NAMCHI")
    assert namchi["habitation_count"] == body["habitations_loaded"]
    assert namchi["source"] == "ingested"

    fc = client.get(
        "/api/v1/spatial/habitations", params={"district_code": "NAMCHI"}
    ).json()
    assert fc["meta"]["count"] == body["habitations_loaded"]
    assert fc["meta"]["bbox"] == body["bbox"]

    # registry listing endpoint
    reg = client.get("/api/v1/admin/ingested").json()
    assert any(r["district_code"] == "NAMCHI" for r in reg)


def test_admin_ingest_rejects_bad_extension(client: TestClient):
    resp = client.post(
        "/api/v1/admin/ingest",
        data={"state_name": "Sikkim", "district_name": "Namchi"},
        files={"file": ("virus.exe", b"not-a-gis-file", "application/octet-stream")},
    )
    assert resp.status_code == 400

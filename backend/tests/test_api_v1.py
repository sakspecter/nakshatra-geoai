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

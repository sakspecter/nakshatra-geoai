"""One-off smoke check for the new spatial + admin endpoints."""
import io

from fastapi.testclient import TestClient

from app.main import app

c = TestClient(app)

s = c.get("/api/v1/spatial/states").json()
print("states:", len(s), s[0])

d = c.get("/api/v1/spatial/districts", params={"state_code": "SK"}).json()
print("SK districts:", d)

raw = open("data/ingestion/samples/namchi_points.geojson", "rb").read()
r = c.post(
    "/api/v1/admin/ingest",
    data={"state_name": "Sikkim", "district_name": "Namchi"},
    files={"file": ("namchi.geojson", io.BytesIO(raw), "application/geo+json")},
)
print("ingest:", r.status_code)
body = r.json()
print("habitations_loaded:", body["habitations_loaded"], "bbox:", body["bbox"])

h = c.get("/api/v1/spatial/habitations", params={"district_code": "NAMCHI"}).json()
print("hab geojson count:", h["meta"]["count"], "bbox:", h["meta"]["bbox"])

# unknown district -> 404
nf = c.get("/api/v1/spatial/habitations", params={"district_code": "NOWHERE"})
print("unknown district status:", nf.status_code)

# pilot district still resolves from seed workspace
p = c.get("/api/v1/spatial/habitations", params={"district_code": "CHAMOLI"}).json()
print("CHAMOLI count:", p["meta"]["count"], "bbox:", p["meta"]["bbox"])

scn = c.post(
    "/api/v1/scenario/simulate",
    json={
        "name": "x",
        "triggers": [{"kind": "rainfall_pct", "factor": 1.25, "hazard_types": ["cloudburst"], "scope_all": True}],
    },
).json()
print("deltas:", len(scn["habitation_deltas"]), scn["habitation_deltas"][0]["delta_category"])
print("SMOKE_OK")

"""Stable in-memory pilot dataset used only when no live database is wired.

These records mirror the two pilot geographies (Uttarakhand: Chamoli /
Pithoragarh; Assam: Dhemaji / Kamrup-M) so every Module-6 API endpoint is
runnable out of the box and deterministic. The ORM/analytics later substitute a
real session; the contracts (dict shape) stay identical.
"""

from __future__ import annotations

from typing import Mapping

from app.core.enums import HazardType

# NOTE: hazard dict supplies ONLY hazard types actually present for the
# settlement (Chamoli: landslide + cloudburst; Dhemaji: flood + cloudburst).
RAW_HABITATIONS: list[dict] = [
    {
        "habitation_id": 101,
        "code": "UK-CHAM-01",
        "name": "Joshimath Colony",
        "state_code": "UK",
        "district_code": "CHAMOLI",
        "total_population": 642,
        "vulnerable_share": 0.41,
        "hazard": {HazardType.LANDSLIDE: 0.32, HazardType.CLOUDBURST: 0.28},
    },
    {
        "habitation_id": 102,
        "code": "UK-CHAM-02",
        "name": "Gopeshwar Riverside",
        "state_code": "UK",
        "district_code": "CHAMOLI",
        "total_population": 215,
        "vulnerable_share": 0.88,
        "hazard": {HazardType.LANDSLIDE: 0.42, HazardType.CLOUDBURST: 0.6},
    },
    {
        "habitation_id": 103,
        "code": "UK-CHAM-03",
        "name": "Nandprayag Upper",
        "state_code": "UK",
        "district_code": "CHAMOLI",
        "total_population": 388,
        "vulnerable_share": 0.72,
        "hazard": {HazardType.LANDSLIDE: 0.74, HazardType.CLOUDBURST: 0.31},
    },
    {
        "habitation_id": 104,
        "code": "UK-PITH-01",
        "name": "Pithoragarh Gate",
        "state_code": "UK",
        "district_code": "PITHORAGARH",
        "total_population": 290,
        "vulnerable_share": 0.80,
        "hazard": {HazardType.LANDSLIDE: 0.55, HazardType.FLOOD: 0.05},
    },
    {
        "habitation_id": 201,
        "code": "AS-DHE-01",
        "name": "Dhemaji Bargaon",
        "state_code": "AS",
        "district_code": "DHEMAJI",
        "total_population": 976,
        "vulnerable_share": 0.62,
        "hazard": {HazardType.FLOOD: 0.33, HazardType.CLOUDBURST: 0.40},
    },
    {
        "habitation_id": 202,
        "code": "AS-DHE-02",
        "name": "Dhemaji Lower Flats",
        "state_code": "AS",
        "district_code": "DHEMAJI",
        "total_population": 433,
        "vulnerable_share": 0.93,
        "hazard": {HazardType.FLOOD: 0.78, HazardType.CLOUDBURST: 0.12},
    },
]

RAW_DESTINATIONS: list[dict] = [
    {
        "id": 1,
        "code": "UK-GRN-CHAM-A1",
        "name": "Chamoli High Ground West",
        "state_code": "UK",
        "district_code": "CHAMOLI",
        "housing_cap": 900,
        "water_cap": 650,
        "healthcare_cap": 500,
        "safe_land_cap": 820,
        "accessibility_cap": 700,
        "population_now": 210,
        "safety": 0.86,
        "access": 0.72,
        "infra": 0.66,
        "allow_cross_district": False,
        "allow_cross_state": False,
        "lon": 79.52,
        "lat": 30.35,
    },
    {
        "id": 2,
        "code": "UK-GRN-PITH-B2",
        "name": "Pithoragarh Saddle",
        "state_code": "UK",
        "district_code": "PITHORAGARH",
        "housing_cap": 600,
        "water_cap": 400,
        "healthcare_cap": 380,
        "safe_land_cap": 1000,
        "accessibility_cap": 520,
        "population_now": 95,
        "safety": 0.90,
        "access": 0.60,
        "infra": 0.72,
        "allow_cross_district": False,
        "allow_cross_state": False,
        "lon": 80.21,
        "lat": 29.54,
    },
    {
        "id": 3,
        "code": "AS-GRN-DHE-C3",
        "name": "Dhemaji Raised Bund North",
        "state_code": "AS",
        "district_code": "DHEMAJI",
        "housing_cap": 800,
        "water_cap": 720,
        "healthcare_cap": 300,
        "safe_land_cap": 420,
        "accessibility_cap": 600,
        "population_now": 130,
        "safety": 0.83,
        "access": 0.81,
        "infra": 0.74,
        "allow_cross_district": False,
        "allow_cross_state": False,
        "lon": 94.55,
        "lat": 27.48,
    },
]


# WGS84 representative centroid per pilot district (demo map tiles only; DB
# streams each habitation's surveyed geom in production).
DISTRICT_CENTROIDS: dict[str, tuple[float, float]] = {
    "CHAMOLI": (79.36, 30.45),
    "PITHORAGARH": (80.21, 29.54),
    "DHEMAJI": (94.58, 27.48),
    "KAMRUP-METROPOLITAN": (91.79, 26.14),
}


def district_centroid(district_code: str) -> tuple[float, float]:
    """Pilot-district centroid fallback used to paint demo map points."""
    return DISTRICT_CENTROIDS.get(district_code, (76.7, 26.0))


def _normalise(raw: Mapping) -> dict:
    return dict(raw)

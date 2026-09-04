"""Nationwide India administrative catalog.

Source of truth for the cascading State -> District selectors and the Admin
Spatial Ingestion pipeline. ``state_code`` is deliberately TEXT-native so that
any Indian state / Union Territory can be onboarded via ``POST /admin/ingest``
without code changes (the legacy ``state_code`` DB enum only mirrors the pilot
states; the nationwide spatial tables use TEXT columns).
"""

from __future__ import annotations

from typing import TypedDict


class IndiaState(TypedDict):
    state_code: str
    state_name: str
    region: str


# All 36 states / union territories. The two legacy pilot states (UK, AS) keep
# their existing short codes for backward compatibility.
INDIA_STATES: list[IndiaState] = [
    {"state_code": "UK", "state_name": "Uttarakhand", "region": "North"},
    {"state_code": "AS", "state_name": "Assam", "region": "North-East"},
    {"state_code": "SK", "state_name": "Sikkim", "region": "North-East"},
    {"state_code": "JK", "state_name": "Jammu and Kashmir", "region": "North"},
    {"state_code": "HP", "state_name": "Himachal Pradesh", "region": "North"},
    {"state_code": "PB", "state_name": "Punjab", "region": "North"},
    {"state_code": "CH", "state_name": "Chandigarh", "region": "North"},
    {"state_code": "HR", "state_name": "Haryana", "region": "North"},
    {"state_code": "DL", "state_name": "Delhi", "region": "North"},
    {"state_code": "RJ", "state_name": "Rajasthan", "region": "North"},
    {"state_code": "UP", "state_name": "Uttar Pradesh", "region": "North"},
    {"state_code": "BR", "state_name": "Bihar", "region": "East"},
    {"state_code": "WB", "state_name": "West Bengal", "region": "East"},
    {"state_code": "JH", "state_name": "Jharkhand", "region": "East"},
    {"state_code": "OD", "state_name": "Odisha", "region": "East"},
    {"state_code": "CG", "state_name": "Chhattisgarh", "region": "Central"},
    {"state_code": "MP", "state_name": "Madhya Pradesh", "region": "Central"},
    {"state_code": "GJ", "state_name": "Gujarat", "region": "West"},
    {"state_code": "MH", "state_name": "Maharashtra", "region": "West"},
    {"state_code": "GA", "state_name": "Goa", "region": "West"},
    {"state_code": "DD", "state_name": "Dadra and Nagar Haveli and Daman and Diu", "region": "West"},
    {"state_code": "KL", "state_name": "Kerala", "region": "South"},
    {"state_code": "TN", "state_name": "Tamil Nadu", "region": "South"},
    {"state_code": "KA", "state_name": "Karnataka", "region": "South"},
    {"state_code": "AP", "state_name": "Andhra Pradesh", "region": "South"},
    {"state_code": "TS", "state_name": "Telangana", "region": "South"},
    {"state_code": "AN", "state_name": "Andaman and Nicobar Islands", "region": "Islands"},
    {"state_code": "LD", "state_name": "Lakshadweep", "region": "Islands"},
    {"state_code": "PY", "state_name": "Puducherry", "region": "South"},
    {"state_code": "AR", "state_name": "Arunachal Pradesh", "region": "North-East"},
    {"state_code": "NL", "state_name": "Nagaland", "region": "North-East"},
    {"state_code": "MN", "state_name": "Manipur", "region": "North-East"},
    {"state_code": "MZ", "state_name": "Mizoram", "region": "North-East"},
    {"state_code": "TR", "state_name": "Tripura", "region": "North-East"},
    {"state_code": "ML", "state_name": "Meghalaya", "region": "North-East"},
    {"state_code": "LA", "state_name": "Ladakh", "region": "North"},
]

# Pilot fallback districts per state for the cascading selector (seed mode).
_PILOT_DISTRICTS: dict[str, list[str]] = {
    "UK": ["CHAMOLI", "PITHORAGARH", "RUDRAPRAYAG"],
    "AS": ["DHEMAJI", "JORHAT", "KAMRUP"],
    "SK": ["NAMCHI", "GANGTOK"],
}


def state_name_for(state_code: str) -> str:
    """Human-readable state name for a code (falls back to the code)."""
    for s in INDIA_STATES:
        if s["state_code"] == state_code:
            return s["state_name"]
    return state_code


def canonical_states() -> list[IndiaState]:
    """Return the deduplicated state catalog for API output."""
    seen: set[str] = set()
    out: list[IndiaState] = []
    for s in INDIA_STATES:
        if s["state_code"] in seen:
            continue
        seen.add(s["state_code"])
        out.append(s)
    return out


def pilot_districts() -> dict[str, list[str]]:
    """Pilot districts per state (seed fallback for the cascading selector)."""
    return {k: list(v) for k, v in _PILOT_DISTRICTS.items()}
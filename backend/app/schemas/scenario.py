"""Pydantic schemas for Scenario simulation (Rule 5 / Rule 6)."""

from __future__ import annotations

from datetime import datetime
from typing import Any, Optional

from pydantic import BaseModel, Field

from app.schemas.common import OrmModel, ProvenanceMixin
from app.schemas.enums import (
    DataConfidence,
    HazardType,
    ScenarioStatus,
    ZoneBand,
)


class ScenarioProvenance(ProvenanceMixin):
    """Scenario creation pins the *scenario* version (Rule 6)."""

    scenario_version: str = Field(default="scenario.new")
    baseline_dataset_version: str = Field(default="")


class TriggerConfig(BaseModel):
    """Structure for ``trigger_config``; flexible enough for any what-if knob.

    Examples:
    - ``{"kind":"rainfall_delta","hazard_type":"landslide","+20%": True, "delta_pct": 20}``
    - ``{"kind":"rainfall_climate","magnitude":1.2}``
    """

    kind: str = Field(alias="kind", default="rainfall_delta")
    hazard_type: HazardType = Field(default=HazardType.LANDSLIDE)
    delta_pct: Optional[float] = Field(default=None, description="Signed percentage trigger, e.g. +20 => 20.0")
    extreme: Optional[bool] = Field(default=True)
    extra: Optional[dict[str, Any]] = Field(default_factory=dict)


class ScenarioCreate(ScenarioProvenance):
    """Create a draft scenario definition; execution is async/queued upstream."""

    name: str = Field(min_length=1)
    description: Optional[str] = None
    admin_unit_id: Optional[int] = Field(default=None, ge=1)
    created_by: str = Field(min_length=1)
    trigger_config: TriggerConfig


class ScenarioRead(OrmModel):
    """Read projection for a persisted scenario row."""

    id: int
    name: str
    description: Optional[str] = None
    admin_unit_id: Optional[int] = None
    trigger_config: dict[str, Any] | None = None
    baseline_dataset_version: Optional[str] = None
    scenario_version: Optional[str] = None
    status: ScenarioStatus
    created_by: str
    created_at: Optional[datetime] = None
    completed_at: Optional[datetime] = None
    result_summary: Optional[dict[str, Any]] = None


class ScenarioHazardDeltaOut(OrmModel):
    id: int
    scenario_id: int
    habitation_id: int
    hazard_type: HazardType
    baseline_score: Optional[float] = None
    scenario_score: Optional[float] = None


class ScenarioZoneChangeOut(OrmModel):
    id: int
    scenario_id: int
    habitation_id: int
    baseline_band: Optional[ZoneBand] = None
    scenario_band: Optional[ZoneBand] = None
    notes: Optional[str] = None

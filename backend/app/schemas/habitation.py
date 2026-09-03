"""Pydantic schemas for the Habitation baseline entity.

Every optional measurement is exposed as a ``ValuedFeature`` so a client cannot
silently pass a ``0`` as though it were measured. Create and Read projections are
kept separate and explicit.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, ConfigDict, Field, model_validator

from app.schemas.common import (
    GeoJSONPoint,
    ProvenanceMixin,
    ValuedFeature,
    OrmModel,
)
from app.schemas.enums import DataConfidence


class _HabCore(BaseModel):
    """Fields shared across Create & Update projection for habitations."""

    habitation_code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1)
    ward: Optional[str] = Field(default=None)
    admin_unit_id: int = Field(ge=1)

    geom: GeoJSONPoint
    raw_boundary: Optional[object] = Field(default=None, description="Optional GeoJSON polygon.")

    total_population: int = Field(ge=0)
    households: int = Field(ge=0)
    vulnerable_pop_share: float = Field(ge=0.0, le=1.0)

    population_confidence: DataConfidence = DataConfidence.CONFIRMED
    demography_confidence: DataConfidence = DataConfidence.CONFIRMED

    # Optional demographic sub-populations each with an explicit status.
    children_under5: Optional[ValuedFeature[int]] = None
    elderly_above60: Optional[ValuedFeature[int]] = None
    disabled: Optional[ValuedFeature[int]] = None
    female_headed_households: Optional[ValuedFeature[int]] = None

    housing_quality_score: Optional[ValuedFeature[float]] = None
    pucca_house_ratio: Optional[ValuedFeature[float]] = None
    avg_household_income_class: Optional[ValuedFeature[int]] = None

    dist_health_km: Optional[ValuedFeature[float]] = None
    dist_school_km: Optional[ValuedFeature[float]] = None
    dist_market_km: Optional[ValuedFeature[float]] = None
    service_confidence: DataConfidence = DataConfidence.CONFIRMED

    evac_road_access_km: Optional[ValuedFeature[float]] = None
    evac_access_difficulty_score: Optional[ValuedFeature[float]] = None
    access_confidence: DataConfidence = DataConfidence.CONFIRMED


class HabitationProvenance(ProvenanceMixin):
    """Provenance payload for a habitation record (Rule 6)."""


class HabitationCreate(_HabCore, HabitationProvenance):
    """Write-projection required metadata for creating a live baseline row."""

    dataset_version: str = Field(..., min_length=1)
    ingestion_batch: str = Field(..., min_length=1)
    # explicitly set to false: the version pins live on getters

    @model_validator(mode="after")
    def _ensure_live_code_unique_input(self) -> "HabitationCreate":
        """Warn-level guard: code field is required and normalised."""
        self.habitation_code = self.habitation_code.strip()
        if not self.habitation_code:
            raise ValueError("habitation_code must be a non-empty string.")
        return self


class HabitationRead(OrmModel):
    """Read projection. Mirrors the immutable baseline ORM columns so the API can
    stream a stored habitations row without recomputation."""

    model_config = ConfigDict(from_attributes=True)

    id: int
    habitation_code: str
    name: str
    ward: Optional[str] = None
    admin_unit_id: int
    total_population: int
    households: int
    vulnerable_pop_share: float
    population_confidence: DataConfidence
    demography_confidence: DataConfidence
    service_confidence: DataConfidence
    access_confidence: DataConfidence
    valid_from: datetime
    valid_to: Optional[datetime] = None
    dataset_version: str
    ingestion_batch: str

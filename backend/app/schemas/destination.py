"""Pydantic schemas for the candidate Destination / carrying-capacity model.

Rule 4 is carried into the *schema* contract by requiring all five independent
ceilings, then computing ``overall_capacity`` as the MIN of them at the service
layer (the DB ALSO enforces it via trigger). A destination only exposes a derived
``overall_capacity`` in responses; it can never be entered directly.
"""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field, model_validator

from app.schemas.common import (
    GeoJSONPoint,
    GeoJSONPolygon,
    OrmModel,
    ProvenanceMixin,
    ScoreFeature,
)
from app.schemas.enums import DataConfidence, ConstraintType


class _CapacityInputs(BaseModel):
    """The five independently-measured ceiling values required by Rule 4."""

    housing_cap: int = Field(ge=0)
    water_cap: int = Field(ge=0)
    healthcare_cap: int = Field(ge=0)
    safe_land_cap: int = Field(ge=0)
    accessibility_cap: int = Field(ge=0)

    @property
    def overall_capacity(self) -> int:
        """Return the tightly-constraining floor across every ceiling (Rule 4)."""
        return min(
            self.housing_cap,
            self.water_cap,
            self.healthcare_cap,
            self.safe_land_cap,
            self.accessibility_cap,
        )


class DestinationProvenance(ProvenanceMixin):
    pass


class DestinationCreate(_CapacityInputs, DestinationProvenance):
    """Write model for registering a new destination (candidate Green site)."""

    destination_code: str = Field(min_length=1, max_length=128)
    name: str = Field(min_length=1)
    admin_unit_id: int = Field(ge=1)
    geom: GeoJSONPolygon
    centroid: GeoJSONPoint
    is_verified_site: bool = Field(default=False)

    # Rule 2: safety / access / infra are best-effort scores - as ScoreFeature.
    safety_score: Optional[ScoreFeature] = None
    accessibility_score: Optional[ScoreFeature] = None
    infrastructure_score: Optional[ScoreFeature] = None
    quality_confidence: DataConfidence = DataConfidence.CONFIRMED

    @model_validator(mode="after")
    def _validate_centroid_inside(self) -> "DestinationCreate":
        # simplistic sanity: for a spatial write we keep ring/inside checks to the
        # service layer; here we only guard non-empty.
        if not self.geom.coordinates:
            raise ValueError("Destination polygon must contain at least one ring")
        return self


class DestinationRead(OrmModel):
    """Read projection of a persisted destination including the derived ceiling."""

    id: int
    destination_code: str
    name: str
    admin_unit_id: int
    is_verified_site: bool
    housing_cap: int
    water_cap: int
    healthcare_cap: int
    safe_land_cap: int
    accessibility_cap: int
    overall_capacity: int
    safety_score: Optional[float] = None
    accessibility_score: Optional[float] = None
    infrastructure_score: Optional[float] = None
    quality_confidence: DataConfidence
    dataset_version: str
    risk_config_version: str
    created_at: Optional[datetime] = None

    @property
    def bottleneck(self) -> ConstraintType | None:
        """Expose which single constraint currently governs this site (Rule 4)."""
        pairs = [
            (self.housing_cap, ConstraintType.HOUSING),
            (self.water_cap, ConstraintType.WATER),
            (self.healthcare_cap, ConstraintType.HEALTHCARE),
            (self.safe_land_cap, ConstraintType.SAFE_LAND),
            (self.accessibility_cap, ConstraintType.ACCESSIBILITY),
        ]
        if not pairs:
            return None
        return min(pairs, key=lambda item: item[0])[1]

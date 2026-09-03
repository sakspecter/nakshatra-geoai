"""Pydantic schemas for the Hazard layer (Rule 3, separate from Vulnerability)."""

from __future__ import annotations

from datetime import datetime
from typing import Optional

from pydantic import BaseModel, Field

from app.schemas.common import ProvenanceMixin, OrmModel, ScoreFeature
from app.schemas.enums import DataConfidence, HazardType


class HazardProvenance(ProvenanceMixin):
    """Provenance common to hazard writes; model_version optional at this layer."""

    dataset_version: str = Field(default="hazard.raster.v0")
    risk_config_version: str = Field(default="risk_cfg.v1")
    model_version: Optional[str] = Field(default=None)


class HazardLayerCreate(HazardProvenance):
    """Write a single deterministic hazard score for a habitation.

    ``score`` is a :class:`~ScoreFeature`; a ``missing``/``not_applicable`` state
    forces value ``None`` while ``available``/``low_confidence`` requires a value
    clamped by the ScoreFeature validator to [0,1]. No 0-coercion on model input.
    """

    habitation_id: int = Field(ge=1)
    hazard_type: HazardType
    score: ScoreFeature = Field(
        ..., description="0..1 normalized hazard score + explicit presence status."
    )
    hazard_confidence: DataConfidence = DataConfidence.CONFIRMED
    hazard_extent: Optional[object] = Field(
        default=None, description="Optional clipped hazard-extent GeoJSON geometry."
    )
    intensity_class: Optional[str] = Field(default=None)

    @property
    def hazard_score_01(self) -> Optional[float]:
        """Flattened projection for ORM mapping: None only when missing/na."""
        return self.score.value


class HazardLayerImport(HazardLayerCreate):
    """Alias used by the ETL ingest path: identical to Create except dataset_version
    will usually already be pinned by the raster source."""


class HazardLayerRead(OrmModel):
    """Read projection mirroring the persisted hazard_layers row."""

    id: int
    habitation_id: int
    hazard_type: HazardType
    hazard_score_01: Optional[float] = None
    hazard_confidence: DataConfidence
    intensity_class: Optional[str] = None
    dataset_version: str
    model_version: Optional[str] = None
    computed_at: datetime

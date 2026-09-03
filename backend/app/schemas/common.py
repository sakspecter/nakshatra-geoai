"""Shared Pydantic base models: provenance metadata, geometry encoding, generic
value+status pair enforcing the Missing Data Rule, and ORM configuration.
"""

from __future__ import annotations

from typing import Any, Generic, TypeVar

from pydantic import (
    BaseModel,
    ConfigDict,
    Field,
    model_validator,
)

from app.schemas.enums import FeatureStatus

# ---------------------------------------------------------------------------
# ORM configuration shim: response models read from SQLAlchemy ORM attributes.
# ---------------------------------------------------------------------------
class OrmModel(BaseModel):
    """Base for all response schemas that serialize ORM objects.

    ``from_attributes=True`` lets pydantic read columns straight from a mapped
    instance. This is the **read** projection - write models (subclasses not
    using this) require explicit clientside ingest, so an accidental 0 can't
    sneak in via unset attribute coercion.
    """

    model_config = ConfigDict(from_attributes=True, populate_by_name=True)


# ---------------------------------------------------------------------------
# Provenance (Rule 6)
# ---------------------------------------------------------------------------
class ProvenanceMixin(BaseModel):
    """Four version pillars carried by every analytical payload (Rule 6)."""

    dataset_version: str = Field(
        default="dataset.unknown",
        min_length=1,
        description="Version tag of the underlying dataset this row was derived from.",
    )
    risk_config_version: str = Field(
        default="risk_cfg.v1",
        min_length=1,
        description="Version of the deterministic risk configuration used.",
    )

    # model / scenario versions are optional at the *source* layers (hazard/vuln
    # rarely come from a model or scenario), but present for ML / scenario tables.

    def provenance_keys(self) -> dict[str, str]:
        """Return the four provenance keys, substituting sensible defaults."""
        return {
            "dataset_version": getattr(self, "dataset_version", "dataset.unknown"),
            "model_version": getattr(self, "model_version", "model.none"),
            "scenario_version": getattr(self, "scenario_version", "scenario.baseline"),
            "risk_config_version": getattr(
                self, "risk_config_version", "risk_cfg.v1"
            ),
        }


# ---------------------------------------------------------------------------
# Value + explicit status pair (Missing Data Rule machinery)
# ---------------------------------------------------------------------------
T = TypeVar("T")


class ValuedFeature(BaseModel, Generic[T]):
    """Bundles an optional numeric value with the *mandatory* state that tells
    consumers how to interpret its absence/presence.

    Pydantic-level guarantee (Rule 2):

    * A feature whose state is ``missing`` or ``not_applicable`` MUST carry a
      ``None`` value. We hard-fail if a caller submits ``0.0`` with these states,
      so "missing" never leaks upward disguised as a safe neutral.
    * A ``available`` state MUST carry a real value (refuse an empty available).
    """

    status: FeatureStatus
    value: float | int | None = Field(default=None)

    @model_validator(mode="after")
    def _enforce_missing_data_rule(self) -> "ValuedFeature[T]":
        if self.status in (FeatureStatus.MISSING, FeatureStatus.NOT_APPLICABLE):
            if self.value is not None:
                raise ValueError(
                    f"{self.status.value} features must carry value=None; "
                    f"got {self.value!r}. A missing measurement must never be "
                    "encoded as a neutral number."
                )
        if self.status is FeatureStatus.AVAILABLE and self.value is None:
            raise ValueError(
                "A feature marked available must include a concrete value."
            )
        return self


class ScoreFeature(ValuedFeature[float]):
    """A 0..1 normalized score that respects the Missing Data Rule.

    When ``available``/``low_confidence`` the value must fall within [0, 1].
    When ``missing``/``not_applicable`` the value must be None.
    """

    @model_validator(mode="after")
    def _check_score_bounds(self) -> "ScoreFeature":
        if self.value is not None and not (0.0 <= float(self.value) <= 1.0):
            raise ValueError(
                f"Normalized score must be within [0,1], got {self.value}."
            )
        return self


# ---------------------------------------------------------------------------
# Geometry encoding helpers (GeoJSON-compatible interchange for the API)
# ---------------------------------------------------------------------------
Point2D = tuple[float, float]


class GeoJSONPoint(BaseModel):
    """Lightweight GeoJSON ``Point`` used in request bodies for spatial writes."""

    type: str = Field(default="Point", frozen=True)
    coordinates: list[float] = Field(
        min_length=2, max_length=3, description="[longitude, latitude] (optionally +elevation)"
    )


class GeoJSONPolygon(BaseModel):
    """GeoJSON ``Polygon`` encoding.

    Each ring is a closed list of [lon, lat] positions of length >= 4; we defer
    rigorous ring-closure validation to Shapely/GeoPandas at the service layer,
    keeping API models focused on shape-level integrity.
    """

    type: str = Field(default="Polygon", frozen=True)
    coordinates: list[list[list[float]]] = Field(
        min_length=1, description="List of linear rings; first ring is exterior."
    )

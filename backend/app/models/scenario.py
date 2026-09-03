"""ORM models for scenario simulation (Rule 5 + Rule 6).

Scenarios run against an immutable *copy* of baseline data living in the
namespaced ``scenario_hazard_deltas`` / ``scenario_zones`` tables keyed back to a
parent ``Scenario`` row. Baseline source data is never mutated.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    DateTime,
    Float,
    ForeignKey,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DataConfidence, HazardType, ScenarioStatus, ZoneBand
from app.db.base import Base, IntPKMixin
from app.models.enum_types import DATA_CONFIDENCE, HAZARD_TYPE, SCENARIO_STATUS, ZONE_BAND


class Scenario(IntPKMixin, Base):
    """A single what-if simulation definition and its state machine."""

    __tablename__ = "scenarios"

    name: Mapped[str] = mapped_column(Text, nullable=False)
    description: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_unit_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("geo_admin_units.id"), nullable=True
    )
    # e.g. {"extreme_rainfall_delta_pct": 20, "hazard_type":"landslide"}
    trigger_config: Mapped[dict] = mapped_column(JSON, nullable=False)
    baseline_dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[ScenarioStatus] = mapped_column(
        SCENARIO_STATUS, nullable=False, default="draft"
    )
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    completed_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    result_summary: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    deltas: Mapped[list["ScenarioHazardDelta"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )
    zone_changes: Mapped[list["ScenarioZone"]] = relationship(
        back_populates="scenario", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Scenario #{self.id} {self.scenario_version} [{self.status.value}]>"


class ScenarioHazardDelta(IntPKMixin, Base):
    """One habitation's baseline-vs-scenario hazard score under a trigger."""

    __tablename__ = "scenario_hazard_deltas"

    scenario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    habitation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("habitations.id", ondelete="CASCADE"), nullable=False
    )
    hazard_type: Mapped[HazardType] = mapped_column(HAZARD_TYPE, nullable=False)
    baseline_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    scenario_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    confidence: Mapped[DataConfidence | None] = mapped_column(
        DATA_CONFIDENCE, nullable=True
    )

    scenario: Mapped["Scenario"] = relationship(back_populates="deltas")

    __table_args__ = (
        UniqueConstraint(
            "scenario_id", "habitation_id", "hazard_type", name="uq_scenario_delta"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<ScenDelta {self.scenario_id} hab={self.habitation_id} "
            f"base={self.baseline_score}->scen={self.scenario_score}>"
        )


class ScenarioZone(IntPKMixin, Base):
    """Predicted band change for a habitation relative to its immutable baseline."""

    __tablename__ = "scenario_zones"

    scenario_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("scenarios.id", ondelete="CASCADE"), nullable=False
    )
    habitation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("habitations.id", ondelete="CASCADE"), nullable=False
    )
    baseline_band: Mapped[ZoneBand | None] = mapped_column(ZONE_BAND, nullable=True)
    scenario_band: Mapped[ZoneBand | None] = mapped_column(ZONE_BAND, nullable=True)
    notes: Mapped[str | None] = mapped_column(Text, nullable=True)

    scenario: Mapped["Scenario"] = relationship(back_populates="zone_changes")

    __table_args__ = (
        UniqueConstraint("scenario_id", "habitation_id", name="uq_scenario_zone"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<ScenarioZone {self.scenario_id} hab={self.habitation_id}>"

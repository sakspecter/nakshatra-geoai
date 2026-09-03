"""ORM models for observed historical events (the ONLY ML training surface,
Rule 3) and for persisted model predictions.
"""

from __future__ import annotations

from datetime import date, datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    Boolean,
    Date,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import DataConfidence, HazardType
from app.db.base import Base, IntPKMixin
from app.models.enum_types import DATA_CONFIDENCE, HAZARD_TYPE


class HistoricalOutcome(IntPKMixin, Base):
    """An observed, real-world disaster occurrence / non-occurrence record.

    ``occurred`` is the raw Boolean label (1/0). Models are trained ONLY on these
    rows - never on composite risk scores (Rule 3). A single habitation may hold
    several historical rows across event types / dates.
    """

    __tablename__ = "historical_outcomes"

    habitation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("habitations.id", ondelete="CASCADE"), nullable=False
    )
    event_type: Mapped[HazardType] = mapped_column(HAZARD_TYPE, nullable=False)
    occurred: Mapped[bool] = mapped_column(Boolean, nullable=False)
    event_date: Mapped[date] = mapped_column(Date, nullable=False)
    severity: Mapped[str | None] = mapped_column(Text, nullable=True)
    casualties: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    displaced_hh: Mapped[int] = mapped_column(Integer, nullable=False, default=0)
    source_ref: Mapped[str | None] = mapped_column(Text, nullable=True)

    # provenance (Rule 6)
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    ingested_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HistoricalOutcome hab={self.habitation_id} {self.event_type.value} occurred={self.occurred}>"


class MLPrediction(IntPKMixin, Base):
    """A persisted supervised-learning prediction about a *specific hazard* for a
    habitation, produced from a model trained on ``historical_outcomes`` only.

    ``event_probability`` is NOT a hazard score; it is the model's calibrated
    likelihood of occurrence and is surfaced as *evidence* together with SHAP
    drivers next to the deterministic hazard / vulnerability layers (Rule 3).

    ``event_probability`` may be NULL only when the evidence was insufficient;
    ``feature_quality_status`` then reads ``insufficient_evidence`` and
    ``prediction_confidence`` maps to ``missing``.
    """

    __tablename__ = "ml_predictions"

    habitation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("habitations.id", ondelete="CASCADE"), nullable=False
    )
    hazard_type: Mapped[HazardType] = mapped_column(HAZARD_TYPE, nullable=False)
    event_probability: Mapped[float | None] = mapped_column(Float, nullable=True)
    prediction_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    model_algorithm: Mapped[str] = mapped_column(Text, nullable=False)
    feature_quality_status: Mapped[str | None] = mapped_column(Text, nullable=True)

    # provenance (Rule 6)
    model_version: Mapped[str] = mapped_column(Text, nullable=False)
    train_dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    scenario_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    risk_config_version: Mapped[str | None] = mapped_column(Text, nullable=True)

    trained_on_rows: Mapped[int | None] = mapped_column(Integer, nullable=True)
    auc_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    shap_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    prediction_confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE, nullable=False, default="confirmed"
    )
    score_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    habitation = relationship("Habitation")  # noqa: F821

    __table_args__ = (
        UniqueConstraint(
            "habitation_id", "hazard_type", "model_version", name="uq_mlpred_version"
        ),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<MLPrediction hab={self.habitation_id} p={self.event_probability} {self.model_version}>"

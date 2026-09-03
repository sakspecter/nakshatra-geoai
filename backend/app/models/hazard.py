"""ORM model for the deterministic hazard layer. (Separate from vulnerability -
Rule 3.)
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Index,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geoalchemy2 import Geometry

from app.core.enums import DataConfidence, HazardType
from app.db.base import Base, IntPKMixin
from app.models.enum_types import DATA_CONFIDENCE, HAZARD_TYPE


class HazardLayer(IntPKMixin, Base):
    """One deterministic hazard score tied to a specific habitation.

    Note (Rule 2 - Missing Data): ``hazard_score_01`` is intentionally nullable.
    A stored ``None`` means the hazard model could NOT produce a defensible value
    for this cell - it is never coerced to ``0.0`` (low hazard) downstream. The
    companion ``hazard_confidence`` records whether that the slot is a genuine
    absence, measured-but-uncertain, or not applicable.
    """

    __tablename__ = "hazard_layers"

    habitation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("habitations.id", ondelete="CASCADE"), nullable=False
    )
    hazard_type: Mapped[HazardType] = mapped_column(HAZARD_TYPE, nullable=False)
    hazard_score_01: Mapped[float | None] = mapped_column(
        Float, nullable=True  # NULL means "no defensible reading", NOT low-hazard
    )
    hazard_confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE, nullable=False, default="confirmed"
    )
    hazard_extent: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="GEOMETRY", srid=4326), nullable=True
    )
    intensity_class: Mapped[str | None] = mapped_column(Text, nullable=True)

    # provenance / Rule 6
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    model_version: Mapped[str | None] = mapped_column(Text, nullable=True)
    computed_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    habitation: Mapped["Habitation"] = relationship(back_populates="hazard_layers")  # noqa: F821

    __table_args__ = (
        CheckConstraint(
            "hazard_score_01 IS NULL OR (hazard_score_01 >= 0 AND hazard_score_01 <= 1)",
            name="ck_hazard_range",
        ),
        UniqueConstraint(
            "habitation_id", "hazard_type", "dataset_version", name="uq_hazard_layer_version"
        ),
        Index("idx_hazard_extent_gist", "hazard_extent", postgresql_using="gist"),
        Index("idx_hazard_hab", "habitation_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<HazardLayer {self.habitation_id} {self.hazard_type.value} {self.hazard_score_01}>"

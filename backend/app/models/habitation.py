"""ORM model for the (append-only, bitemporal) habitation baseline.

Rule 5 - immutable baseline is mirrored here: the table is deliberately
constructed for synthetic insert of row-versions. A unique *partial* index on
``habitation_code WHERE valid_to IS NULL`` guards one live row per code.
Confidence / provenance columns are declared locally, inline, per our
"explicit fields" convention.
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
    Integer,
    String,
    Text,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geoalchemy2 import Geometry

from app.core.enums import DataConfidence
from app.db.base import Base, IntPKMixin
from app.models.enum_types import DATA_CONFIDENCE


class Habitation(IntPKMixin, Base):  # type: ignore[misc]
    __tablename__ = "habitations"

    habitation_code: Mapped[str] = mapped_column(String(128), nullable=False, index=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    ward: Mapped[str | None] = mapped_column(Text, nullable=True)
    admin_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geo_admin_units.id", ondelete="RESTRICT"), nullable=False
    )

    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )
    raw_boundary: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=True
    )

    # ----- demographics (intentionally non-null where core, nullable where proxy)
    total_population: Mapped[int] = mapped_column(
        Integer, nullable=False, server_default="0"
    )
    households: Mapped[int] = mapped_column(Integer, nullable=False, server_default="0")
    vulnerable_pop_share: Mapped[float] = mapped_column(
        Float, nullable=False, server_default="0.0"
    )
    children_under5_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    elderly_above60_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    disabled_n: Mapped[int | None] = mapped_column(Integer, nullable=True)
    female_headed_hn: Mapped[int | None] = mapped_column(Integer, nullable=True)

    population_confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE,
        nullable=False,
        default=DataConfidence.CONFIRMED.value,
    )
    demography_confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE,
        nullable=False,
        default=DataConfidence.CONFIRMED.value,
    )

    # ----- social / shelter proxies
    avg_household_income_class: Mapped[int | None] = mapped_column(Integer, nullable=True)
    housing_quality_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    pucca_house_ratio: Mapped[float | None] = mapped_column(Float, nullable=True)
    social_proxy_confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE, nullable=False, default="confirmed"
    )

    # ----- critical-service access metrics (km) carrying confidence
    dist_health_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    dist_school_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    dist_market_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    service_confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE, nullable=False, default="confirmed"
    )

    # ----- evacuation access
    evac_road_access_km: Mapped[float | None] = mapped_column(Float, nullable=True)
    evac_access_difficulty_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    access_confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE, nullable=False, default="confirmed"
    )

    # ----- temporal immutability (Rule 5) + provenance (Rule 6)
    valid_from: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    valid_to: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    superseded_by: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("habitations.id"), nullable=True
    )
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    ingestion_batch: Mapped[str] = mapped_column(Text, nullable=False)

    # ----- relationships
    admin_unit: Mapped["GeoAdminUnit"] = relationship(  # noqa: F821
        back_populates="habitations"
    )
    hazard_layers: Mapped[list["HazardLayer"]] = relationship(  # noqa: F821
        back_populates="habitation"
    )
    vulnerability_layers: Mapped[list["VulnerabilityLayer"]] = relationship(  # noqa: F821
        back_populates="habitation"
    )

    __table_args__ = (
        CheckConstraint(
            "total_population >= 0", name="ck_hab_population_nonneg"
        ),
        CheckConstraint(
            "households >= 0", name="ck_hab_households_nonneg"
        ),
        CheckConstraint(
            "vulnerable_pop_share >= 0 AND vulnerable_pop_share <= 1",
            name="ck_hab_vulnshare_range",
        ),
        Index(
            "uq_habitation_live",
            "habitation_code",
            unique=True,
            postgresql_where="valid_to IS NULL",
        ),
        Index(
            "idx_habitation_geom_gist",
            "geom",
            postgresql_using="gist",
        ),
        Index("idx_habitation_admin", "admin_unit_id"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Habitation {self.habitation_code} pop={self.total_population}>"

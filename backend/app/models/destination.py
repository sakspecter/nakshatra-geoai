"""ORM model for candidate relocation destination (Green site) with the
Rule 4 carrying-capacity governing ceiling pre-computed by the DB trigger.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    BigInteger,
    Boolean,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
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


class Destination(IntPKMixin, Base):
    """A verified or candidate relocation destination (Green-zone safe site).

    Rule 4 - the *governing ceiling* is:

        overall_capacity = MIN(housing_cap, water_cap, healthcare_cap,
                               safe_land_cap, accessibility_cap)

    This is **enforced by a DB BEFORE-INSERT/UPDATE trigger** that overwrites
    whatever ``overall_capacity`` value an application supplied with the LEAST of
    the five sub-ceilings. The ORM exposes all five ceilings and the derived
    ceiling read-only; the allocation engine reads this single authoritative
    ``overall_capacity``.
    """

    __tablename__ = "destinations"

    destination_code: Mapped[str] = mapped_column(String(128), nullable=False, unique=True)
    name: Mapped[str] = mapped_column(Text, nullable=False)
    admin_unit_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("geo_admin_units.id", ondelete="RESTRICT"), nullable=False
    )

    geom: Mapped[object] = mapped_column(
        Geometry(geometry_type="POLYGON", srid=4326), nullable=False
    )
    centroid: Mapped[object] = mapped_column(
        Geometry(geometry_type="POINT", srid=4326), nullable=False
    )

    is_verified_site: Mapped[bool] = mapped_column(
        Boolean, nullable=False, default=False
    )

    # ----- five independently-measured ceilings (Rule 4)
    housing_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    water_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    healthcare_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    safe_land_cap: Mapped[int] = mapped_column(Integer, nullable=False)
    accessibility_cap: Mapped[int] = mapped_column(Integer, nullable=False)

    # ----- derived ceiling (written by database trigger; do not set manually)
    overall_capacity: Mapped[int] = mapped_column(Integer, nullable=False, default=0)

    # ----- destination quality scores used by the Destination Score formula
    safety_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    accessibility_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    infrastructure_score: Mapped[float | None] = mapped_column(Float, nullable=True)

    quality_confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE, nullable=False, default="confirmed"
    )

    # provenance (Rule 6)
    dataset_version: Mapped[str] = mapped_column(Text, nullable=False)
    risk_config_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )

    admin_unit: Mapped["GeoAdminUnit"] = relationship(  # noqa: F821
        back_populates="destinations"
    )

    __table_args__ = (
        CheckConstraint("housing_cap >= 0", name="ck_dest_housing_cap"),
        CheckConstraint("water_cap >= 0", name="ck_dest_water_cap"),
        CheckConstraint("healthcare_cap >= 0", name="ck_dest_healthcare_cap"),
        CheckConstraint("safe_land_cap >= 0", name="ck_dest_land_cap"),
        CheckConstraint("accessibility_cap >= 0", name="ck_dest_access_cap"),
        CheckConstraint("overall_capacity >= 0", name="ck_dest_overall_capacity"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Destination {self.destination_code} cap={self.overall_capacity}>"

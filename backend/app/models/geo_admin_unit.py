"""ORM model for the eligible pilot administrative geography."""

from __future__ import annotations

from sqlalchemy import Boolean, Index, String, Text
from sqlalchemy.dialects.postgresql import ARRAY
from sqlalchemy.orm import Mapped, mapped_column, relationship

from geoalchemy2 import Geometry

from app.core.enums import HazardType, StateCode
from app.db.base import Base, IntPKMixin
from app.models.enum_types import HAZARD_TYPE, STATE_CODE


class GeoAdminUnit(IntPKMixin, Base):
    """A district-sized administrative unit participating in a pilot geography.

    Maps to the ``geo_admin_units`` table. Boundaries are stored as
    ``MultiPolygon`` in geographic CRS EPSG:4326 for agnostic HTTP-based services
    and spatial indexing (PostGIS GIST).
    """

    __tablename__ = "geo_admin_units"

    unit_code: Mapped[str] = mapped_column(
        String(64), unique=True, nullable=False, index=True
    )
    state: Mapped[StateCode] = mapped_column(STATE_CODE, nullable=False)
    district: Mapped[str] = mapped_column(Text, nullable=False)
    terrain: Mapped[str] = mapped_column(Text, nullable=False)
    focus_hazards: Mapped[list[HazardType]] = mapped_column(
        ARRAY(HAZARD_TYPE),
        server_default="{}",
        nullable=False,
    )
    boundary: Mapped[object | None] = mapped_column(
        Geometry(geometry_type="MULTIPOLYGON", srid=4326), nullable=True
    )
    is_active: Mapped[bool] = mapped_column(Boolean, nullable=False, default=True)

    __table_args__ = (
        Index("idx_admin_boundary_gist", "boundary", postgresql_using="gist"),
    )

    habitations: Mapped[list["Habitation"]] = relationship(  # noqa: F821
        back_populates="admin_unit"
    )
    destinations: Mapped[list["Destination"]] = relationship(  # noqa: F821
        back_populates="admin_unit"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<GeoAdminUnit {self.unit_code} ({self.state.value})>"

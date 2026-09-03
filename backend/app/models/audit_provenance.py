"""ORM model for the provenance/audit log (Rule 6)."""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import JSON, BigInteger, DateTime, Text, func
from sqlalchemy.orm import Mapped, mapped_column

from app.db.base import Base, IntPKMixin


class AuditProvenance(IntPKMixin, Base):
    """A generic lineage event recording *who* changed *what* and under which
    version keys all four provenance pillars were bound.

    ``operation_context`` is a JSON object that typically carries scalar strings:

        {
          "dataset_version":   "...",
          "model_version":     "...",
          "scenario_version":  "...",
          "risk_config_version":"..."
        }

    Because every table composes the four version pillars, this single log is the
    cross-table audit trail used by governance and for answering “on which data,
    model, config and scenario did this number depend?”.
    """

    __tablename__ = "audit_provenance"

    occurred_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    actor: Mapped[str] = mapped_column(Text, nullable=False)
    action: Mapped[str] = mapped_column(Text, nullable=False)
    entity_table: Mapped[str] = mapped_column(Text, nullable=False)
    entity_id: Mapped[int | None] = mapped_column(BigInteger, nullable=True)
    operation_context: Mapped[dict | None] = mapped_column(JSON, nullable=True)
    diff: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    def __repr__(self) -> str:  # pragma: no cover
        return f"<Audit {self.actor} {self.action} on {self.entity_table}.{self.entity_id}>"

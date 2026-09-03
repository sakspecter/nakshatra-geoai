"""ORM models for the Decision Engine output (allocation/relocation plan) and its
human-in-the-loop workflow state machine (Rule 1).
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import (
    JSON,
    BigInteger,
    CheckConstraint,
    DateTime,
    Float,
    ForeignKey,
    Integer,
    Text,
    UniqueConstraint,
    func,
)
from sqlalchemy.orm import Mapped, mapped_column, relationship

from app.core.enums import ConstraintType, DataConfidence, WorkflowState
from app.db.base import Base, IntPKMixin
from app.models.enum_types import CONSTRAINT_TYPE, DATA_CONFIDENCE, WORKFLOW_STATE


class AllocationPlan(IntPKMixin, Base):
    """A consolidated relocation plan (may target baseline or a named scenario).

    ``scenario_id`` NULL means the plan targets current live baseline; non-NULL
    ties it to an immutable simulation. The ``status`` enum enforces that only a
    fully ``authorized`` plan may ever progress to ``executed`` (Human-in-the-Loop).
    """

    __tablename__ = "allocation_plans"

    scenario_id: Mapped[int | None] = mapped_column(
        BigInteger, ForeignKey("scenarios.id"), nullable=True
    )
    plan_version: Mapped[str] = mapped_column(Text, nullable=False)
    status: Mapped[WorkflowState] = mapped_column(
        WORKFLOW_STATE, nullable=False, default="draft"
    )
    risk_config_version: Mapped[str] = mapped_column(Text, nullable=False)
    created_by: Mapped[str] = mapped_column(Text, nullable=False)
    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True), nullable=False, server_default=func.now()
    )
    authorized_by: Mapped[str | None] = mapped_column(Text, nullable=True)
    authorized_at: Mapped[datetime | None] = mapped_column(
        DateTime(timezone=True), nullable=True
    )
    summary_json: Mapped[dict | None] = mapped_column(JSON, nullable=True)

    entries: Mapped[list["AllocationEntry"]] = relationship(
        back_populates="plan", cascade="all, delete-orphan"
    )

    def __repr__(self) -> str:  # pragma: no cover
        return f"<AllocationPlan #{self.id} {self.plan_version} [{self.status.value}]>"


class AllocationEntry(IntPKMixin, Base):
    """One source habitation matched to one candidate destination.

    Invariant across a batch: sum of ``allocated_persons`` per destination must
    never exceed that destination's DB-authoritative ``overall_capacity`` ceiling.
    The bottleneck field records which specific constraint bound the assignment so
    a human can inspect the exact tightest constraint (Rule 4 transparency).
    """

    __tablename__ = "allocation_entries"

    plan_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("allocation_plans.id", ondelete="CASCADE"), nullable=False
    )
    habitation_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("habitations.id", ondelete="RESTRICT"), nullable=False
    )
    destination_id: Mapped[int] = mapped_column(
        BigInteger, ForeignKey("destinations.id", ondelete="RESTRICT"), nullable=False
    )
    allocated_persons: Mapped[int] = mapped_column(Integer, nullable=False)
    destination_score: Mapped[float | None] = mapped_column(Float, nullable=True)
    per_constraint_bottleneck: Mapped[ConstraintType | None] = mapped_column(
        CONSTRAINT_TYPE, nullable=True
    )
    capacity_at_plan: Mapped[int | None] = mapped_column(Integer, nullable=True)
    confidence: Mapped[DataConfidence] = mapped_column(
        DATA_CONFIDENCE, nullable=False, default="confirmed"
    )
    plan_version: Mapped[str] = mapped_column(Text, nullable=False)

    plan: Mapped["AllocationPlan"] = relationship(back_populates="entries")

    __table_args__ = (
        CheckConstraint("allocated_persons >= 0", name="ck_alloc_nonneg"),
        UniqueConstraint("plan_id", "habitation_id", name="uq_alloc_hab_plan"),
    )

    def __repr__(self) -> str:  # pragma: no cover
        return (
            f"<Alloc hab={self.habitation_id} -> dest={self.destination_id} "
            f"persons={self.allocated_persons}>"
        )

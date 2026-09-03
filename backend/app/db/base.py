"""Declarative base for ALL ORM models.

``Base`` is defined here (rather than in ``app/models/base.py``) so that Alembic
autogenerate and any registration helper can import a single object that already
knows every mapped class once the models package is imported.
"""

from __future__ import annotations

from datetime import datetime

from sqlalchemy import DateTime, Identity, func
from sqlalchemy.orm import DeclarativeBase, Mapped, mapped_column


class Base(DeclarativeBase):
    """Typed declarative base shared by every SQLAlchemy 2.0 ORM model."""


class IntPKMixin:
    """Conventional BIGINT surrogate primary key for non-join core tables.

    Mixin yields an autoincrementing ``id: Mapped[int]`` column so the whole
    codebase can rely on a stable, simple primary-key type.
    """

    id: Mapped[int] = mapped_column(
        Identity(always=False),
        primary_key=True,
        autoincrement=True,
    )


class TimestampMixin:
    """Adds auditable ``created_at``/``updated_at`` timestamps (utc-aware).

    Reused on every writable table to align with the schema's temporal-capable
    design and Rule 6 provenance philosophy.
    """

    created_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        nullable=False,
    )
    updated_at: Mapped[datetime] = mapped_column(
        DateTime(timezone=True),
        server_default=func.now(),
        onupdate=func.now(),
        nullable=False,
    )

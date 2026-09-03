"""Shared API dependencies (DI glue + DB async session re-export)."""

from __future__ import annotations

from sqlalchemy.ext.asyncio import AsyncSession

from app.db.session import get_db_session

__all__ = ["get_db_session", "AsyncSession"]

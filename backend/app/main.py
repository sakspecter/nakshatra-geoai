"""FastAPI application entrypoint for Project Nakshatra backend."""

from __future__ import annotations

from contextlib import asynccontextmanager
from typing import AsyncIterator

from fastapi import FastAPI
from fastapi.middleware.cors import CORSMiddleware

from app.core.config import settings
from app.db.session import close_engine, engine
from app.api.v1.router import api_router


@asynccontextmanager
async def lifespan(app: FastAPI) -> AsyncIterator[None]:
    """Application lifespan: keep the engine alive and dispose on shutdown."""
    # A lightweight ping is optional here because most deployments of module 1 do
    # not require an eager connect (models/schemas are DB-agnostic at import).
    yield
    await close_engine()


app = FastAPI(
    title=settings.PROJECT_NAME,
    description=(
        "GeoAI Disaster Decision Support System. Advisory-only recommendations; "
        "relocation orders remain a human-in-the-loop decision."
    ),
    version=settings.VERSION,
    lifespan=lifespan,
)

# CORS for the Next.js command dashboard.
app.add_middleware(
    CORSMiddleware,
    allow_origins=settings.BACKEND_CORS_ORIGINS,
    allow_credentials=True,
    allow_methods=["*"],
    allow_headers=["*"],
)

# Module 6 command-dashboard API mounted under the version prefix.
app.include_router(api_router, prefix=settings.API_V1_PREFIX)


@app.get("/health", tags=["system"])
async def health_check() -> dict[str, str]:
    """Liveness probe."""
    return {
        "status": "ok",
        "service": settings.PROJECT_NAME,
        "version": settings.VERSION,
        "engine_connected": engine is not None,
    }

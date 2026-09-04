"""Aggregate v1 router - includes each feature sub-router."""

from __future__ import annotations

from fastapi import APIRouter

from app.api.v1.admin import router as admin_router
from app.api.v1.habitation_detail import router as habitation_router
from app.api.v1.map_tiles import router as map_router
from app.api.v1.overview import router as overview_router
from app.api.v1.relocation import router as relocation_router
from app.api.v1.scenario import router as scenario_router
from app.api.v1.spatial import router as spatial_router


api_router = APIRouter()

# deterministic feature modules
api_router.include_router(overview_router)
api_router.include_router(map_router)
api_router.include_router(habitation_router)
api_router.include_router(relocation_router)
api_router.include_router(scenario_router)

# nationwide spatial catalog + zero-code admin ingestion
api_router.include_router(spatial_router)
api_router.include_router(admin_router)

__all__ = ["api_router"]

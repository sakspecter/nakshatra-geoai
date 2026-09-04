"""Admin endpoints - zero-code Spatial Ingestion Engine.

``POST /admin/ingest`` accepts form-data (state_name, district_name, optional
terrain, file) and runs the full ingestion pipeline:

    Uploading -> Normalizing CRS -> Spatial Joins -> Running ML Inference ->
    Computing Capacity Limits -> Complete

The endpoint is fully functional without a live database (results are cached in
the in-process registry and self-heal into PostGIS when a session is wired).
"""

from __future__ import annotations

import json
from pathlib import Path
from typing import List, Optional

from fastapi import (
    APIRouter,
    Depends,
    File,
    Form,
    HTTPException,
    UploadFile,
)
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.services.ingestion import PIPELINE_STAGES, registered_districts, run_ingestion_pipeline

router = APIRouter(tags=["admin"])

_ALLOWED_SUFFIXES = (".json", ".geojson", ".zip", ".gpkg")


class IngestResult(BaseModel):
    status: str
    state_code: str
    state_name: str
    district_name: str
    district_code: str
    terrain: str
    habitations_loaded: int
    zone_breakdown: dict = Field(default_factory=dict)
    capacity_limiter: Optional[str] = None
    bbox: List[float] = Field(default_factory=list)
    dataset_version: str
    model_version: str
    pipeline_stages: List[str] = Field(default_factory=list)
    produced_at: str = ""


class IngestedDistrictSummary(BaseModel):
    district_code: str
    district_name: str
    state_code: str
    state_name: str
    habitation_count: int
    bbox: List[float] = Field(default_factory=list)
    dataset_version: str
    loaded_at: str


@router.post(
    "/admin/ingest",
    response_model=IngestResult,
    summary="Ingest raw GIS boundaries for any Indian district",
)
async def ingest_district(
    state_name: str = Form(..., description="Human-readable state name, e.g. 'Sikkim'"),
    district_name: str = Form(..., description="District name, e.g. 'Namchi'"),
    terrain: Optional[str] = Form(default=None, description="Optional terrain label"),
    file: UploadFile = File(..., description="GeoJSON / JSON / Zipped shapefile / Geopackage"),
    _session: AsyncSession = Depends(get_db_session),
) -> IngestResult:
    """Run the spatial ingestion pipeline over the uploaded vector file."""
    filename = (file.filename or "upload.geojson").lower()
    suffix = _safe_suffix(filename)
    if suffix not in _ALLOWED_SUFFIXES:
        raise HTTPException(
            status_code=400,
            detail=(
                f"Unsupported file type '{suffix}'. Expected one of: "
                f"{', '.join(_ALLOWED_SUFFIXES)}"
            ),
        )
    if not state_name.strip() or not district_name.strip():
        raise HTTPException(status_code=422, detail="state_name and district_name are required.")

    raw = await file.read()
    if not raw:
        raise HTTPException(status_code=400, detail="Uploaded file is empty.")

    try:
        result = run_ingestion_pipeline(
            state_name=state_name.strip(),
            district_name=district_name.strip(),
            raw=raw,
            filename=filename,
            terrain=terrain,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover - defensive 500 with context
        raise HTTPException(
            status_code=500, detail=f"Ingestion pipeline failed: {exc}"
        ) from exc
    return IngestResult(**result)


@router.post(
    "/admin/ingest-auto",
    response_model=IngestResult,
    summary="Auto-ingest a district: fetch its boundary from GADM, no file upload",
)
async def ingest_district_auto(
    state_name: str = Form(..., description="Human-readable state name, e.g. 'Sikkim'"),
    district_name: str = Form(..., description="District name, e.g. 'Namchi'"),
    n_settlements: int = Form(default=15, ge=1, le=200),
    with_villages: bool = Form(default=False),
    terrain: Optional[str] = Form(default=None),
    _session: AsyncSession = Depends(get_db_session),
) -> IngestResult:
    """Quick Ingest: downloads the district polygon from GADM, generates
    deterministic settlements, optionally overlays OSM villages, and runs the
    pipeline — no file required."""
    try:
        from app.services.auto_ingest import auto_ingest_district

        result = auto_ingest_district(
            state_name=state_name.strip(),
            district_name=district_name.strip(),
            n_settlements=n_settlements,
            with_villages=with_villages,
            terrain=terrain,
        )
    except ValueError as exc:
        raise HTTPException(status_code=422, detail=str(exc)) from exc
    except Exception as exc:  # pragma: no cover
        raise HTTPException(
            status_code=500, detail=f"Auto-ingest failed: {exc}"
        ) from exc
    return IngestResult(**result)


@router.get(
    "/admin/geo-options",
    summary="List states and districts available for auto-ingest (instant, static catalog)",
)
async def geo_options(
    state: Optional[str] = None,
) -> dict:
    """Serve the bundled state->district catalog (9 KB static JSON).

    Instant response - no GADM download. The full GADM boundary file is only
    fetched lazily when an actual auto-ingest runs (and then cached)."""
    catalog_path = (
        Path(__file__).resolve().parent.parent.parent
        / "data" / "india_districts.json"
    )
    if not catalog_path.exists():
        raise HTTPException(
            status_code=500,
            detail="Static district catalog missing. Run scripts/gen_catalog.py once.",
        )

    catalog: dict = json.loads(catalog_path.read_text(encoding="utf-8"))

    if state:
        # case-insensitive + alias-tolerant lookup
        wanted = state.strip().lower()
        matched = next(
            (k for k in catalog if k.lower() == wanted),
            None,
        )
        if matched is None:
            # try substring
            matched = next(
                (k for k in catalog if wanted in k.lower() or k.lower() in wanted),
                None,
            )
        if matched is None:
            return {"state": state, "districts": []}
        return {"state": matched, "districts": catalog[matched]}

    return {"states": sorted(catalog.keys())}


@router.get(
    "/admin/ingested",
    response_model=List[IngestedDistrictSummary],
    summary="List currently ingested districts in this process",
)
async def get_ingested(
    _session: AsyncSession = Depends(get_db_session),
) -> List[IngestedDistrictSummary]:
    """Registry-backed listing for verification / operational transparency."""
    return [IngestedDistrictSummary(**r) for r in registered_districts()]


def _safe_suffix(filename: str) -> str:
    """Lower-cased extension incl. leading dot; missing extension -> '.geojson'."""
    if "." not in filename:
        return ".geojson"
    return "." + filename.rsplit(".", 1)[-1].lower()
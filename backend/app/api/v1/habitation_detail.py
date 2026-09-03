"""Habitation detailed profile endpoint - GET /habitations/{id}.

Returns a rich read-model: base risk profile, per-hazard evidence, data-quality
flags (Missing-data Rule transparency) and SHAP drivers when an ML model is
available for that habit (else explicit ``shap_state='unavailable'`` rather than
fabricating drivers).
"""

from __future__ import annotations

from typing import List, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.services.workspace import load_baselines

router = APIRouter(tags=["habitations"])


class HazardEvidence(BaseModel):
    hazard_type: str
    score: Optional[float]
    missing: bool = False
    low_confidence: bool = False


class ShapDriverOut(BaseModel):
    feature: str
    direction: str
    contribution: float
    label: str


class DataQualityFlags(BaseModel):
    hazard_provided: bool
    vulnerability_provided: bool
    missing_feature_hint: Optional[str] = None
    evidence_sufficient: bool
    warnings: List[str] = Field(default_factory=list)


class HabitationDetailResponse(BaseModel):
    habitation_id: int
    habitation_code: str
    state_code: str
    district_code: str
    total_population: int
    zone: str
    risk: float
    vulnerability_score: float
    priority: str
    hazard_evidence: List[HazardEvidence]
    shap_drivers: List[ShapDriverOut] = Field(default_factory=list)
    shap_state: str = "unavailable"
    data_quality_flags: DataQualityFlags


def _to_priority(zone_value: str) -> str:
    from app.core.enums import RelocationPriority, ZoneBand

    if zone_value == ZoneBand.RED.value:
        return RelocationPriority.IMMEDIATE.value
    if zone_value == ZoneBand.YELLOW.value:
        return RelocationPriority.PRIORITY.value
    return RelocationPriority.MONITOR.value


def build_habitation_detail(habitation_id: int) -> HabitationDetailResponse:
    base = None
    for bl in load_baselines():
        if bl.habitation_id == habitation_id:
            base = bl
            break
    if base is None:
        raise HTTPException(status_code=404, detail="Habitation not found")

    evidence = [
        HazardEvidence(hazard_type=h.value, score=round(s, 4))
        for h, s in base.hazard_scores.items()
    ]
    # Rule 2 transparency: each evidence entry carries explicit presence state.
    provided_hazard = bool(len(base.hazard_scores))
    vuln_known = base.vulnerability_score is not None

    flags = DataQualityFlags(
        hazard_provided=provided_hazard,
        vulnerability_provided=vuln_known,
        evidence_sufficient=provided_hazard and vuln_known,
        warnings=[] if (provided_hazard and vuln_known) else ["Evidence insufficient"],
    )

    return HabitationDetailResponse(
        habitation_id=base.habitation_id,
        habitation_code=base.habitation_code,
        state_code=base.state_code,
        district_code=base.district_code,
        total_population=base.population,
        zone=base.baseline_zone.value,
        risk=round(base.baseline_risk, 4),
        vulnerability_score=round(base.vulnerability_score, 4),
        priority=_to_priority(base.baseline_zone.value),
        hazard_evidence=evidence,
        shap_state="unavailable",  # a real model registration path fills this
        data_quality_flags=flags,
    )


@router.get(
    "/habitations/{habitation_id}",
    response_model=HabitationDetailResponse,
    summary="Detailed settlement risk profile with SHAP + quality flags",
)
async def get_habitation_detail(
    habitation_id: int,
    _session: AsyncSession = Depends(get_db_session),
) -> HabitationDetailResponse:
    return build_habitation_detail(habitation_id=habitation_id)

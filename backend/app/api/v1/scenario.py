"""Scenario simulator endpoint - POST /scenario/simulate.

Takes explicit what-if triggers (e.g. +25% cloudburst rainfall in Chamoli; flash
flood stress in Dhemaji), runs them against an immutable deep-copied baseline,
and returns a side-by-side baseline_risk/scenario_risk + red-zone delta report.
"""

from __future__ import annotations

from datetime import datetime, timezone
from typing import List, Literal, Optional

from fastapi import APIRouter, Depends, HTTPException
from pydantic import BaseModel, Field
from sqlalchemy.ext.asyncio import AsyncSession

from app.api.deps import get_db_session
from app.core.enums import HazardType
from app.services.scenario import (
    ScenarioTrigger,
    apply_triggers,
)
from app.services.workspace import load_baselines

router = APIRouter(tags=["scenario"])


class TriggerIn(BaseModel):
    kind: Literal["rainfall_pct", "hazard_multiplier"] = "rainfall_pct"
    hazard_types: List[HazardType] = Field(
        default_factory=lambda: [HazardType.CLOUDBURST]
    )
    factor: float = Field(default=1.0, ge=0.0, description="1.25 => +25 %")
    district: Optional[str] = None
    state: Optional[str] = None
    scope_all: bool = False


class ScenarioSimulateRequest(BaseModel):
    name: str = Field(min_length=1, description="Human-readable scenario name")
    triggers: List[TriggerIn] = Field(min_length=1)
    baseline_dataset_version: str = "seed-baseline"
    scenario_version: Optional[str] = Field(
        default=None,
        description="Explicit model/scenario config version (Rule 6)",
    )


class SimulatedRowOut(BaseModel):
    habitation_id: int
    baseline_risk: float
    scenario_risk: float
    risk_delta: float
    baseline_zone: str
    scenario_zone: str
    zones_changed: bool
    habitation_name: str = ""
    habitation_code: str = ""
    state_code: str = ""
    district_code: str = ""


class HabitationDeltaRow(BaseModel):
    """Itemized per-habitation risk delta surfaced as an explicit row-set.

    Fixes the dashboard warning where a run returned only aggregate KPIs. The
    simulator now always materializes one row per baseline habitation with the
    pre/post risk scores and a human-readable delta category."""

    habitation_id: int
    habitation_name: str = ""
    habitation_code: str = ""
    state_code: str = ""
    district_code: str = ""
    pre_risk_score: float
    post_risk_score: float
    risk_delta: float
    delta_category: Literal["Improved", "Degraded", "Unchanged"]


class ScenarioSimulateResponse(BaseModel):
    scenario_id: str
    name: str
    produced_at: datetime = Field(default_factory=lambda: datetime.now(timezone.utc))
    scenario_version: str
    baseline_dataset_version: str
    triggered_on: List[dict] = Field(default_factory=list)
    side_by_side: dict = Field(default_factory=dict)          # baseline vs scenario counts
    delta: dict = Field(default_factory=dict)                 # explicit metric deltas
    rows: List[SimulatedRowOut] = Field(default_factory=list)
    # explicit row-level breakdown (itemized habitation deltas)
    habitation_deltas: List[HabitationDeltaRow] = Field(default_factory=list)
    baseline_untouched: bool = True
    note: str = "Baseline ground-truth is immutable; simulation runs only on deep copies."


def _to_trigger(t: TriggerIn) -> ScenarioTrigger:
    return ScenarioTrigger(
        kind=t.kind,
        factor=t.factor,
        hazard_types=tuple(t.hazard_types),
        district_code=t.district,
        state_code=t.state,
        scope_all=t.scope_all,
    )


def _run_simulation(
    name: str,
    triggers: List[TriggerIn],
    baseline_dataset_version: str = "seed-baseline",
    scenario_version: str = "scenario.v1",
) -> ScenarioSimulateResponse:
    base_rows = load_baselines()

    result = apply_triggers(
        baselines=base_rows,
        triggers=[_to_trigger(t) for t in triggers],
        scenario_id=f"scn-{datetime.now(timezone.utc).strftime('%Y%m%d-%H%M%S')}",
        scenario_version=scenario_version,
        baseline_dataset_version=baseline_dataset_version,
    )

    summary = result.summarize()
    side_by_side = {
        "baseline_red_zones": summary["baseline_red_zones"],
        "scenario_red_zones": summary["scenario_red_zones"],
        "baseline_green": sum(
            1 for r in result.rows if r.baseline.baseline_zone.value == "green"
        ),
        "scenario_green": sum(1 for r in result.rows if r.scenario_zone.value == "green"),
    }
    delta = {
        "delta_red_zones": summary["delta_red_zones"],
        "new_red_zones": summary["new_red_zones"],
        "changed_rows": summary["changed_rows"],
        "mean_baseline_risk": summary["mean_baseline_risk"],
        "mean_scenario_risk": summary["mean_scenario_risk"],
        "pop_baseline_red_approx": summary["pop_baseline_red_approx"],
        "pop_scenario_red_approx": summary["pop_scenario_red_approx"],
    }
    rows_out = [
        SimulatedRowOut(
            habitation_id=s.habitation_id,
            baseline_risk=round(s.baseline.baseline_risk, 4),
            scenario_risk=round(s.scenario_risk, 4),
            risk_delta=round(s.scenario_risk - s.baseline.baseline_risk, 4),
            baseline_zone=s.baseline.baseline_zone.value,
            scenario_zone=s.scenario_zone.value,
            zones_changed=s.baseline.baseline_zone != s.scenario_zone,
            habitation_name=s.baseline.name,
            habitation_code=s.baseline.habitation_code,
            state_code=s.baseline.state_code,
            district_code=s.baseline.district_code,
        )
        for s in result.rows
    ]
    delta_rows = [
        HabitationDeltaRow(
            habitation_id=s.habitation_id,
            habitation_name=s.baseline.name,
            habitation_code=s.baseline.habitation_code,
            state_code=s.baseline.state_code,
            district_code=s.baseline.district_code,
            pre_risk_score=round(s.baseline.baseline_risk, 4),
            post_risk_score=round(s.scenario_risk, 4),
            risk_delta=round(s.scenario_risk - s.baseline.baseline_risk, 4),
            delta_category=_delta_category(
                s.scenario_risk - s.baseline.baseline_risk
            ),
        )
        for s in result.rows
    ]
    triggered_on = [
        {
            "kind": t.kind,
            "factor": t.factor,
            "hazard_types": [h.value for h in t.hazard_types],
            "district": t.district,
            "state": t.state,
            "scope_all": t.scope_all,
        }
        for t in triggers
    ]
    return ScenarioSimulateResponse(
        scenario_id=result.scenario_id,
        name=name,
        scenario_version=scenario_version,
        baseline_dataset_version=baseline_dataset_version,
        triggered_on=triggered_on,
        side_by_side=side_by_side,
        delta=delta,
        rows=rows_out,
        habitation_deltas=delta_rows,
        baseline_untouched=True,
    )


def _delta_category(delta: float) -> str:
    """Classify an itemized risk delta for the per-habitation row-set."""
    if delta > 0.0:
        return "Degraded"
    if delta < 0.0:
        return "Improved"
    return "Unchanged"


@router.post(
    "/scenario/simulate",
    response_model=ScenarioSimulateResponse,
    summary="Run a what-if scenario with immutable baseline copies",
)
async def simulate(
    body: ScenarioSimulateRequest,
    _session: AsyncSession = Depends(get_db_session),
) -> ScenarioSimulateResponse:
    return _run_simulation(
        name=body.name,
        triggers=body.triggers,
        baseline_dataset_version=body.baseline_dataset_version,
        scenario_version=body.scenario_version or "scenario.v1",
    )

"""Module 5 - Scenario Simulation Engine (Rule 5 immutability + Rule 6 versioning).

SUMMARY
-------
* Baseline data passed to the simulator is **never mutated** (ground-truth keeps
  its identity untouched). Every baseline row is deep-copied into a private
  namespace before triggers are applied.
* A *trigger* is an explicit adjustment to one physical driver for an optional
  spatial scope (state, district, or element set). Triggers alter only the copy.
* The result is a side-by-side delta report:
    baseline_risk vs scenario_risk,
    baseline_red_zones vs scenario_red_zones,
    plus per-row band/risk deltas and overall metrics.

Driven by immutable ``frozen=True`` state so callers cannot trip up the copy rule.
"""

from __future__ import annotations

import copy
from dataclasses import dataclass, field
from typing import Iterable, Literal, Optional

from app.core.enums import HazardType, ZoneBand

# The four hazard types our recompute layer supports for a per-habitation row.
_SUPPORTED = (
    HazardType.FLOOD,
    HazardType.LANDSLIDE,
    HazardType.COASTAL_EROSION,
    HazardType.CLOUDBURST,
)


# ---------------------------------------------------------------------------
# Domain state
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HabitationBaseline:
    """An immutable, survey-grade row for one habitation as of the baseline
    dataset (from the DB layer). Building a scenario copy deep-copies this."""

    habitation_id: int
    habitation_code: str
    state_code: str
    district_code: str
    hazard_scores: dict[HazardType, float]       # measured scores
    vulnerability_score: float
    population: int
    baseline_risk: float
    baseline_zone: ZoneBand
    name: str = ""                               # human-readable settlement name


@dataclass(frozen=True)
class ScenarioTrigger:
    """A what-if adjustment to a physical driver.

    ``kind``:
        rainfall_pct   -> multiply CLOUDBURST (and optionally FLOOD) by a % lift.
        hazard_multiplier -> multiply the chosen ``hazard_types`` by ``factor``
                             (e.g. 1.25 for +25%).
    ``scope``:
        {"district_code": "...", "state_code":"...", "all": true}
    """

    kind: Literal["rainfall_pct", "hazard_multiplier"]
    factor: float = 1.0                       # 1.25 == +25%
    hazard_types: tuple[HazardType, ...] = (HazardType.CLOUDBURST,)
    district_code: Optional[str] = None       # apply to a specific district
    state_code: Optional[str] = None          # apply to a specific state
    scope_all: bool = False                   # apply everywhere

    def in_scope(self, row: HabitationBaseline) -> bool:
        if self.scope_all:
            return True
        if self.district_code and row.district_code == self.district_code:
            return True
        if self.state_code and row.state_code == self.state_code:
            return True
        return False


# ---------------------------------------------------------------------------
# scenario results + triggers
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ScenarioHazards:
    hazard: dict[HazardType, float]
    vuln: float
    population: int


def recompute_band(risk: float, hazard: float, vuln: float) -> ZoneBand:
    """Zone thresholds mirroring the documented deterministic Risk Engine:"""
    if risk >= 0.60 or (hazard >= 0.70 and vuln >= 0.65):
        return ZoneBand.RED
    if risk < 0.20:
        # treat low risk only when data clearly supports it
        return ZoneBand.GREEN
    return ZoneBand.YELLOW


def safe_risk(hazard: float, vuln: float) -> float:
    return max(0.0, min(1.0, hazard * vuln))


# ---------------------------------------------------------------------------
# The simulator
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class SimulatedHabitation:
    habitation_id: int
    baseline: HabitationBaseline
    scenario_hazard: dict[HazardType, float]
    scenario_risk: float
    scenario_zone: ZoneBand

    def to_delta_dict(self) -> dict:
        return {
            "habitation_id": self.habitation_id,
            "habitation_name": self.baseline.name,
            "habitation_code": self.baseline.habitation_code,
            "state_code": self.baseline.state_code,
            "district_code": self.baseline.district_code,
            "baseline_risk": round(self.baseline.baseline_risk, 4),
            "scenario_risk": round(self.scenario_risk, 4),
            "risk_delta": round(self.scenario_risk - self.baseline.baseline_risk, 4),
            "baseline_zone": self.baseline.baseline_zone.value,
            "scenario_zone": self.scenario_zone.value,
            "zones_changed": self.baseline.baseline_zone != self.scenario_zone,
        }


@dataclass(frozen=True)
class ScenarioComparison:
    """Side-by-side comparison over an immutable copy of the baseline."""

    rows: list[SimulatedHabitation]
    scenario_id: str
    scenario_version: str
    baseline_dataset_version: str
    metrics: dict = field(default_factory=dict)

    # shared pointer aggregate metrics
    @property
    def baseline_red(self) -> int:
        return sum(1 for r in self.rows if r.baseline.baseline_zone is ZoneBand.RED)

    @property
    def scenario_red(self) -> int:
        return sum(1 for r in self.rows if r.scenario_zone is ZoneBand.RED)

    @property
    def new_red(self) -> int:
        return sum(
            1 for r in self.rows
            if r.baseline.baseline_zone is not ZoneBand.RED and r.scenario_zone is ZoneBand.RED
        )

    def summarize(self) -> dict:
        # aggregate vulnerable-population risk headline uses midpoint estimates
        return {
            "baseline_red_zones": self.baseline_red,
            "scenario_red_zones": self.scenario_red,
            "new_red_zones": self.new_red,
            "delta_red_zones": self.scenario_red - self.baseline_red,
            "mean_baseline_risk": round(
                sum(r.baseline.baseline_risk for r in self.rows) / max(len(self.rows), 1), 4
            ),
            "mean_scenario_risk": round(
                sum(r.scenario_risk for r in self.rows) / max(len(self.rows), 1), 4
            ),
            "pop_baseline_red_approx": sum(
                r.baseline.population for r in self.rows
                if r.baseline.baseline_zone is ZoneBand.RED
            ),
            "pop_scenario_red_approx": sum(
                r.baseline.population
                for r in self.rows
                if r.scenario_zone is ZoneBand.RED
            ),
            "changed_rows": sum(1 for r in self.rows if
                                r.scenario_zone != r.baseline.baseline_zone),
        }


def _clone_baselines(baselines: Iterable[HabitationBaseline]) -> list[HabitationBaseline]:
    """Deep copies of baseline records into the scenario namespace (Rule 5)."""
    return [copy.deepcopy(row) for row in baselines]


def apply_triggers(
    baselines: list[HabitationBaseline],
    triggers: list[ScenarioTrigger],
    scenario_id: str,
    scenario_version: str,
    baseline_dataset_version: str,
) -> ScenarioComparison:
    """Run what-if triggers on deep copies.

    Baseline rows are deep-copied into a private workspace before any arithmetic;
    the caller's ground-truth records are NEVER mutated (Rule 5). Each simulated
    row carries a read-only reference to its pristine baseline only for diffing.
    """
    # Pristine baseline map (never written to) for display / comparisons.
    original_by_id = {row.habitation_id: row for row in baselines}

    # Private, mutation-safe workspace (deep copies):
    working = _clone_baselines(baselines)

    simulated: list[SimulatedHabitation] = []
    for row in working:
        hazard_scen: dict[HazardType, float] = copy.deepcopy(row.hazard_scores)
        for trig in triggers:
            if not trig.in_scope(row):
                continue
            for hz in trig.hazard_types:
                if hz not in hazard_scen:
                    continue
                new_val: float
                if trig.kind == "rainfall_pct" or trig.kind == "hazard_multiplier":
                    new_val = hazard_scen[hz] * trig.factor
                else:  # pragma: no cover - Literal guard
                    new_val = hazard_scen[hz]
                hazard_scen[hz] = max(0.0, min(1.0, new_val))

        # Use the composite mean of the four measured scores as a conservative
        # hazard driver consistent with the deterministic risk engine usage.
        comp_hazard = (
            sum(v for v in hazard_scen.values()) / max(len(hazard_scen), 1)
            if hazard_scen
            else 0.0
        )
        scen_risk = safe_risk(comp_hazard, row.vulnerability_score)
        scen_zone = recompute_band(scen_risk, comp_hazard, row.vulnerability_score)

        simulated.append(
            SimulatedHabitation(
                habitation_id=row.habitation_id,
                baseline=original_by_id.get(row.habitation_id, row),
                scenario_hazard=hazard_scen,
                scenario_risk=scen_risk,
                scenario_zone=scen_zone,
            )
        )

    skeleton = ScenarioComparison(
        rows=simulated,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        baseline_dataset_version=baseline_dataset_version,
    )
    return ScenarioComparison(
        rows=simulated,
        scenario_id=scenario_id,
        scenario_version=scenario_version,
        baseline_dataset_version=baseline_dataset_version,
        metrics=skeleton.summarize(),
    )

"""Module 5 unit tests - capacity, relocation, scenario simulation."""

from __future__ import annotations

import copy

import pytest

from app.core.enums import (
    ConstraintType,
    HazardType,
    RelocationPriority,
    ZoneBand,
)
from app.services.capacity import (
    DestinationCapabilities,
    compute_capacity,
    overall_capacity_for,
)
from app.services.relocation import (
    DestinationCandidate,
    RelocationDemand,
    allocate,
    rank_candidates,
)
from app.services.scenario import (
    HabitationBaseline,
    ScenarioTrigger,
    apply_triggers,
    recompute_band,
    safe_risk,
)


def _caps():
    return DestinationCapabilities(
        destination_code="UK-GRN-1",
        housing_cap=500,
        water_cap=250,
        healthcare_cap=300,
        safe_land_cap=400,
        accessibility_cap=900,
    )


class TestCapacityRule4:
    def test_overall_is_min(self):
        c = _caps()
        assert overall_capacity_for(c) == 250
        assert compute_capacity(c, 0).limiting_constraint is ConstraintType.WATER

    def test_available_is_floor_zero(self):
        c = _caps()
        res = compute_capacity(c, current_population=260)
        assert res.overall_capacity == 250
        assert res.available_capacity == 0
        assert res.population_over_ceiling is True

    def test_available_decrement(self):
        res = compute_capacity(_caps(), current_population=40)
        assert res.available_capacity == 210

    def test_limiter_label_human(self):
        res = compute_capacity(_caps(), current_population=10)
        assert res.limiting_label == "Water Supply"


class TestRelocationMCDA:
    _C = DestinationCandidate(
        destination_id=1, destination_code="D1", state_code="UK",
        district_code="CHAMOLI", safety=0.9, access=0.8, capacity=0.6,
        infra=0.7, distance_km=12.0,
    )
    _D = RelocationDemand(
        habitation_id=10, habitation_code="S10", state_code="UK",
        district_code="CHAMOLI", population_at_risk=120,
        priority=RelocationPriority.IMMEDIATE,
    )

    def test_rank_same_state_site_kept(self):
        ranks = rank_candidates(
            self._D,
            [self._C, DestinationCandidate(
                destination_id=2, destination_code="D2", state_code="AS",
                district_code="DHEMAJI", safety=1.0, access=1.0, capacity=1.0,
                infra=1.0, distance_km=5.0)],
        )
        # cross-state D2 excluded by default => only D1 present
        assert len(ranks) == 1
        assert ranks[0].destination.destination_id == 1


class TestAllocationNoOverflow:
    def test_split_across_sites_no_overflow(self):
        demand = RelocationDemand(
            habitation_id=1, habitation_code="H1", state_code="UK",
            district_code="CHAMOLI", population_at_risk=300,
            priority=RelocationPriority.IMMEDIATE,
        )
        c1 = DestinationCandidate(
            destination_id=1, destination_code="G1", state_code="UK",
            district_code="CHAMOLI", safety=0.9, access=0.8, capacity=0.5,
            infra=0.6, distance_km=3.0)
        c2 = DestinationCandidate(
            destination_id=2, destination_code="G2", state_code="UK",
            district_code="CHAMOLI", safety=0.7, access=0.5, capacity=0.5,
            infra=0.6, distance_km=4.0)

        from app.services.capacity import DestinationCapabilities, compute_capacity
        cap1 = compute_capacity(DestinationCapabilities("G1", 180, 180, 180, 180, 180), 0)
        cap2 = compute_capacity(DestinationCapabilities("G2", 200, 200, 200, 200, 200), 0)
        summary = allocate(
            [demand],
            capacities={1: cap1, 2: cap2},
            candidates=[c1, c2],
        )
        served = sum(r.persons_allocated for r in summary.records)
        # G1 holds 180 then G2 tops up remaining 120 => two chunks
        assert summary.population_served == 300
        assert served == 300
        assert summary.split_settlements == 1

    def test_no_allocation_onto_full_site(self):
        demand = RelocationDemand(
            habitation_id=9, habitation_code="S9", state_code="UK",
            district_code="CHAMOLI", population_at_risk=60,
            priority=RelocationPriority.PRIORITY)
        from app.services.capacity import DestinationCapabilities
        cap = compute_capacity(DestinationCapabilities("F", 100, 100, 100, 100, 100), 100)
        site = DestinationCandidate(
            destination_id=7, destination_code="FULL", state_code="UK",
            district_code="CHAMOLI", safety=1.0, access=1.0, capacity=0.2,
            infra=0.5, distance_km=1.0)
        summary = allocate([demand], capacities={7: cap}, candidates=[site])
        assert summary.population_served == 0
        assert summary.population_unserved == 60


class TestScenarioRule5:
    def _base(self):
        return [
            HabitationBaseline(
                habitation_id=1, habitation_code="H1", state_code="UK",
                district_code="CHAMOLI",
                hazard_scores={
                    HazardType.FLOOD: 0.3,
                    HazardType.CLOUDBURST: 0.2,
                    HazardType.LANDSLIDE: 0.1,
                    HazardType.COASTAL_EROSION: 0.0,
                },
                vulnerability_score=0.7, population=420,
                baseline_risk=safe_risk(0.15, 0.7),
                baseline_zone=ZoneBand.GREEN,
            ),
            HabitationBaseline(
                habitation_id=2, habitation_code="H2", state_code="UK",
                district_code="PITHORAGARH",
                hazard_scores={
                    HazardType.FLOOD: 0.8,
                    HazardType.LANDSLIDE: 0.4,
                    HazardType.CLOUDBURST: 0.5,
                    HazardType.COASTAL_EROSION: 0.0,
                },
                vulnerability_score=0.8, population=300,
                baseline_risk=safe_risk(0.5, 0.8),
                baseline_zone=ZoneBand.RED,
            ),
        ]

    def test_baseline_untouched_after_triggers(self):
        base = self._base()
        snapshot = copy.deepcopy(base)
        trig = ScenarioTrigger(
            kind="rainfall_pct", factor=1.25,
            hazard_types=(HazardType.CLOUDBURST, HazardType.FLOOD),
            scope_all=True,
        )
        cmp = apply_triggers(base, [trig], "scn_1", "v1", "hist_2024")
        # ground-truth objects passed in are not mutated:
        assert base == snapshot
        # scenario produced separate rows
        assert len(cmp.rows) == 2
        for sim in cmp.rows:
            assert sim is not base[sim.habitation_id - 1]

    def test_delivery_delta_reported(self):
        base = self._base()
        trig = ScenarioTrigger(
            kind="rainfall_pct", factor=1.5,
            hazard_types=(HazardType.CLOUDBURST, HazardType.FLOOD),
            district_code="CHAMOLI",
        )
        cmp = apply_triggers(base, [trig], "scn_2", "v1", "hist_2024")
        # resident in Chamoli sees elevated cloudburst/flood -> higher risk
        affected = [sim for sim in cmp.rows if sim.habitation_id == 1][0]
        assert affected.scenario_risk >= affected.baseline.baseline_risk
        assert len(cmp.metrics) >= 6

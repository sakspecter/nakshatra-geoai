"""Module 2/3 service tests via pytest.

Run from repo root:
    python -m pytest backend/tests -q

These tests validate deterministic scoring, Rule-2 missing-data discipline in
the physical pipeline, and zone/priority banding without a live database.
"""

from __future__ import annotations

import pytest

from app.core.enums import HazardType, RelocationPriority, ZoneBand
from app.schemas.enums import FeatureStatus
from app.services.etl import HazardReading, PhysicalReading
from app.services.scoring import (
    FloodEvidence,
    RiskWeights,
    LandslideEvidence,
    CloudburstEvidence,
    composite_hazard,
    hazard_cloudburst,
    hazard_flood,
    hazard_landslide,
    priority_score,
    run_risk_classification,
    vulnerability_score,
    VulnerabilityInput,
    PriorityInput,
    HazardSubScore,
)


class TestPhysicalRule2:
    def test_missing_invariably_carries_none(self) -> None:
        ok = PhysicalReading("dem_elevation_m", FeatureStatus.MISSING)
        assert ok.value is None
        with pytest.raises(ValueError):
            PhysicalReading("dem_elevation_m", FeatureStatus.MISSING, value=42.0)

    def test_construed_hazard_reading_guard(self) -> None:
        with pytest.raises(ValueError):
            PhysicalReading("x", FeatureStatus.NOT_APPLICABLE, value=0.0)


class TestHazardScoring:
    def test_flood_river_distance_normalise(self) -> None:
        # near river => near 1; far => low
        near = hazard_flood(FloodEvidence(river_dist_km=0.2)).value
        far = hazard_flood(FloodEvidence(river_dist_km=20.0)).value
        assert near is not None and far is not None
        assert near > far

    def test_flood_missing(self) -> None:
        res = hazard_flood(FloodEvidence(river_dist_km=None))
        assert res.value is None
        assert res.status is FeatureStatus.MISSING

    def test_flood_inside_footprint_is_high(self) -> None:
        assert hazard_flood(FloodEvidence(river_dist_km=None, inside_inundation=True)).value == 1.0

    def test_landslide_index_below_1_0(self) -> None:
        assert hazard_landslide(LandslideEvidence(0.35)).value == pytest.approx(0.35)

    def test_cloudburst_normalise(self) -> None:
        # 150 mm maps to 1.0
        assert hazard_cloudburst(CloudburstEvidence(150.0)).value == pytest.approx(1.0)


class TestCompositeHazardMissingRule:
    def test_average_only_over_available(self) -> None:
        scores = {
            HazardType.FLOOD: HazardSubScore(0.8, FeatureStatus.AVAILABLE),
            HazardType.LANDSLIDE: HazardSubScore(None, FeatureStatus.MISSING),  # excluded
            HazardType.COASTAL_EROSION: HazardSubScore(None, FeatureStatus.NOT_APPLICABLE),
            HazardType.CLOUDBURST: HazardSubScore(0.4, FeatureStatus.AVAILABLE),
        }
        comp = composite_hazard(scores, RiskWeights())
        assert comp.value is not None
        # weight flood 0.35, cloudburst 0.20; both available
        expected = (0.35 * 0.8 + 0.20 * 0.4) / (0.35 + 0.20)
        assert comp.value == pytest.approx(expected)

    def test_no_available_returns_none_not_zero(self) -> None:
        scores = {
            HazardType.FLOOD: HazardSubScore(None, FeatureStatus.MISSING),
            HazardType.LANDSLIDE: HazardSubScore(None, FeatureStatus.MISSING),
        }
        comp = composite_hazard(scores)
        assert comp.value is None  # NEVER coerced to 0
        assert comp.status is FeatureStatus.MISSING


class TestVulnerabilityAndRisk:
    def test_vulnerability_missing_demography_none(self) -> None:
        res = vulnerability_score(
            VulnerabilityInput(
                population_density_idx=None,
                housing_quality_score=None,
                hospital_distance_idx=None,
                road_distance_idx=None,
                vulnerable_pop_share=None,
                disabled_children_elderly_idx=None,
            )
        )
        assert res.value is None

    def test_well_served_low_vuln_vs_poorly_served(self) -> None:
        well = vulnerability_score(VulnerabilityInput(  # good housing far=low vuln
            population_density_idx=0.1,
            housing_quality_score=0.9,
            hospital_distance_idx=0.1,
            road_distance_idx=0.1,
            vulnerable_pop_share=0.1,
            disabled_children_elderly_idx=0.1,
        ))
        poor = vulnerability_score(VulnerabilityInput(
            population_density_idx=0.9,
            housing_quality_score=0.1,
            hospital_distance_idx=0.9,
            road_distance_idx=0.9,
            vulnerable_pop_share=0.8,
            disabled_children_elderly_idx=0.8,
        ))
        assert well.value is not None and poor.value is not None
        assert well.value < poor.value

    def test_risk_red_via_high_hazard_high_vuln(self) -> None:
        res = run_risk_classification(
            HazardSubScore(0.85, FeatureStatus.AVAILABLE),
            HazardSubScore(0.9, FeatureStatus.AVAILABLE),
        )
        assert res.zone_band is ZoneBand.RED
        assert res.priority is RelocationPriority.IMMEDIATE

    def test_risk_green(self) -> None:
        res = run_risk_classification(
            HazardSubScore(0.1, FeatureStatus.AVAILABLE),
            HazardSubScore(0.1, FeatureStatus.AVAILABLE),
        )
        assert res.zone_band is ZoneBand.GREEN
        assert res.priority is RelocationPriority.MONITOR

    def test_missing_risk_flagged_not_safe(self) -> None:
        res = run_risk_classification(
            HazardSubScore(None, FeatureStatus.MISSING),
            HazardSubScore(None, FeatureStatus.MISSING),
        )
        assert res.risk_score is None
        assert res.status is FeatureStatus.MISSING


class TestPriorityBand:
    def test_priority_class_split(self) -> None:
        immediate = priority_score(PriorityInput(
            composite_hazard=1.0, vulnerability=1.0, history_ratio=1.0,
            exposure_share=1.0, access_difficulty=1.0,
        ))
        monitor = priority_score(PriorityInput(
            composite_hazard=0.0, vulnerability=0.0, history_ratio=0.0,
            exposure_share=0.0, access_difficulty=0.0,
        ))
        assert immediate[1] is RelocationPriority.IMMEDIATE
        assert immediate[0] == pytest.approx(1.0)
        assert monitor[1] is RelocationPriority.MONITOR or monitor[1] is RelocationPriority.PRIORITY

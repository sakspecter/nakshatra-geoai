"""Regression tests proving Rule 2 (Missing Data) and Rule 4 (Carrying
Capacity) are enforced at the API/schema boundary.

Run with:  python -m pytest tests -q
"""

from __future__ import annotations

import pytest
from pydantic import ValidationError

from app.core.enums import DataConfidence
from app.schemas.common import ScoreFeature, ValuedFeature
from app.schemas.destination import DestinationCreate
from app.schemas.enums import FeatureStatus


class TestRule2MissingData:
    def test_missing_cannot_carry_zero(self) -> None:
        # A `missing` feature MUST NOT be represented as a safe number (0).
        with pytest.raises(ValidationError):
            ScoreFeature(status=FeatureStatus.MISSING, value=0.0)

    def test_missing_with_none_is_allowed(self) -> None:
        feature = ScoreFeature(status=FeatureStatus.MISSING, value=None)
        assert feature.value is None

    def test_not_applicable_rejects_numeric(self) -> None:
        with pytest.raises(ValidationError):
            ScoreFeature(status=FeatureStatus.NOT_APPLICABLE, value=0.5)

    def test_available_requires_value(self) -> None:
        with pytest.raises(ValidationError):
            ScoreFeature(status=FeatureStatus.AVAILABLE, value=None)

    def test_available_out_of_range_rejected(self) -> None:
        with pytest.raises(ValidationError):
            ScoreFeature(status=FeatureStatus.AVAILABLE, value=1.7)

    def test_genetic_valued_feature_missing_guard(self) -> None:
        with pytest.raises(ValidationError):
            ValuedFeature[int](status=FeatureStatus.MISSING, value=42)


class TestRule4CarryingCapacity:
    @staticmethod
    def _make_destination() -> DestinationCreate:
        return DestinationCreate(
            destination_code="UK-CH-SITE-01",
            name="Demo Site",
            admin_unit_id=1,
            housing_cap=520,
            water_cap=400,
            healthcare_cap=250,
            safe_land_cap=600,
            accessibility_cap=380,
            geom={
                "type": "Polygon",
                "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
            },
            centroid={"type": "Point", "coordinates": [0.5, 0.5]},
            is_verified_site=True,
        )

    def test_overall_capacity_is_min_of_ceilings(self) -> None:
        d = self._make_destination()
        assert min(520, 400, 250, 600, 380) == 250
        assert d.overall_capacity == 250  # tightest ceiling governs

    def test_negative_capacity_rejected(self) -> None:
        with pytest.raises(ValidationError):
            DestinationCreate(
                destination_code="X",
                name="Y",
                admin_unit_id=1,
                housing_cap=-1,
                water_cap=10,
                healthcare_cap=10,
                safe_land_cap=10,
                accessibility_cap=10,
                geom={
                    "type": "Polygon",
                    "coordinates": [[[0, 0], [1, 0], [1, 1], [0, 1], [0, 0]]],
                },
                centroid={"type": "Point", "coordinates": [0.5, 0.5]},
            )


class TestConfidenceEnumValues:
    def test_data_confidence_labels(self) -> None:
        labels = {dc.value for dc in DataConfidence}
        assert labels == {
            "confirmed",
            "low_confidence",
            "missing",
            "not_applicable",
        }

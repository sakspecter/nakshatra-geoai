"""Module 4 - ML engine + SHAP tests (no DB needed)."""

from __future__ import annotations

import numpy as np
import pandas as pd
import pytest

from app.core.enums import HazardType
from app.services.ml_engine import (
    QUALITY_INSUFFICIENT,
    QUALITY_SUFFICIENT,
    MLConfig,
    ShapDriver,
    evidence_state_for_row,
    predict_model,
    train_event_model,
    save_artifact,
    load_artifact,
)


def _synth(n_per_group: int = 60) -> pd.DataFrame:
    rng = np.random.RandomState(1)
    n = n_per_group * 2
    df = pd.DataFrame(
        {
            "region": ["UK"] * n_per_group + ["AS"] * n_per_group,
            "slope": rng.uniform(0, 40, n),
            "rain3d": rng.uniform(20, 180, n),
            "dist_river": rng.uniform(0, 20, n),
            "geom": rng.uniform(0, 1, n),
        }
    )
    logit = (df["slope"] - 20) / 8 + (df["rain3d"] - 120) / 40
    df["occurred"] = (rng.uniform(0, 1, n) < 1 / (1 + np.exp(-logit))).astype(int)
    return df


class TestEvidenceGate:
    def test_missing_beyond_tolerance_insufficient(self):
        status, frac = evidence_state_for_row(
            ["slope", "rain3d", "dist_river", "geom"],
            {"slope": 30.0},  # only 1 of 4 present => 0.75 missing
            allowed_missing_fraction=0.20,
        )
        assert status == QUALITY_INSUFFICIENT
        assert frac == pytest.approx(0.75)

    def test_within_tolerance_sufficient(self):
        status, frac = evidence_state_for_row(
            ["a", "b", "c", "d"],
            {"a": 1.0, "b": None, "c": 3.0, "d": None},  # 0.5 missing
            allowed_missing_fraction=0.6,
        )
        assert status == QUALITY_SUFFICIENT
        assert frac == pytest.approx(0.5)


class TestTrainingAndMetrics:
    def test_spatial_group_kfold_trains_metrics(self):
        df = _synth()
        m = train_event_model(
            df,
            "occurred",
            "region",
            ["slope", "rain3d", "dist_river", "geom"],
            model_version="events_v001",
            train_dataset_version="hist_2023",
            hazard_type=HazardType.LANDSLIDE,
        )
        mean = m.metrics["mean"]
        assert "mean_precision" in mean
        assert "mean_recall" in mean
        assert "mean_critical_class_recall" in mean
        assert m.metrics["label_summary"]["total"] > 0


class TestPredictionQualities:
    def _model(self):
        df = _synth()
        return train_event_model(df, "occurred", "region",
                                 ["slope", "rain3d", "dist_river", "geom"],
                                 "events_v001", "hist_2023",
                                 HazardType.LANDSLIDE)

    def test_complete_sample_sufficient_with_shap(self):
        m = self._model()
        sample = {"slope": 35.0, "rain3d": 150.0, "dist_river": 0.5, "geom": 0.6}
        (res,) = predict_model(m, [sample], [1])
        assert res.feature_quality_status == QUALITY_SUFFICIENT
        assert res.predicted_probability is not None
        assert res.prediction_class in (0, 1)
        assert len(res.shap_explanation_summary) > 0
        assert isinstance(res.shap_explanation_summary[0], ShapDriver)

    def test_deficient_sample_insufficient_no_fabrication(self):
        m = self._model()
        sample = {"slope": 35.0}  # only 1/4 present -> insufficient
        (res,) = predict_model(m, [sample], [7])
        assert res.feature_quality_status == QUALITY_INSUFFICIENT
        assert res.predicted_probability is None
        assert res.prediction_class is None
        assert res.shap_explanation_summary == []


class TestRandomForestFallback:
    def test_rf_predicts_on_complete(self):
        df = _synth()
        m = train_event_model(df, "occurred", "region",
                              ["slope", "rain3d"],
                              "rf_v001", "hist_2023", HazardType.FLOOD,
                              backend="random_forest")
        sample = {"slope": 30.0, "rain3d": 160.0}
        (res,) = predict_model(m, [sample], [11])
        assert res.predicted_probability is not None
        assert res.feature_quality_status == QUALITY_SUFFICIENT


class TestArtifactRoundTrip:
    def test_save_load(self, tmp_path):
        df = _synth()
        m = train_event_model(df, "occurred", "region",
                              ["slope", "rain3d"],
                              "events_v009", "hist_2023", HazardType.FLOOD)
        save_artifact(m, tmp_path)
        loaded = load_artifact(tmp_path, "events_v009")
        assert loaded.feature_names == m.feature_names
        assert loaded.model_version == m.model_version
        assert tuple(loaded.classes_) == tuple(m.classes_)

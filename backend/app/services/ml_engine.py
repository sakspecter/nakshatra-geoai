"""Module 4 - ML Hazard-Occurrence Prediction + SHAP explainability.

MODEL / Rule 3 DISCIPLINE
=========================
This supervised engine learns to predict the occurrence (1/0) of an actually
observed historical disaster event. It trains ONLY on rows from the
``historical_outcomes`` table; it is NEVER trained to predict or reproduce a
deterministic composite risk score. Deterministic hazards may appear as optional
*input features* (never as labels). What the model does predict is the
probability of an observed event occurring for a given hazard type.

WORKFLOW
--------
1. Assemble a feature matrix whose rows join a habitation's physical/process
   data to its historical event labels (``occurred`` per hazard).
2. Partition samples by an explicit spatial ``group`` column (state/district)
   and use Group K-Fold so folds never leak across geographic regions.
3. Train ``xgboost.XGBClassifier`` (primary) or RandomForestClassifier (fallback);
   report precision / recall / F1 / ROC-AUC / confusion / critical-class recall.
4. Inference enforces an *evidence gate*: if more than a configurable fraction of
   required features are missing for a habitation, the result is an explicit
   ``insufficient_evidence`` state with ``predicted_probability = None``. Missing
   features are NEVER fabricated or median-filled.
5. Local SHAP attributions (logit-space) are returned for each served prediction.

UNIT HONESTY
------------
SHAP reports additive contributions in logit space. We surface magnitude +
direction and label drivers with literal descriptors; we never report the logit
contribution as if it were a probability.
"""

from __future__ import annotations

import json
import logging
import math
from dataclasses import dataclass, field
from pathlib import Path
from typing import Any, Literal, Optional, Sequence

import numpy as np
import pandas as pd
from sklearn.ensemble import RandomForestClassifier
from sklearn.metrics import (
    accuracy_score,
    confusion_matrix,
    f1_score,
    precision_score,
    recall_score,
    roc_auc_score,
)
from sklearn.model_selection import GroupKFold
from xgboost import XGBClassifier

from app.core.enums import DataConfidence, HazardType

logger = logging.getLogger(__name__)

ModelBackend = Literal["xgboost", "random_forest"]

QUALITY_SUFFICIENT = "sufficient"
QUALITY_INSUFFICIENT = "insufficient_evidence"


# ---------------------------------------------------------------------------
# ML response / artifact contracts
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class ShapDriver:
    """One ranked local attribution driver."""

    feature: str
    direction: Literal["+", "-"]
    contribution: float             # logit-space, always >=0 stored here
    human_label: str
    rank: int = 0

    def to_dict(self) -> dict[str, Any]:
        return {
            "feature": self.feature,
            "direction": self.direction,
            "contribution": round(self.contribution, 4),
            "label": self.human_label,
            "rank": self.rank,
        }


@dataclass(frozen=True)
class MLPredictionResult:
    """Complete inference return value persistable straight into ``MLPrediction``."""

    habitation_id: int
    hazard_type: HazardType
    predicted_probability: Optional[float]
    prediction_class: Optional[int]
    model_version: str
    feature_quality_status: str
    shap_explanation_summary: list[ShapDriver] = field(default_factory=list)
    model_algorithm: str = "xgboost"
    train_dataset_version: str = "dataset.train"
    scenario_version: str = "scenario.baseline"
    risk_config_version: str = "risk_cfg.v1"

    @property
    def confidence(self) -> DataConfidence:
        if self.feature_quality_status == QUALITY_INSUFFICIENT:
            return DataConfidence.MISSING
        return DataConfidence.CONFIRMED

    def to_dict(self) -> dict[str, Any]:
        return {
            "habitation_id": self.habitation_id,
            "hazard_type": self.hazard_type.value,
            "predicted_probability": (
                None
                if self.predicted_probability is None
                else round(self.predicted_probability, 4)
            ),
            "prediction_class": self.prediction_class,
            "model_version": self.model_version,
            "feature_quality_status": self.feature_quality_status,
            "shap_explanation_summary": [d.to_dict() for d in self.shap_explanation_summary],
            "model_algorithm": self.model_algorithm,
            "train_dataset_version": self.train_dataset_version,
            "scenario_version": self.scenario_version,
            "risk_config_version": self.risk_config_version,
        }


@dataclass(frozen=True)
class TrainedEventModel:
    """The immutable prediction artifact: fitted model + its feature contract."""

    model_version: str
    train_dataset_version: str
    feature_names: tuple[str, ...]
    hazard_type: Optional[HazardType]
    backend: ModelBackend
    estimator: Any = field(repr=False)
    metrics: dict[str, Any] = field(default_factory=dict)
    classes_: tuple[int, int] = (0, 1)

    @property
    def na_acceptable(self) -> bool:
        """XGBoost natively routes NaN; RandomForest cannot - affects gating."""
        return self.backend == "xgboost"

    def basename(self) -> str:
        tag = self.hazard_type.value if self.hazard_type else "general"
        return f"{tag}_{self.model_version}"


@dataclass
class MLConfig:
    """Tunable policy (no code edits needed to adjust)."""

    allowed_missing_fraction: float = 0.20
    probability_threshold: float = 0.5
    random_state: int = 42
    n_jobs: int = -1
    n_estimators: int = 250
    max_depth: int = 5


# ---------------------------------------------------------------------------
# Evidence gate
# ---------------------------------------------------------------------------
def _is_unusable(value: Any) -> bool:
    if value is None:
        return True
    try:
        v = float(value)
    except (TypeError, ValueError):
        return True
    return math.isnan(v) or math.isinf(v)


def evidence_state_for_row(
    required_features: Sequence[str],
    row: dict[str, Any],
    allowed_missing_fraction: float,
) -> tuple[str, float]:
    """Return (quality_status, missing_fraction) for one habitation.

    NEVER defaults or imputes; if the missing-fraction exceeds tolerance the gate
    closes and the prediction is marked ``insufficient_evidence``.
    """
    if not required_features:
        return QUALITY_SUFFICIENT, 0.0
    missing = sum(1 for f in required_features if _is_unusable(row.get(f)))
    frac = missing / len(required_features)
    status = QUALITY_SUFFICIENT if frac <= allowed_missing_fraction else QUALITY_INSUFFICIENT
    return status, frac


# ---------------------------------------------------------------------------
# Spatial Group K-Fold evaluation
# ---------------------------------------------------------------------------
def evaluate_binary(
    y_true: np.ndarray, y_pred: np.ndarray, y_proba: np.ndarray
) -> dict[str, Any]:
    """Metrics with explicit publication of critical(positive)-class recall."""
    out: dict[str, Any] = {}
    out["precision"] = float(precision_score(y_true, y_pred, zero_division=0))
    out["recall"] = float(recall_score(y_true, y_pred, zero_division=0))
    out["f1"] = float(f1_score(y_true, y_pred, zero_division=0))
    out["roc_auc"] = None
    if len(np.unique(y_true)) > 1:
        try:
            out["roc_auc"] = float(roc_auc_score(y_true, y_proba))
        except Exception:  # pragma: no cover
            out["roc_auc"] = None
    tn, fp, fn, tp = confusion_matrix(y_true, y_pred, labels=[0, 1]).ravel()
    positive = tp + fn
    out["critical_class_recall"] = None if positive == 0 else float(tp / positive)
    out["confusion_matrix"] = {
        "true_neg": int(tn),
        "false_pos": int(fp),
        "false_neg": int(fn),
        "true_pos": int(tp),
        "positive_total": int(positive),
    }
    out["accuracy"] = float(accuracy_score(y_true, y_pred))
    return out


def build_classifier(backend: ModelBackend, cfg: MLConfig) -> Any:
    if backend == "random_forest":
        return RandomForestClassifier(
            n_estimators=cfg.n_estimators,
            max_depth=cfg.max_depth,
            min_samples_leaf=3,
            class_weight="balanced",
            random_state=cfg.random_state,
            n_jobs=cfg.n_jobs,
        )
    return XGBClassifier(
        n_estimators=cfg.n_estimators,
        max_depth=cfg.max_depth,
        learning_rate=0.03,
        subsample=0.85,
        colsample_bytree=0.7,
        objective="binary:logistic",
        eval_metric="auc",
        tree_method="hist",
        random_state=cfg.random_state,
        n_jobs=cfg.n_jobs,
    )


def train_event_model(
    df: pd.DataFrame,
    target_col: str,
    group_col: str,
    feature_cols: Sequence[str],
    model_version: str,
    train_dataset_version: str,
    hazard_type: HazardType,
    backend: ModelBackend = "xgboost",
    cfg: MLConfig | None = None,
    n_splits: int = 5,
) -> TrainedEventModel:
    """Fit on historical event labels using Spatial Group K-Fold validation.

    Parameters mirror the Rule 3 boundary: ``target_col`` comes exclusively from
    the observed-outcome table (occurred:1/0), not from any composite score.
    """
    cfg = cfg or MLConfig()
    feature_cols = list(feature_cols)
    X = df[feature_cols].to_numpy(dtype="float64")
    y = df[target_col].to_numpy(dtype="int64")
    groups = df[group_col].to_numpy()

    labels = {
        "total": int(len(y)),
        "positive": int(int(y.sum())),
        "prevalence_class1": round(int(y.sum()) / max(len(y), 1), 4),
    }
    uniq_groups, counts = np.unique(groups, return_counts=True)
    group_summary = {
        "n_groups": int(len(uniq_groups)),
        "groups_seen": [str(g) for g in _flat(groups)],
        "rows_per_group": [int(c) for c in counts],
    }

    n_groups = int(len(uniq_groups))
    splits = max(2, min(n_splits, n_groups))
    splitter = GroupKFold(n_splits=splits)

    fold_metrics: list[dict[str, Any]] = []
    oof_proba: list[np.ndarray] = []
    oof_true: list[np.ndarray] = []

    for fold_i, (tr, va) in enumerate(splitter.split(X, y, groups=groups)):
        y_tr = y[tr]
        if len(np.unique(y_tr)) < 2:
            fold_metrics.append({"fold": fold_i, "skipped_no_positive_train": True})
            continue
        clf = build_classifier(backend, cfg)
        clf.fit(X[tr], y_tr)
        p = clf.predict_proba(X[va])[:, 1]
        pred = (p >= cfg.probability_threshold).astype(int)
        m = evaluate_binary(y[va], pred, p)
        m["fold"] = fold_i
        m["val_groups"] = [str(g) for g in np.unique(groups[va])]
        fold_metrics.append(m)
        oof_proba.append(p)
        oof_true.append(y[va])

    mean_metrics = _aggregate_fold_metrics(fold_metrics)

    # Final estimator fitted to the complete spatial-labelled set for serving.
    estimator = build_classifier(backend, cfg)
    estimator.fit(X, y)

    return TrainedEventModel(
        model_version=model_version,
        train_dataset_version=train_dataset_version,
        feature_names=tuple(feature_cols),
        hazard_type=hazard_type,
        backend=backend,
        estimator=estimator,
        metrics={
            "fold_metrics": fold_metrics,
            "mean": mean_metrics,
            "label_summary": labels,
        },
    )


def _flat(groups: np.ndarray) -> list[Any]:
    return list(np.ravel(groups))


def _aggregate_fold_metrics(fold_metrics: list[dict[str, Any]]) -> dict[str, Any]:
    keys = [
        "precision",
        "recall",
        "f1",
        "roc_auc",
        "accuracy",
        "critical_class_recall",
    ]
    out: dict[str, Any] = {}
    for k in keys:
        vals = [m[k] for m in fold_metrics if isinstance(m.get(k), (int, float))]
        out[f"mean_{k}"] = round(float(np.mean(vals)), 4) if vals else None
        out[f"std_{k}"] = round(float(np.std(vals)), 4) if len(vals) > 1 else None
    out["usable_folds"] = len([m for m in fold_metrics if "skipped" not in m])
    return out


# ---------------------------------------------------------------------------
# SHAP
# ---------------------------------------------------------------------------
def _human_label(feature: str, direction: str) -> str:
    base = feature.replace("_", " ").replace("-", " ").strip().title() or feature
    tone = "High" if direction == "+" else "Low"
    return f"{tone} {base}"


def explain_local(model: TrainedEventModel, X_row: np.ndarray) -> list[ShapDriver]:
    """Return ranked local attributions for the positive (event) class."""
    import shap  # lazy to keep module import cheap

    explainer = shap.TreeExplainer(model.estimator)
    values = explainer.shap_values(X_row)

    if isinstance(values, list):
        values = values[1] if len(values) > 1 else values[0]
    arr = np.asarray(values).flatten()
    if len(arr) != len(model.feature_names):
        raise ValueError("SHAP value length did not match the feature contract")

    drivers: list[ShapDriver] = []
    for feat, contrib in zip(model.feature_names, arr):
        direction: Literal["+", "-"] = "+" if float(contrib) >= 0 else "-"
        drivers.append(
            ShapDriver(
                feature=feat,
                direction=direction,
                contribution=abs(float(contrib)),
                human_label=_human_label(feat, direction),
            )
        )
    drivers.sort(key=lambda d: d.contribution, reverse=True)
    for rank, d in enumerate(drivers, start=1):
        object.__setattr__(d, "rank", rank)  # frozen dataclass: allowed
    return drivers


# ---------------------------------------------------------------------------
# Inference
# ---------------------------------------------------------------------------
def _float_or_nan(value: Any) -> float:
    if value is None:
        return float("nan")
    try:
        return float(value)
    except (TypeError, ValueError):
        return float("nan")


def predict_model(
    model: TrainedEventModel,
    samples: list[dict[str, Any]],
    habitation_ids: Sequence[int],
    allowed_missing_fraction: float | None = None,
    threshold: float | None = None,
    shap_top_k: int = 5,
    scenario_version: str = "scenario.baseline",
    risk_config_version: str = "risk_cfg.v1",
) -> list[MLPredictionResult]:
    """Run the evidence gate, then honest predict + SHAP for each habitation.

    Order of returned results matches ``samples``/``habitation_ids`` order. Every
    input produces exactly one result; habitation lacking enough evidence yields
    an ``insufficient_evidence`` result (probability None), never a fabricated one.
    """
    frac = (
        MLConfig().allowed_missing_fraction
        if allowed_missing_fraction is None
        else allowed_missing_fraction
    )
    thresh = MLConfig().probability_threshold if threshold is None else threshold

    hazard_type = model.hazard_type if model.hazard_type else HazardType.FLOOD
    results: list[MLPredictionResult] = []

    # indices of result that are *not* closed yet and their feature vectors
    open_positions: list[int] = []
    open_rows: list[np.ndarray] = []
    open_ids: list[int] = []

    for pos, (sample, hid) in enumerate(zip(samples, habitation_ids)):
        status, _ = evidence_state_for_row(model.feature_names, sample, frac)
        if status == QUALITY_INSUFFICIENT:
            results.append(
                MLPredictionResult(
                    habitation_id=int(hid),
                    hazard_type=hazard_type,
                    predicted_probability=None,
                    prediction_class=None,
                    model_version=model.model_version,
                    feature_quality_status=QUALITY_INSUFFICIENT,
                    model_algorithm=model.backend,
                    train_dataset_version=model.train_dataset_version,
                    scenario_version=scenario_version,
                    risk_config_version=risk_config_version,
                )
            )
            continue

        vector = np.asarray(
            [_float_or_nan(sample.get(f)) for f in model.feature_names],
            dtype="float64",
        )
        # Reserve slot (temporary insufficient placeholder) and remember position.
        results.append(
            MLPredictionResult(
                habitation_id=int(hid),
                hazard_type=hazard_type,
                predicted_probability=None,
                prediction_class=None,
                model_version=model.model_version,
                feature_quality_status=QUALITY_SUFFICIENT,  # provisional
                model_algorithm=model.backend,
                train_dataset_version=model.train_dataset_version,
                scenario_version=scenario_version,
                risk_config_version=risk_config_version,
            )
        )
        open_positions.append(pos)
        open_rows.append(vector)
        open_ids.append(hid)

    # For backends that cannot take NaN (RandomForest), a row still missing a
    # feature after passing tolerance is honestly downgraded to insufficient.
    for j in range(len(open_rows)):
        row = open_rows[j]
        pos = open_positions[j]
        hid = int(open_ids[j])

        if not model.na_acceptable and np.isnan(row).any():
            results[pos] = _result_insufficient(
                hid, hazard_type, model, scenario_version, risk_config_version
            )
            continue

        proba = float(model.estimator.predict_proba(row.reshape(1, -1))[0, 1])
        if math.isnan(proba):
            results[pos] = _result_insufficient(
                hid, hazard_type, model, scenario_version, risk_config_version
            )
            continue
        label = int(proba >= thresh)

        drivers: list[ShapDriver] = []
        try:
            drivers = explain_local(model, row.reshape(1, -1))[:shap_top_k]
        except Exception as exc:  # pragma: no cover
            logger.warning("SHAP failed for habitation %s: %s", hid, exc)

        results[pos] = MLPredictionResult(
            habitation_id=hid,
            hazard_type=hazard_type,
            predicted_probability=proba,
            prediction_class=label,
            model_version=model.model_version,
            feature_quality_status=QUALITY_SUFFICIENT,
            shap_explanation_summary=drivers,
            model_algorithm=model.backend,
            train_dataset_version=model.train_dataset_version,
            scenario_version=scenario_version,
            risk_config_version=risk_config_version,
        )

    return results


def _result_insufficient(
    hid: int,
    hazard_type: HazardType,
    model: TrainedEventModel,
    scenario_version: str,
    risk_config_version: str,
) -> MLPredictionResult:
    return MLPredictionResult(
        habitation_id=hid,
        hazard_type=hazard_type,
        predicted_probability=None,
        prediction_class=None,
        model_version=model.model_version,
        feature_quality_status=QUALITY_INSUFFICIENT,
        model_algorithm=model.backend,
        train_dataset_version=model.train_dataset_version,
        scenario_version=scenario_version,
        risk_config_version=risk_config_version,
    )


# ---------------------------------------------------------------------------
# Persistence (.json metadata + .joblib estimator)
# ---------------------------------------------------------------------------
def save_artifact(
    model: TrainedEventModel, directory: str | Path
) -> tuple[Path, Path]:
    import joblib

    directory = Path(directory)
    directory.mkdir(parents=True, exist_ok=True)
    meta_path = directory / f"event_model_{model.basename()}.json"
    est_path = directory / f"event_estimator_{model.basename()}.joblib"

    payload = {
        "model_version": model.model_version,
        "train_dataset_version": model.train_dataset_version,
        "backend": model.backend,
        "hazard_type": model.hazard_type.value if model.hazard_type else None,
        "feature_names": list(model.feature_names),
        "classes": list(model.classes_),
        "metrics": model.metrics,
    }
    meta_path.write_text(
        json.dumps(payload, indent=2, default=str), encoding="utf-8"
    )
    joblib.dump(model.estimator, est_path)
    logger.info("Saved estimator %s and meta %s", est_path, meta_path)
    return meta_path, est_path


def load_artifact(directory: str | Path, model_version: str) -> TrainedEventModel:
    import joblib

    directory = Path(directory)
    # Resolve which hazard tag: first locate matching .json files.
    candidates = sorted(directory.glob(f"event_model_*_{model_version}.json"))
    if not candidates:
        raise FileNotFoundError(
            f"No saved model artifact for model_version={model_version} "
            f"in {directory}"
        )
    meta_path = candidates[0]
    meta = json.loads(meta_path.read_text(encoding="utf-8"))
    # Reconstruct estimator filename from the metadata filename's hazard tag.
    tag = meta_path.stem.replace("event_model_", "", 1).rsplit(f"_{model_version}", 1)[0]
    est_path = directory / f"event_estimator_{tag}_{model_version}.joblib"
    estimator = joblib.load(est_path)

    return TrainedEventModel(
        model_version=meta["model_version"],
        train_dataset_version=meta["train_dataset_version"],
        feature_names=tuple(meta["feature_names"]),
        classes_=tuple(meta.get("classes", [0, 1])),
        hazard_type=HazardType(meta["hazard_type"]) if meta.get("hazard_type") else None,
        backend=meta.get("backend", "xgboost"),
        estimator=estimator,
        metrics=meta.get("metrics", {}),
    )


# ---------------------------------------------------------------------------
# DB sync helpers (provenance-heavy insertion into MLPrediction table)
# ---------------------------------------------------------------------------
async def persist_predictions(
    session: Any,
    predictions: list[MLPredictionResult],
    table_version_tag: str = "ml_predictions",
) -> int:
    """Write ML results asynchronously into ``ml_predictions`` (upsert by
    ``(habitation_id, hazard_type, model_version)``) and mirror provenance to the
    audit log. Implemented as a thin import-forward so callers import uniformly
    from this module or ``db_sync``.
    """
    from app.services.db_sync import upsert_ml_predictions

    return await upsert_ml_predictions(session, predictions, table_version_tag)

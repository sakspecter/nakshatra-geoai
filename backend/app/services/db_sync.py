"""Module 3 - Asynchronous database synchronization.

Writes processed hazard/vulnerability results into the correct separate tables
using SQLAlchemy 2.0 async sessions, with full provenance metadata (Rule 6) and
strict confidence mapping honouring the Missing Data Rule (Rule 2).

Design notes:

* A single function per target table prevents accidental cross-layer writes
  (Rule 3 separation is preserved at the service boundary). The hazard writer only
  ever touches ``hazard_layers``; the vulnerability writer only
  ``vulnerability_layers``.
* Every row insert is version-keyed; re-ingestion of an identical
  ``(habitation, hazard_type, dataset_version)`` performs an **upsert** so failed
  batches can be re-run idempotently, avoiding duplicate physical evidence rows.
"""

from __future__ import annotations

from dataclasses import dataclass, field
from datetime import datetime, timezone
from typing import Optional

from sqlalchemy import delete, select
from sqlalchemy.ext.asyncio import AsyncSession

from app.core.enums import DataConfidence, HazardType
from app.models.audit_provenance import AuditProvenance
from app.models.hazard import HazardLayer
from app.models.historical_outcome import MLPrediction
from app.models.vulnerability import VulnerabilityLayer
from app.schemas.enums import FeatureStatus


# ---------------------------------------------------------------------------
# status -> DB confidence mapping (data_confidence is the source of truth)
# ---------------------------------------------------------------------------
def _confidence_of(feature_status: FeatureStatus) -> DataConfidence:
    return {
        FeatureStatus.AVAILABLE: DataConfidence.CONFIRMED,
        FeatureStatus.LOW_CONFIDENCE: DataConfidence.LOW_CONFIDENCE,
        FeatureStatus.MISSING: DataConfidence.MISSING,
        FeatureStatus.NOT_APPLICABLE: DataConfidence.NOT_APPLICABLE,
    }.get(feature_status, DataConfidence.MISSING)


# ---------------------------------------------------------------------------
# Row DTOs
# ---------------------------------------------------------------------------
@dataclass(frozen=True)
class HazardLayerRecord:
    habitation_id: int
    hazard_type: HazardType
    score: Optional[float]             # None when the reading was missing/NA (Rule 2)
    status: FeatureStatus
    dataset_version: str
    model_version: Optional[str] = None
    risk_config_version: str = "risk_cfg.v1"
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def confidence(self) -> DataConfidence:
        return _confidence_of(self.status)


@dataclass(frozen=True)
class VulnerabilityLayerRecord:
    habitation_id: int
    score: Optional[float]
    status: FeatureStatus
    dataset_version: str
    risk_config_version: str = "risk_cfg.v1"
    population_sub: Optional[float] = None
    social_proxy_sub: Optional[float] = None
    housing_quality_sub: Optional[float] = None
    critical_access_sub: Optional[float] = None
    evac_access_sub: Optional[float] = None
    component_confidence: Optional[dict] = None
    computed_at: datetime = field(default_factory=lambda: datetime.now(timezone.utc))

    @property
    def confidence(self) -> DataConfidence:
        return _confidence_of(self.status)


# ---------------------------------------------------------------------------
# Shared provenance logger (Rule 6)
# ---------------------------------------------------------------------------
async def _log_provenance(
    session: AsyncSession,
    record_id: int,
    table: str,
    context: dict,
    actor: str,
) -> None:
    """Insert one ``audit_provenance`` row capturing all four version pillars.

    The four provenance keys may not each be a physical column on every table; the
    audit log is where the full context is persisted together.
    """
    session.add(
        AuditProvenance(
            actor=actor,
            action="UPSERT",
            entity_table=table,
            entity_id=record_id,
            operation_context=context,
        )
    )


# ---------------------------------------------------------------------------
# Hazard writer
# ---------------------------------------------------------------------------
async def sync_hazard_layers(
    session: AsyncSession,
    records: list[HazardLayerRecord],
    actor: str = "hazard_engine",
) -> int:
    """Upsert hazard-layer rows in one transaction.

    Matching key is ``(habitation_id, hazard_type, dataset_version)``; if present
    the value is replaced, else a fresh row is inserted. Provenance (Rule 6) is
    mirrored into ``audit_provenance`` with the four version pillars.
    """
    written = 0
    for rec in records:
        stmt = select(HazardLayer).where(
            HazardLayer.habitation_id == rec.habitation_id,
            HazardLayer.hazard_type == rec.hazard_type,
            HazardLayer.dataset_version == rec.dataset_version,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing is not None:
            existing.hazard_score_01 = rec.score
            existing.hazard_confidence = rec.confidence
            existing.model_version = rec.model_version
            existing.computed_at = rec.computed_at
            await session.flush()
            row_id = int(existing.id)
        else:
            new_row = HazardLayer(
                habitation_id=rec.habitation_id,
                hazard_type=rec.hazard_type,
                hazard_score_01=rec.score,
                hazard_confidence=rec.confidence,
                dataset_version=rec.dataset_version,
                model_version=rec.model_version,
                computed_at=rec.computed_at,
            )
            session.add(new_row)
            await session.flush()
            row_id = int(new_row.id)

        await _log_provenance(
            session,
            record_id=row_id,
            table="hazard_layers",
            context={
                "dataset_version": rec.dataset_version,
                "model_version": rec.model_version,
                "scenario_version": "scenario.none",
                "risk_config_version": rec.risk_config_version,
                "hazard_type": rec.hazard_type.value,
                "confidence": rec.confidence.value,
            },
            actor=actor,
        )
        written += 1

    await session.commit()
    return written


async def purge_hazard_for_version(
    session: AsyncSession, dataset_version: str
) -> int:
    """Delete all hazard rows tagged to a given dataset_version (full re-run)."""
    result = await session.execute(
        delete(HazardLayer).where(HazardLayer.dataset_version == dataset_version)
    )
    await session.commit()
    return int(result.rowcount or 0)


# ---------------------------------------------------------------------------
# Vulnerability writer
# ---------------------------------------------------------------------------
async def sync_vulnerability_layers(
    session: AsyncSession,
    records: list[VulnerabilityLayerRecord],
    actor: str = "vulnerability_engine",
) -> int:
    """Upsert vulnerability-layer rows.

    Version key: ``(habitation_id, dataset_version, risk_config_version)``; when a
    matching row already exists its score & component sub-scores are replaced so an
    idempotent re-run can't grow duplicate rows.
    """
    written = 0
    for rec in records:
        stmt = select(VulnerabilityLayer).where(
            VulnerabilityLayer.habitation_id == rec.habitation_id,
            VulnerabilityLayer.dataset_version == rec.dataset_version,
            VulnerabilityLayer.risk_config_version == rec.risk_config_version,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        if existing is not None:
            existing.vuln_score_01 = rec.score
            existing.vuln_confidence = rec.confidence
            existing.population_sub = rec.population_sub
            existing.social_proxy_sub = rec.social_proxy_sub
            existing.housing_quality_sub = rec.housing_quality_sub
            existing.critical_access_sub = rec.critical_access_sub
            existing.evac_access_sub = rec.evac_access_sub
            existing.component_confidence = rec.component_confidence
            existing.computed_at = rec.computed_at
            await session.flush()
            row_id = int(existing.id)
        else:
            new_row = VulnerabilityLayer(
                habitation_id=rec.habitation_id,
                vuln_score_01=rec.score,
                vuln_confidence=rec.confidence,
                population_sub=rec.population_sub,
                social_proxy_sub=rec.social_proxy_sub,
                housing_quality_sub=rec.housing_quality_sub,
                critical_access_sub=rec.critical_access_sub,
                evac_access_sub=rec.evac_access_sub,
                component_confidence=rec.component_confidence,
                dataset_version=rec.dataset_version,
                risk_config_version=rec.risk_config_version,
                computed_at=rec.computed_at,
            )
            session.add(new_row)
            await session.flush()
            row_id = int(new_row.id)

        await _log_provenance(
            session,
            record_id=row_id,
            table="vulnerability_layers",
            context={
                "dataset_version": rec.dataset_version,
                "model_version": "model.none",
                "scenario_version": "scenario.none",
                "risk_config_version": rec.risk_config_version,
                "confidence": rec.confidence.value,
            },
            actor=actor,
        )
        written += 1

    await session.commit()
    return written


async def upsert_ml_predictions(
    session: AsyncSession,
    predictions: list,
    actor: str = "ml_engine",
) -> int:
    """Persist ML prediction/SHAP outputs into ``ml_predictions`` (upsert).

    Each item is expected to expose the attributes consumed here (see
    ``app.services.ml_engine.MLPredictionResult``): ``habitation_id``,
    ``hazard_type``, ``predicted_probability``, ``prediction_class``,
    ``model_version``, ``feature_quality_status``, ``shap_explanation_summary``,
    ``model_algorithm``, ``train_dataset_version``, ``scenario_version``,
    ``risk_config_version``, and ``confidence``.

    Key: ``(habitation_id, hazard_type, model_version)``.
    """
    written = 0
    for pred in predictions:
        stmt = select(MLPrediction).where(
            MLPrediction.habitation_id == pred.habitation_id,
            MLPrediction.hazard_type == pred.hazard_type,
            MLPrediction.model_version == pred.model_version,
        )
        existing = (await session.execute(stmt)).scalar_one_or_none()

        shap_spec = {
            "summary": [d.to_dict() for d in pred.shap_explanation_summary],
            "feature_quality_status": pred.feature_quality_status,
        }
        if existing is not None:
            existing.event_probability = pred.predicted_probability
            existing.prediction_class = pred.prediction_class
            existing.model_algorithm = pred.model_algorithm
            existing.feature_quality_status = pred.feature_quality_status
            existing.shap_json = shap_spec
            existing.prediction_confidence = pred.confidence
            existing.train_dataset_version = pred.train_dataset_version
            existing.scenario_version = pred.scenario_version
            existing.risk_config_version = pred.risk_config_version
            await session.flush()
            row_id = int(existing.id)
        else:
            session.add(
                MLPrediction(
                    habitation_id=pred.habitation_id,
                    hazard_type=pred.hazard_type,
                    event_probability=pred.predicted_probability,
                    prediction_class=pred.prediction_class,
                    model_algorithm=pred.model_algorithm,
                    feature_quality_status=pred.feature_quality_status,
                    model_version=pred.model_version,
                    train_dataset_version=pred.train_dataset_version,
                    scenario_version=pred.scenario_version,
                    risk_config_version=pred.risk_config_version,
                    shap_json=shap_spec,
                    prediction_confidence=pred.confidence,
                )
            )
            await session.flush()
            row_id = int((await session.execute(
                select(MLPrediction)
                .where(MLPrediction.habitation_id == pred.habitation_id)
                .where(MLPrediction.model_version == pred.model_version)
                .where(MLPrediction.hazard_type == pred.hazard_type)
            )).scalar_one().id)

        await _log_provenance(
            session,
            record_id=row_id,
            table="ml_predictions",
            context={
                "dataset_version": pred.train_dataset_version,
                "model_version": pred.model_version,
                "scenario_version": pred.scenario_version,
                "risk_config_version": pred.risk_config_version,
                "hazard_type": pred.hazard_type.value,
                "quality_status": pred.feature_quality_status,
            },
            actor=actor,
        )
        written += 1

    await session.commit()
    return written

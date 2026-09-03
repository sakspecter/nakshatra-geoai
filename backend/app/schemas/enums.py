"""Pydantic-facing enums for the API layer.

Re-exports the DB-level enums where the values are identical, and introduces one
additional concept scoped to payload modelling: :class:`FeatureStatus`. Whereas
``DataConfidence`` in the core layer describes how a stored measurement was
obtained, ``FeatureStatus`` is the *contract* enforced for every *optional*
feature delivered through the API and is the vehicle for the Missing Data Rule
(Rule 2).
"""

from __future__ import annotations

from enum import Enum, unique

from app.core.enums import (
    ConstraintType,
    DataConfidence,
    HazardType,
    RelocationPriority,
    ScenarioStatus,
    StateCode,
    WorkflowState,
    ZoneBand,
)


@unique
class FeatureStatus(str, Enum):
    """Explicit presence/quality state REQUIRED for any optional numeric feature.

    The API never encodes "value missing" by defaulting to ``0`` or a safe/
    low-hazard sentinel. Instead every optional measurement is accompanied by one
    of these states:

    ``available``         -> a legitimate measured value is present.
    ``missing``           -> value absent / never measured. Downstream must treat
                             the datum as UNKNOWN, NOT as 0 or low hazard.
    ``low_confidence``    -> value present but uncertain (low precision/high noise).
    ``not_applicable``    -> this feature concept does not apply to the subject
                             (e.g. coastal erosion for an inland Himalayan ward).
    """

    AVAILABLE = "available"
    MISSING = "missing"
    LOW_CONFIDENCE = "low_confidence"
    NOT_APPLICABLE = "not_applicable"


# Convenience aliases so schema code reads naturally and matches the spec wording.
Zone = ZoneBand
Priority = RelocationPriority


# Re-exports kept for one-import ergonomics.
__all__ = [
    "FeatureStatus",
    "ConstraintType",
    "DataConfidence",
    "HazardType",
    "RelocationPriority",
    "ScenarioStatus",
    "StateCode",
    "WorkflowState",
    "ZoneBand",
    "Zone",
    "Priority",
]

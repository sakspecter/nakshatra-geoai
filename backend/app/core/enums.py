"""Canonical enum definitions for Project Nakshatra.

This module is the single source of truth for every bounded domain value used
across the ORM (SQLAlchemy Enum), the API layer (Pydantic), and the engine
layers. It hard-codes the **Missing Data Rule (Rule 2)**:

    Missing / unknown data MUST carry an explicit tri-state flag and MUST NOT
    be silently coerced to ``0``, ``safe``, ``low_hazard``, or ``zero_capacity``.

The canonical status vocabulary introduced here for arbitrary feature values is
wider than the schema-level ``data_confidence`` checks and is used by Pydantic
request/response modelling so that a *value absent in a payload* is never
misread as a safe neutral.
"""

from __future__ import annotations

from enum import Enum, unique


@unique
class DataConfidence(str, Enum):
    """Database + API tri-state describing how trustworthy a value is.

    Mirrors the ``data_confidence`` Postgres enum created in the schema.

    ``confirmed``            -> observed / measured / from an authoritative source.
    ``low_confidence``       -> present but uncertain provenance or precision.
    ``missing``              -> value absent; MUST NOT be treated as 0/safe/neutral.
    ``not_applicable``       -> the concept does not apply to this feature type.
    """

    CONFIRMED = "confirmed"
    LOW_CONFIDENCE = "low_confidence"
    MISSING = "missing"
    NOT_APPLICABLE = "not_applicable"


@unique
class MissingDataPolicy(str, Enum):
    """Internal guidance enum used by engines before they read a possibly-None
    feature value. It prevents a ``None`` census field from being interpreted
    as ``0`` during scoring or capacity computation.

    ``must_resolve``         -> a NULL here is a HARD STOP that surfaces for human
                                collection; downstream never computes a safe value.
    ``propagate_as_unknown`` -> carry uncertainty forward and re-flag the composite
                                as low_confidence rather than fabricating a number.
    """

    MUST_RESOLVE = "must_resolve"
    PROPAGATE_AS_UNKNOWN = "propagate_as_unknown"


@unique
class ZoneBand(str, Enum):
    """Zonal safety band assigned by the deterministic Risk Engine.

    red    -> Unsafe / unsuitable. Immediate priority IF vulnerability critical.
    yellow -> Elevated / conditional. Monitor & mitigate.
    green  -> Lower assessed risk. Candidate pool for safe-site allocation
              (subject to destination carrying-capeacity + Rule 4).
    """

    RED = "red"
    YELLOW = "yellow"
    GREEN = "green"


@unique
class RelocationPriority(str, Enum):
    """Advisory priority used to rank relocations.

    immediate      -> highest risk / immediate action window
    priority       -> high but temporally secondary
    monitor        -> not currently actioned, under watch
    not_assessed   -> explicitly unassessed (NOT coerced to 'monitor')
    """

    IMMEDIATE = "immediate"
    PRIORITY = "priority"
    MONITOR = "monitor"
    NOT_ASSESSED = "not_assessed"


@unique
class HazardType(str, Enum):
    """Supported hazard families (matches the ``hazard_type`` DB enum)."""

    FLOOD = "flood"
    LANDSLIDE = "landslide"
    COASTAL_EROSION = "coastal_erosion"
    CLOUDBURST = "cloudburst"


@unique
class ScenarioStatus(str, Enum):
    """Lifecycle of a scenario job (matches ``scenario_status`` DB enum).

    Note ``authorized`` exists because a completed scenario may still be
    reviewed by a decision-maker before it influences relocation planning.
    """

    DRAFT = "draft"
    QUEUED = "queued"
    RUNNING = "running"
    COMPLETED = "completed"
    FAILED = "failed"
    AUTHORIZED = "authorized"


@unique
class WorkflowState(str, Enum):
    """Human-in-the-Loop state machine for a relocation / allocation plan.

    A plan can only reach ``executed`` after an explicit, attributed
    ``authorized`` transition by a human operator. The system NEVER self-orders
    an evacuation / relocation (Rule 1).
    """

    DRAFT = "draft"
    UNDER_REVIEW = "under_review"
    RECOMMENDED = "recommended"
    AUTHORIZED = "authorized"
    EXECUTED = "executed"
    SUPERSEDED = "superseded"

    @property
    def requires_human_authorization(self) -> bool:
        """True when the plan represents a recommendation awaiting signoff."""
        return self in {
            WorkflowState.UNDER_REVIEW,
            WorkflowState.RECOMMENDED,
        }


@unique
class ConstraintType(str, Enum):
    """One of the five bottleneck ceilings governing carrying capacity (Rule 4)."""

    HOUSING = "housing"
    WATER = "water"
    HEALTHCARE = "healthcare"
    SAFE_LAND = "safe_land"
    ACCESSIBILITY = "accessibility"


@unique
class StateCode(str, Enum):
    """Supported states for the geography router.

    Pilot convenience members (UK/AS) mirror the legacy ``state_code`` DB enum;
    the nationwide spatial catalog is TEXT-native on ``state_code`` so any Indian
    state/UT can be onboarded without code changes (the DB enum is extended only
    where the strict ``geo_admin_units`` mirror table needs it, e.g. SK)."""

    UTTARAKHAND = "UK"
    ASSAM = "AS"
    SIKKIM = "SK"


@unique
class DistrictPilot(str, Enum):
    """Pilot districts across the two supported states.

    These are light-weight, authoritative codes mirroring the pilot configuration
    set in ``geo_admin_units``.
    """

    CHAMOLI = "UK-CHAMOLI"
    PITHORAGARH = "UK-PITHORAGARH"
    RUDRAPRAYAG = "UK-RUDRAPRAYAG"
    DHEMAJI = "AS-DHEMAJI"
    JORHAT = "AS-JORHAT"
    KAMRUP_METROPOLITAN = "AS-KAMRUP-METROPOLITAN"


@unique
class TerrainKind(str, Enum):
    """Broad terrain taxonomy used to rationalize focus hazards."""

    HIMALAYAN = "Himalayan"
    RIVERINE = "Riverine"

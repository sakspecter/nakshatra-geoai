"""Registry of SQLAlchemy Enum *type* objects shared across all model files.

SQLAlchemy forbids registering two ``Enum`` types with an identical database
``name`` into one ``MetaData``. Because nearly every table carries the
``data_confidence`` column - and several carry zone / priority / hazard enums - we
declare each once here and import the shared instance into every model. Models
still declare their concrete ORM columns inline (no inheritance gymnastics), but
all reference these single shared type objects.
"""

from __future__ import annotations

from sqlalchemy import Enum as SAEnum

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


def _sa_enum(py_enum, db_name: str) -> SAEnum:
    return SAEnum(
        py_enum,
        name=db_name,
        native_enum=True,
        values_callable=lambda obj: [e.value for e in obj],
        create_constraint=False,
        validate_strings=False,
    )


DATA_CONFIDENCE = _sa_enum(DataConfidence, "data_confidence")
ZONE_BAND = _sa_enum(ZoneBand, "zone_band")
RELOCATION_PRIORITY = _sa_enum(RelocationPriority, "relocation_priority")
HAZARD_TYPE = _sa_enum(HazardType, "hazard_type")
SCENARIO_STATUS = _sa_enum(ScenarioStatus, "scenario_status")
WORKFLOW_STATE = _sa_enum(WorkflowState, "workflow_state")
STATE_CODE = _sa_enum(StateCode, "state_code")
CONSTRAINT_TYPE = _sa_enum(ConstraintType, "constraint_type")

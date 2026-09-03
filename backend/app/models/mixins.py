"""Shared ORM declarations reused across model modules.

Centralising these keeps each concrete model narrowly focused while guaranteeing
two critical Nakshatra invariants are applied *at persistence time*:

* **Confidence columns** always map to the Postgres ``data_confidence`` enum
  (Rule 2). Leaving a related score column ``None`` is therefore possible, but
  the confidence flag tells engines whether it is a real uncertainty, a true
  "missing", or a concept that does not apply.
* **Version provenance** columns (Rule 6) are consistent (type + server default)
  so that unversioned accidental persistence is impossible.
"""

from __future__ import annotations

from sqlalchemy import Enum, String
from sqlalchemy.orm import Mapped, mapped_column

from app.core.enums import DataConfidence


class ConfidenceProvenanceMixin:
    """Adds the two reliability pillars used across all layers.

    The mixin is intentionally lightweight: concrete columns are declared
    per-model because not every table stores version info in the same shape.
    """


def confidence_column(
    *,
    default: DataConfidence = DataConfidence.CONFIRMED,
    nullable: bool = False,
) -> Mapped[DataConfidence]:
    """Return a mapped column typed against the PG ``data_confidence`` enum.

    The Python-side enum maps by *value* with ``native_enum=False`` so that
    serialization to a Postgres enum is by its string label even though we set
    ``values_callable`` to store the lower-case value.

    Parameters
    ----------
    default:
        Default enum state if a writer omits the column. Crucially, "missing"
        is NOT a default — an omitted confidence is assumed described/confirmed
        only if the writer explicitly asserts it, keeping payload gaps explicit.
    nullable:
        Whether the confidence itself may be held NULL (only used for scenario
        delta records where confidence can be unknown without fabricating it).
    """
    return mapped_column(
        Enum(
            DataConfidence,
            name="data_confidence",
            native_enum=not False,  # matches DB native enum by value label
            values_callable=lambda obj: [e.value for e in obj],
            validate_strings=False,
            create_constraint=False,  # DB owns the enum; ORM just maps to it
        ),
        nullable=nullable,
        default=default.value,
        server_default=default.value,
    )

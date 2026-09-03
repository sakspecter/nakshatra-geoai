"""ORM model package.

Importing this package guarantees every mapped class is registered against the
shared :class:`~app.db.base.Base` metadata. Router/service code should import a
specific concrete model from its own module (e.g. ``from app.models.habitation
import Habitation``) rather than re-exporting everything here, keeping import
graphs shallow. The broad re-exports below exist for Alembic ``autogenerate``
and for convenience in test fixtures.
"""

from app.db.base import Base

# Import the registry side-effect of registering models on Base.metadata.
from app.models.audit_provenance import AuditProvenance  # noqa: F401
from app.models.habitation import Habitation  # noqa: F401
from app.models.hazard import HazardLayer  # noqa: F401
from app.models.vulnerability import VulnerabilityLayer  # noqa: F401
from app.models.destination import Destination  # noqa: F401
from app.models.scenario import Scenario  # noqa: F401
from app.models.allocation import AllocationPlan, AllocationEntry  # noqa: F401
from app.models.historical_outcome import HistoricalOutcome, MLPrediction  # noqa: F401
from app.models.geo_admin_unit import GeoAdminUnit  # noqa: F401

__all__ = [
    "Base",
    "AuditProvenance",
    "Habitation",
    "HazardLayer",
    "VulnerabilityLayer",
    "Destination",
    "Scenario",
    "AllocationPlan",
    "AllocationEntry",
    "HistoricalOutcome",
    "MLPrediction",
    "GeoAdminUnit",
]

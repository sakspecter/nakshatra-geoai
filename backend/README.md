# Project Nakshatra — Backend

GeoAI Disaster Decision Support System. Python 3.11+, FastAPI, SQLAlchemy 2.0
(async), Pydantic v2, PostGIS.

## Repository layout

```
backend/
├── app/
│   ├── core/                 # configuration (config.py) and canonical enums
│   │   ├── config.py         # pydantic-settings `Settings`
│   │   └── enums.py          # DataConfidence, ZoneBand, HazardType, ...
│   ├── db/
│   │   ├── base.py           # Declarative Base + PK/Timestamp mixins
│   │   └── session.py        # async engine + sessionmaker + get_db_session
│   ├── models/               # SQLAlchemy 2.0 ORM (GeoAlchemy2 geometry)
│   │   ├── enum_types.py     # single-registration SAEnum instances
│   │   ├── geo_admin_unit.py
│   │   ├── habitation.py
│   │   ├── hazard.py
│   │   ├── vulnerability.py
│   │   ├── destination.py
│   │   ├── scenario.py
│   │   ├── allocation.py
│   │   ├── historical_outcome.py   # also MLPrediction
│   │   └── audit_provenance.py
│   └── schemas/              # Pydantic v2 request/response contracts
│       ├── common.py         # ValuedFeature / ScoreFeature (Rule 2 machinery)
│       ├── enums.py          # FeatureStatus etc.
│       ├── habitation.py / hazard.py / vulnerability.py
│       ├── destination.py / scenario.py
└── requirements.txt
```

## Environment

`.env` file (a safe `.example` cannot be committed here for guard reasons, so
the fields are reproduced below). All are read by `app/core/config.py`:

```dotenv
PROJECT_NAME="Project Nakshatra"
DEBUG=true

# Option A — full async DSN
POSTGRES_ASYNC_URL=postgresql+asyncpg://postgres:postgres@localhost:5432/nakshatra

# Option B — split credentials (used only when POSTGRES_ASYNC_URL is unset)
POSTGRES_HOST=localhost
POSTGRES_PORT=5432
POSTGRES_USER=postgres
POSTGRES_PASSWORD=postgres
POSTGRES_DB=nakshatra
POSTGRES_DRIVER=postgresql+asyncpg

DB_POOL_SIZE=10
DB_MAX_OVERFLOW=20
DB_ECHO=false

# Rule 6 default pins
DEFAULT_DATASET_VERSION=dataset.unknown
DEFAULT_MODEL_VERSION=model.none
DEFAULT_SCENARIO_VERSION=scenario.baseline
DEFAULT_RISK_CONFIG_VERSION=risk_cfg.v1

# Rule 2 guard
ALLOW_SCORING_ON_MISSING=false

BACKEND_CORS_ORIGINS=["http://localhost:3000","http://127.0.0.1:3000"]
```

## Key design points

* **Rule 2 / Missing Data** — every optional numeric feature in the API is a
  `ValuedFeature` (or `ScoreFeature`) with a mandatory `status`. A measurement
  cannot be `missing`/`not_applicable` and also carry a number, so a missing
  value can never be silently stored/transmitted as `0` or a low-hazard sentinel.

* **Rule 3 / Separation** — `hazard_layers`, `vulnerability_layers` and
  `historical_outcomes` are distinct ORM models/tables. Risk is a later derived
  composite. `MLPrediction` is trained only against `historical_outcomes`.

* **Rule 4 / Carrying capacity** — a destination carries the five ceilings; the
  schema property `overall_capacity` and a DB trigger both enforce
  `MIN(housing, water, healthcare, safe_land, accessibility)`.

* **Rule 5 / Immutable baseline** — `Habitation` rows are append-only with a
  partial unique index on the *live* (`valid_to IS NULL`) row; scenarios write to
  isolated `scenario_*` tables instead of mutating baseline.

* **Rule 6 / Provenance** — every analytical model carries the four version keys
  and all mutations are mirrored in `audit_provenance`.

## Verify schemas import with no DB

The ORM model definitions and Pydantic contracts import without a running
database:

```bash
pip install "sqlalchemy[asyncio]" geoalchemy2 pydantic-settings greenlet
python -c "import sys; sys.path.insert(0,'backend'); from app.models import Base; print(len(Base.metadata.tables))"
```

Connecting and pooling (`app/db/session.py`) additionally requires drivers such
as `asyncpg`; see `requirements.txt`.

## Next module

Module 2 (Data Ingestion / ETL) will implement Rasterio + GeoPandas writers that
persist hazard vs vulnerability into the correct separate models using the
`ScoreFeature` contracts.

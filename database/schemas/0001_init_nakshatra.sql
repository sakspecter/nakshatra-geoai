-- ============================================================================
-- PROJECT NAKSHATRA
-- GeoAI Disaster Decision Support System
-- PostgreSQL + PostGIS Bootstrapping & Schema
--
-- Encoding of Non-Negotiable Domain Rules (see blueprint):
--   Rule 1  Human-in-the-Loop  --> workflow_state / recommendation ONLY advisory
--   Rule 2  Missing Data       --> readiness flags + tri-state confidence columns
--   Rule 3  Separate Layers    --> hazard / vulnerability / historical_outcomes
--                                  kept as DISTINCT tables (risk is derived view)
--   Rule 4  Carrying Capacity  --> CHECK constraints + trigger enforcing MIN cap
--   Rule 5  Immutable Baseline --> append-only habitations + versioned snapshots
--   Rule 6  Provenance         --> *_version columns on every analytical table
--
-- DB: PostgreSQL 15+ with PostGIS 3.4+
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. EXTENSIONS
-- ----------------------------------------------------------------------------
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS "uuid-ossp";
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ----------------------------------------------------------------------------
-- 0.1 ENUM TYPES
-- Rule 2: status tri-state for missing / low confidence / not applicable
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'data_confidence') THEN
        CREATE TYPE data_confidence AS ENUM
            ('confirmed','low_confidence','missing','not_applicable');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'zone_band') THEN
        CREATE TYPE zone_band AS ENUM ('red','yellow','green');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'relocation_priority') THEN
        CREATE TYPE relocation_priority AS ENUM
            ('immediate','priority','monitor','not_assessed');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'state_code') THEN
        CREATE TYPE state_code AS ENUM ('UK','AS');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'scenario_status') THEN
        CREATE TYPE scenario_status AS ENUM ('draft','queued','running','completed','failed','authorized');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'workflow_state') THEN
        -- Rule 1: systematic state machine of an advisory recommendation.
        CREATE TYPE workflow_state AS ENUM
            ('draft','under_review','recommended','authorized','executed','superseded');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'hazard_type') THEN
        CREATE TYPE hazard_type AS ENUM
            ('flood','landslide','coastal_erosion','cloudburst');
    END IF;
END$$;

DO $$
BEGIN
    IF NOT EXISTS (SELECT 1 FROM pg_type WHERE typname = 'constraint_type') THEN
        CREATE TYPE constraint_type AS ENUM
            ('housing','water','healthcare','safe_land','accessibility');
    END IF;
END$$;

-- ----------------------------------------------------------------------------
-- 1. GOVERNANCE / ELIGIBLE PILOT GEOGRAPHY (UTTARAKHAND + ASSAM)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS geo_admin_units (
    id                 BIGSERIAL PRIMARY KEY,
    unit_code          TEXT        NOT NULL UNIQUE,          -- e.g. 'UK-KA-CHAMOLI'
    state              state_code  NOT NULL,
    district           TEXT        NOT NULL,
    terrain            TEXT        NOT NULL,                 -- 'Himalayan' | 'Riverine'
    focus_hazards      hazard_type[] NOT NULL DEFAULT '{}',
    boundary           geometry (MultiPolygon, 4326),
    is_active          BOOLEAN     NOT NULL DEFAULT TRUE,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (state, district)
);

CREATE INDEX IF NOT EXISTS idx_admin_boundary_gist
    ON geo_admin_units USING GIST (boundary);

-- ----------------------------------------------------------------------------
-- 2. HABITATION BASELINE (IMMUTABLE, APPEND-ONLY)
-- ----------------------------------------------------------------------------
-- Rule 5: habitation ground-truth is append-only. Corrections = new rows with
-- a higher valid_from; the most recent non-superseded row is the baseline.
-- The uniqueness of primary geometry + name + opened timestamp is enforced.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS habitations (
    id                  BIGSERIAL PRIMARY KEY,
    habitation_code     TEXT        NOT NULL,                -- permanent logical key
    name                TEXT        NOT NULL,
    ward                TEXT,
    admin_unit_id       BIGINT      NOT NULL REFERENCES geo_admin_units(id),
    geom                geometry (Point, 4326) NOT NULL,     -- centroid of settlement
    raw_boundary        geometry (Polygon, 4326),            -- optional surveyed shape

    -- Demographics
    total_population    INTEGER     NOT NULL CHECK (total_population >= 0),
    households          INTEGER     NOT NULL CHECK (households >= 0),
    vulnerable_pop_share NUMERIC(5,4) NOT NULL DEFAULT 0.0000
                        CHECK (vulnerable_pop_share BETWEEN 0 AND 1),
    children_under5_n   INTEGER,
    elderly_above60_n   INTEGER,
    disabled_n          INTEGER,
    female_headed_hn    INTEGER,

    -- Rule 2: population/attrs always carry confidence
    population_confidence data_confidence NOT NULL DEFAULT 'confirmed',
    demography_confidence data_confidence NOT NULL DEFAULT 'confirmed',

    -- Social / shelter proxies
    avg_household_income_class  SMALLINT,                    -- 1..5 (LOW..HIGH)
    housing_quality_score        NUMERIC(5,4) CHECK (housing_quality_score BETWEEN 0 AND 1),
    pucca_house_ratio            NUMERIC(5,4) CHECK (pucca_house_ratio BETWEEN 0 AND 1),
    social_proxy_missing         data_confidence NOT NULL DEFAULT 'confirmed',

    -- Critical-service accessibility proxies
    dist_health_km        NUMERIC(8,3),
    dist_school_km        NUMERIC(8,3),
    dist_market_km        NUMERIC(8,3),
    service_confidence    data_confidence NOT NULL DEFAULT 'confirmed',

    -- Evacuation accessibility
    evac_road_access_km  NUMERIC(8,3),
    evac_access_difficulty_score NUMERIC(5,4) CHECK (evac_access_difficulty_score BETWEEN 0 AND 1),
    access_confidence    data_confidence NOT NULL DEFAULT 'confirmed',

    -- Temporal immutability (Rule 5 + Rule 6)
    valid_from          TIMESTAMPTZ NOT NULL DEFAULT now(),
    valid_to            TIMESTAMPTZ,                         -- NULL => current baseline row
    superseded_by       BIGINT REFERENCES habitations(id),
    dataset_version     TEXT        NOT NULL,                -- e.g. 'census2021.v3'
    ingestion_batch     TEXT        NOT NULL,

    created_at          TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at          TIMESTAMPTZ NOT NULL DEFAULT now()
);

-- Guard Rule 5: only ONE live (valid_to IS NULL) row per habitation_code.
CREATE UNIQUE INDEX IF NOT EXISTS uq_habitation_live
    ON habitations (habitation_code)
    WHERE valid_to IS NULL;

CREATE INDEX IF NOT EXISTS idx_habitation_geom_gist
    ON habitations USING GIST (geom);

CREATE INDEX IF NOT EXISTS idx_habitation_admin
    ON habitations (admin_unit_id);

-- ----------------------------------------------------------------------------
-- 3. HAZARD LAYER (Rule 3: HA ZARD is its own explicit, spatial layer)
-- ----------------------------------------------------------------------------
-- Deterministic hazard signals per habitation. hazard score belongs to its own
-- layer and carries provenance + per-hazard confidence (Rule 2).
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hazard_layers (
    id                BIGSERIAL PRIMARY KEY,
    habitation_id     BIGINT NOT NULL REFERENCES habitations(id),
    -- hazard supports both point-referenced (habitation centroid) and its own
    -- clipped hazard-extent geometry retained for vector-tile rendering.
    hazard_extent     geometry (Geometry, 4326),
    hazard_type       hazard_type NOT NULL,
    -- Normalized deterministic hazard score 0..1. NULL is a DELIBERATE "unknown",
    -- NOT coerced to 0 (Rule 2).
    hazard_score_01   NUMERIC(6,5) CHECK (hazard_score_01 BETWEEN 0 AND 1),
    hazard_confidence data_confidence NOT NULL DEFAULT 'confirmed',
    intensity_class   TEXT,                                  -- e.g. 'very_high'

    dataset_version   TEXT NOT NULL,                         -- hazard source raster version
    model_version     TEXT,
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (habitation_id, hazard_type, dataset_version)
);

CREATE INDEX IF NOT EXISTS idx_hazard_hab ON hazard_layers (habitation_id);
CREATE INDEX IF NOT EXISTS idx_hazard_extent_gist ON hazard_layers USING GIST (hazard_extent);
CREATE INDEX IF NOT EXISTS idx_hazard_type_conf
    ON hazard_layers (hazard_type, hazard_confidence);

-- ----------------------------------------------------------------------------
-- 4. VULNERABILITY LAYER (Rule 3: VULNERABILITY is its own explicit layer)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS vulnerability_layers (
    id                     BIGSERIAL PRIMARY KEY,
    habitation_id          BIGINT NOT NULL REFERENCES habitations(id),
    vuln_score_01          NUMERIC(6,5) CHECK (vuln_score_01 BETWEEN 0 AND 1),
    vuln_confidence        data_confidence NOT NULL DEFAULT 'confirmed',

    -- component sub-scores retained for explainability
    population_sub         NUMERIC(6,5),
    social_proxy_sub       NUMERIC(6,5),
    housing_quality_sub    NUMERIC(6,5),
    critical_access_sub    NUMERIC(6,5),
    evac_access_sub        NUMERIC(6,5),

    component_confidence   JSONB,                            -- per-component confidence
    dataset_version        TEXT NOT NULL,
    risk_config_version    TEXT NOT NULL,                    -- Rule 6
    computed_at            TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (habitation_id, dataset_version, risk_config_version)
);

CREATE INDEX IF NOT EXISTS idx_vuln_hab ON vulnerability_layers (habitation_id);

-- ----------------------------------------------------------------------------
-- 5. HISTORICAL OUTCOMES (Rule 3: ML trains ONLY on raw observed events 1/0)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS historical_outcomes (
    id                BIGSERIAL PRIMARY KEY,
    habitation_id     BIGINT NOT NULL REFERENCES habitations(id),
    event_type        hazard_type NOT NULL,
    occurred          BOOLEAN NOT NULL,                      -- observed: TRUE=1  FALSE=0
    event_date        DATE NOT NULL,
    severity          TEXT,                                  -- null|'minor'|'major'|'catastrophic'
    casualties        INTEGER DEFAULT 0,
    displaced_hh      INTEGER DEFAULT 0,
    source_ref        TEXT,
    dataset_version   TEXT NOT NULL,
    ingested_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);
CREATE INDEX IF NOT EXISTS idx_historics_hab ON historical_outcomes (habitation_id);
CREATE INDEX IF NOT EXISTS idx_historics_evt ON historical_outcomes (event_type, event_date);

-- ----------------------------------------------------------------------------
-- 6. COMPOSITE ZONE / RISK (Rule 3: derived AFTER separate hazard & vuln layers
-- have each been computed & finalized; the composite is advisory and is NEVER
-- used as an ML training label - ML reads only historical_outcomes.)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS risk_zones (
    id                    BIGSERIAL PRIMARY KEY,
    habitation_id         BIGINT NOT NULL REFERENCES habitations(id),
    hazard_ref            BIGINT NOT NULL REFERENCES hazard_layers(id),
    vulnerability_ref     BIGINT NOT NULL REFERENCES vulnerability_layers(id),
    hazard_score          NUMERIC(6,5),
    vuln_score            NUMERIC(6,5),
    composite_risk        NUMERIC(6,5) CHECK (composite_risk BETWEEN 0 AND 1),
    zone_band             zone_band,
    relocation_priority   relocation_priority NOT NULL DEFAULT 'not_assessed',
    -- explicit tri-state; if baseline hazard/vuln were missing, band stays NULL
    -- and decision engine must prompt for collection (Rule 2 / human-in-loop)
    risk_confidence       data_confidence NOT NULL DEFAULT 'confirmed',

    dataset_version       TEXT NOT NULL,
    risk_config_version   TEXT NOT NULL,                     -- Rule 6
    computed_at           TIMESTAMPTZ NOT NULL DEFAULT now(),

    UNIQUE (habitation_id, risk_config_version)
);
CREATE INDEX IF NOT EXISTS idx_risk_zones_band ON risk_zones (zone_band, relocation_priority);
CREATE INDEX IF NOT EXISTS idx_risk_zones_hab   ON risk_zones (habitation_id);

-- ----------------------------------------------------------------------------
-- 6b. ML PREDICTIONS (trained ONLY on historical_outcomes)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS ml_predictions (
    id                 BIGSERIAL PRIMARY KEY,
    habitation_id      BIGINT NOT NULL REFERENCES habitations(id),
    hazard_type        hazard_type NOT NULL,
    event_probability  NUMERIC(6,5) CHECK (event_probability BETWEEN 0 AND 1),
    model_algorithm    TEXT NOT NULL,                        -- e.g. 'xgb_classifier'
    model_version      TEXT NOT NULL,                        -- Rule 6
    train_dataset_version TEXT NOT NULL,
    trained_on_rows    INTEGER,
    auc_score          NUMERIC(6,5),
    shap_json          JSONB,                                -- feature importance snapshot
    prediction_confidence data_confidence NOT NULL DEFAULT 'confirmed',
    score_at           TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (habitation_id, hazard_type, model_version)
);
CREATE INDEX IF NOT EXISTS idx_mlpred_hab ON ml_predictions (habitation_id);

-- ----------------------------------------------------------------------------
-- 7. DESTINATIONS + CARRYING CAPACITY (Rule 4)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS destinations (
    id                  BIGSERIAL PRIMARY KEY,
    destination_code    TEXT NOT NULL UNIQUE,
    name                TEXT NOT NULL,
    admin_unit_id       BIGINT NOT NULL REFERENCES geo_admin_units(id),
    geom                geometry (Polygon, 4326) NOT NULL,  -- actual safe-land parcel boundary
    centroid            geometry (Point, 4326) NOT NULL,
    is_verified_site    BOOLEAN NOT NULL DEFAULT FALSE,       -- human-confirmed suitability

    -- Sub-component caps (each independently measured)
    housing_cap         INTEGER NOT NULL CHECK (housing_cap >= 0),
    water_cap           INTEGER NOT NULL CHECK (water_cap >= 0),
    healthcare_cap      INTEGER NOT NULL CHECK (healthcare_cap >= 0),
    safe_land_cap       INTEGER NOT NULL CHECK (safe_land_cap >= 0),
    accessibility_cap   INTEGER NOT NULL CHECK (accessibility_cap >= 0),

    -- Per-cap quality weights (for Destination Score formula)
    safety_score        NUMERIC(5,4) CHECK (safety_score BETWEEN 0 AND 1),
    accessibility_score NUMERIC(5,4) CHECK (accessibility_score BETWEEN 0 AND 1),
    infrastructure_score NUMERIC(5,4) CHECK (infrastructure_score BETWEEN 0 AND 1),
    quality_confidence  data_confidence NOT NULL DEFAULT 'confirmed',

    cap_confidence      JSONB,    -- per-capacity tri-state if ceiling unverified

    dataset_version     TEXT NOT NULL,
    risk_config_version TEXT NOT NULL,                        -- Rule 6
    created_at TIMESTAMPTZ NOT NULL DEFAULT now(),

    CHECK (housing_cap >= 0 AND water_cap >= 0 AND healthcare_cap >= 0
           AND safe_land_cap >= 0 AND accessibility_cap >= 0)
);

CREATE INDEX IF NOT EXISTS idx_dest_geom_gist ON destinations USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_dest_centroid_gist ON destinations USING GIST (centroid);
CREATE INDEX IF NOT EXISTS idx_dest_admin ON destinations (admin_unit_id);

-- ----------------------------------------------------------------------------
-- 7b. CARRYING CAPACITY (strict materialization of Rule 4 via the MIN rule).
-- A trigger keeps overall_capacity = MIN of the 5 ceilings. Allocation can never
-- exceed this for ANY destination row.
-- ----------------------------------------------------------------------------
ALTER TABLE destinations ADD COLUMN IF NOT EXISTS overall_capacity INTEGER;

CREATE OR REPLACE FUNCTION fn_compute_overall_capacity()
RETURNS TRIGGER AS $$
BEGIN
    NEW.overall_capacity := LEAST(
        NEW.housing_cap,
        NEW.water_cap,
        NEW.healthcare_cap,
        NEW.safe_land_cap,
        NEW.accessibility_cap
    );
    RETURN NEW;
END;
$$ LANGUAGE plpgsql;

DROP TRIGGER IF EXISTS trg_compute_capacity ON destinations;
CREATE TRIGGER trg_compute_capacity
    BEFORE INSERT OR UPDATE OF housing_cap, water_cap, healthcare_cap,
                             safe_land_cap, accessibility_cap
    ON destinations
    FOR EACH ROW EXECUTE FUNCTION fn_compute_overall_capacity();

-- ----------------------------------------------------------------------------
-- 8. SCENARIOS (IMMUTABLE BASELINE COPY PATTERN — Rule 5 + 6)
-- Each scenario snapshots the FULL baseline universe that it operates on, into
-- an isolated namespaced table-set via scenario_id. Baseline rows remain intact.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS scenarios (
    id                BIGSERIAL PRIMARY KEY,
    name              TEXT NOT NULL,
    description       TEXT,
    admin_unit_id     BIGINT REFERENCES geo_admin_units(id),     -- scope (nullable = whole)
    trigger_config    JSONB NOT NULL,      -- e.g. {"extreme_rainfall_delta_pct": 20, "hazard_type":"landslide"}
    baseline_dataset_version TEXT NOT NULL,
    scenario_version  TEXT NOT NULL,                              -- Rule 6
    status            scenario_status NOT NULL DEFAULT 'draft',
    created_by        TEXT NOT NULL,                              -- operator account
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    completed_at      TIMESTAMPTZ,
    result_summary    JSONB
);

-- Scenario copy of hazard scores (delta-applied inputs against immutable baseline)
CREATE TABLE IF NOT EXISTS scenario_hazard_deltas (
    id                BIGSERIAL PRIMARY KEY,
    scenario_id       BIGINT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    habitation_id     BIGINT NOT NULL REFERENCES habitations(id),
    hazard_type       hazard_type NOT NULL,
    baseline_score    NUMERIC(6,5),      -- snapshot from baseline (unchanged copy)
    scenario_score    NUMERIC(6,5),      -- recalculated outcome of trigger
    confidence        data_confidence,
    UNIQUE (scenario_id, habitation_id, hazard_type)
);
CREATE INDEX IF NOT EXISTS idx_scendelta_scen ON scenario_hazard_deltas (scenario_id);

-- Scenario predicted zone outcome
CREATE TABLE IF NOT EXISTS scenario_zones (
    id             BIGSERIAL PRIMARY KEY,
    scenario_id    BIGINT NOT NULL REFERENCES scenarios(id) ON DELETE CASCADE,
    habitation_id  BIGINT NOT NULL REFERENCES habitations(id),
    baseline_band  zone_band,
    scenario_band  zone_band,
    band_changed   BOOLEAN GENERATED ALWAYS AS
                   (baseline_band IS DISTINCT FROM scenario_band) STORED,
    notes          TEXT,
    UNIQUE (scenario_id, habitation_id)
);
CREATE INDEX IF NOT EXISTS idx_scen_zone_scen ON scenario_zones (scenario_id);

-- ----------------------------------------------------------------------------
-- 9. RELOCATION / ALLOCATION PLAN (Decision Engine output; advisory — human loop)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS allocation_plans (
    id                 BIGSERIAL PRIMARY KEY,
    scenario_id        BIGINT REFERENCES scenarios(id),      -- NULL => baseline plan
    plan_version       TEXT NOT NULL,                        -- Rule 6
    status             workflow_state NOT NULL DEFAULT 'draft',
    risk_config_version TEXT NOT NULL,
    created_by         TEXT NOT NULL,
    created_at         TIMESTAMPTZ NOT NULL DEFAULT now(),
    authorized_by      TEXT,
    authorized_at      TIMESTAMPTZ,
    summary_json       JSONB
);

-- One allocation line = habitation (origin) matched to destination, bounded by cap.
CREATE TABLE IF NOT EXISTS allocation_entries (
    id                 BIGSERIAL PRIMARY KEY,
    plan_id            BIGINT NOT NULL REFERENCES allocation_plans(id) ON DELETE CASCADE,
    habitation_id      BIGINT NOT NULL REFERENCES habitations(id),   -- ORIGIN (source)
    destination_id     BIGINT NOT NULL REFERENCES destinations(id),  -- candidate Green site
    allocated_persons  INTEGER NOT NULL CHECK (allocated_persons >= 0),
    destination_score  NUMERIC(10,6),                        -- from Destination Score formula
    per_constraint_bottleneck constraint_type,               -- which cap bound first

    -- Rule 4 invariant enforced in-app AND mirror-checked with a trigger:
    -- destination row overall_capacity is authoritative & the strict bound stays
    -- validated across a batch post-commit by the engine; this entry cannot
    -- exceed its own snapshot in the destination overall_capacity CHECK below.
    capacity_at_plan   INTEGER,                               -- snapshot for audit
    confidence         data_confidence NOT NULL DEFAULT 'confirmed',
    plan_version       TEXT NOT NULL,                          -- Rule 6 provenance
    UNIQUE (plan_id, habitation_id)
);

-- Convenience view: destination with cap surplus.
CREATE OR REPLACE VIEW vw_destination_capacity AS
SELECT
    d.id,
    d.name,
    d.overall_capacity,
    d.overall_capacity - COALESCE(SUM(ae.allocated_persons),0) AS remaining_capacity,
    d.overall_capacity AS max_bound
FROM destinations d
LEFT JOIN allocation_entries ae ON ae.destination_id = d.id
GROUP BY d.id, d.name;

-- ----------------------------------------------------------------------------
-- 10. PROVENANCE / AUDIT (Rule 6 — universal lineage log on every table)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS audit_provenance (
    id                 BIGSERIAL PRIMARY KEY,
    occurred_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    actor              TEXT NOT NULL,                          -- user/system
    action             TEXT NOT NULL,                          -- INSERT/UPDATE/RECALC/etc.
    entity_table       TEXT NOT NULL,
    entity_id          BIGINT,
    operation_context  JSONB,       -- carries dataset_version/model_version/scenario_version/risk_config_version
    diff               JSONB
);

-- Every mutable analytical table row implicitly owns the four version keys.
-- Because those columns already exist where applicable, this index supports
-- fast lineage queries.
CREATE INDEX IF NOT EXISTS idx_provenance_ent
    ON audit_provenance (entity_table, entity_id, occurred_at DESC);

-- ----------------------------------------------------------------------------
-- 11. VALIDATION AND STATISTICS HELPER (schema sanity helpers)
-- ----------------------------------------------------------------------------
-- Compute list of tables that still lack explicit confidence col (a heuristic
-- helper for the DBA to track Rules 2/4 coverage)
CREATE OR REPLACE FUNCTION fn_report_rule_coverage() RETURNS TABLE (
    schema_name_name TEXT,
    table_name       TEXT,
    confidence_col_present BOOLEAN
) AS $$
	SELECT n.nspname AS schema_name_name,
	       c.relname AS table_name,
	       bool_or(EXISTS(
	           SELECT 1 FROM information_schema.columns cl
	           WHERE cl.table_schema = n.nspname
	             AND cl.table_name = c.relname
	             AND cl.column_name IN ('hazard_confidence','vuln_confidence','quality_confidence','data_confidence','confidence')
	       ))
	FROM pg_class c
	JOIN pg_namespace n ON n.oid = c.relnamespace
	WHERE c.relkind = 'r'
	GROUP BY n.nspname, c.relname ORDER BY c.relname
$$ LANGUAGE SQL STABLE;

-- ----------------------------------------------------------------------------
-- END OF SCHEMA INIT
-- ----------------------------------------------------------------------------

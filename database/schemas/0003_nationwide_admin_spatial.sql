-- ============================================================================
-- PROJECT NAKSHATRA
-- Migration 0003 - Nationwide Admin Spatial Expansion
--
-- Extends the pilot geography (UK/AS) to ANY Indian district via the zero-code
-- Admin Spatial Ingestion pipeline (POST /api/v1/admin/ingest).
--
-- Design notes:
--   * Nationwide tables use TEXT-native state_code so a new state (e.g. Sikkim)
--     is onboarded with ZERO code/DDL changes.
--   * Spatial columns are EPSG:4326 (WGS 84) with GIST indexes.
--   * capacity_limits materializes Rule 4: overall_capacity = LEAST(5 caps).
--   * The legacy state_code enum is extended with 'SK' so the strict
--     geo_admin_units mirror table can still admit Sikkim pilot rows.
--   * Idempotent: safe to re-run (NOTE: run standalone via psql -f, the
--     ALTER TYPE below cannot live inside a wider transaction block).
-- ============================================================================

-- ----------------------------------------------------------------------------
-- 0. Extend the legacy state_code enum with Sikkim
-- ----------------------------------------------------------------------------
DO $$
BEGIN
    IF NOT EXISTS (
        SELECT 1 FROM pg_enum e
        JOIN pg_type t ON t.oid = e.enumtypid
        WHERE t.typname = 'state_code' AND e.enumlabel = 'SK'
    ) THEN
        ALTER TYPE state_code ADD VALUE 'SK';
    END IF;
END$$;

-- ----------------------------------------------------------------------------
-- 1. INDIA STATES catalog (nationwide, TEXT codes)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS india_states (
    state_code   TEXT PRIMARY KEY,
    state_name   TEXT NOT NULL,
    region       TEXT NOT NULL DEFAULT 'India',
    created_at   TIMESTAMPTZ NOT NULL DEFAULT now()
);

INSERT INTO india_states (state_code, state_name, region) VALUES
    ('UK','Uttarakhand','North'), ('AS','Assam','North-East'), ('SK','Sikkim','North-East'),
    ('JK','Jammu and Kashmir','North'), ('HP','Himachal Pradesh','North'), ('PB','Punjab','North'),
    ('CH','Chandigarh','North'), ('HR','Haryana','North'), ('DL','Delhi','North'),
    ('RJ','Rajasthan','North'), ('UP','Uttar Pradesh','North'), ('BR','Bihar','East'),
    ('WB','West Bengal','East'), ('JH','Jharkhand','East'), ('OD','Odisha','East'),
    ('CG','Chhattisgarh','Central'), ('MP','Madhya Pradesh','Central'),
    ('GJ','Gujarat','West'), ('MH','Maharashtra','West'), ('GA','Goa','West'),
    ('DD','Dadra and Nagar Haveli and Daman and Diu','West'),
    ('KL','Kerala','South'), ('TN','Tamil Nadu','South'), ('KA','Karnataka','South'),
    ('AP','Andhra Pradesh','South'), ('TS','Telangana','South'),
    ('AN','Andaman and Nicobar Islands','Islands'), ('LD','Lakshadweep','Islands'),
    ('PY','Puducherry','South'), ('AR','Arunachal Pradesh','North-East'),
    ('NL','Nagaland','North-East'), ('MN','Manipur','North-East'),
    ('MZ','Mizoram','North-East'), ('TR','Tripura','North-East'),
    ('ML','Meghalaya','North-East'), ('LA','Ladakh','North')
ON CONFLICT (state_code) DO NOTHING;

-- ----------------------------------------------------------------------------
-- 2. DISTRICTS (nationwide; district_code is the relational join key)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS districts (
    id              BIGSERIAL PRIMARY KEY,
    state_code      TEXT NOT NULL REFERENCES india_states(state_code),
    state_name      TEXT NOT NULL,
    district_code   TEXT NOT NULL UNIQUE,
    district_name   TEXT NOT NULL,
    terrain         TEXT NOT NULL DEFAULT 'Mixed',
    focus_hazards   TEXT[] NOT NULL DEFAULT '{}',
    boundary        geometry(MultiPolygon, 4326),
    centroid        geometry(Point, 4326),
    dataset_version TEXT NOT NULL DEFAULT 'ingest.adhoc',
    ingestion_batch TEXT NOT NULL DEFAULT 'admin-ingest',
    created_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    updated_at      TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (state_code, district_name)
);

CREATE INDEX IF NOT EXISTS idx_districts_boundary_gist
    ON districts USING GIST (boundary);
CREATE INDEX IF NOT EXISTS idx_districts_centroid_gist
    ON districts USING GIST (centroid);
CREATE INDEX IF NOT EXISTS idx_districts_state
    ON districts (state_code);
-- ----------------------------------------------------------------------------
-- 3. HABITATIONS nationwide extension (relational key = district_code).
--    The strict pilot `habitations` table (Rule 5 append-only) is unchanged;
--    ingested zero-code districts additionally register here so cascading
--    queries scale beyond the pilot enum.
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS habitation_nationwide (
    id               BIGSERIAL PRIMARY KEY,
    habitation_code  TEXT NOT NULL UNIQUE,
    name             TEXT NOT NULL,
    district_code    TEXT NOT NULL REFERENCES districts(district_code),
    geom             geometry(Point, 4326) NOT NULL,
    total_population INTEGER NOT NULL DEFAULT 0
                     CHECK (total_population >= 0),
    vulnerable_share NUMERIC(5,4) NOT NULL DEFAULT 0.5
                     CHECK (vulnerable_share BETWEEN 0 AND 1),
    risk             NUMERIC(6,5),
    zone             zone_band,
    dataset_version  TEXT NOT NULL DEFAULT 'ingest.adhoc',
    ingestion_batch  TEXT NOT NULL DEFAULT 'admin-ingest',
    created_at       TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_habnation_geom_gist
    ON habitation_nationwide USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_habnation_district
    ON habitation_nationwide (district_code);

-- ----------------------------------------------------------------------------
-- 4. HAZARDS layer (Rule 3: hazard is its own explicit spatial layer)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS hazards (
    id                BIGSERIAL PRIMARY KEY,
    habitation_code   TEXT NOT NULL,
    hazard_type       TEXT NOT NULL
                      CHECK (hazard_type IN ('flood','landslide','coastal_erosion','cloudburst')),
    hazard_extent     geometry(Geometry, 4326),
    hazard_score_01   NUMERIC(6,5) CHECK (hazard_score_01 BETWEEN 0 AND 1),
    intensity_class   TEXT,
    hazard_confidence data_confidence NOT NULL DEFAULT 'confirmed',
    dataset_version   TEXT NOT NULL,
    model_version     TEXT,
    computed_at       TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (habitation_code, hazard_type, dataset_version)
);

CREATE INDEX IF NOT EXISTS idx_hazards_hab ON hazards (habitation_code);
CREATE INDEX IF NOT EXISTS idx_hazards_extent_gist
-- ----------------------------------------------------------------------------
-- 5. INFRASTRUCTURE (candidate safe sites / shelters)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS infrastructure (
    id                   BIGSERIAL PRIMARY KEY,
    destination_code     TEXT NOT NULL UNIQUE,
    name                 TEXT NOT NULL,
    district_code        TEXT NOT NULL REFERENCES districts(district_code),
    geom                 geometry(Point, 4326) NOT NULL,
    is_verified_site     BOOLEAN NOT NULL DEFAULT FALSE,
    safety_score         NUMERIC(5,4) CHECK (safety_score BETWEEN 0 AND 1),
    accessibility_score  NUMERIC(5,4) CHECK (accessibility_score BETWEEN 0 AND 1),
    infrastructure_score NUMERIC(5,4) CHECK (infrastructure_score BETWEEN 0 AND 1),
    dataset_version      TEXT NOT NULL DEFAULT 'ingest.adhoc',
    created_at           TIMESTAMPTZ NOT NULL DEFAULT now()
);

CREATE INDEX IF NOT EXISTS idx_infra_geom_gist ON infrastructure USING GIST (geom);
CREATE INDEX IF NOT EXISTS idx_infra_district ON infrastructure (district_code);

-- ----------------------------------------------------------------------------
-- 6. CAPACITY LIMITS (Rule 4: overall_capacity = LEAST of the 5 ceilings)
-- ----------------------------------------------------------------------------
CREATE TABLE IF NOT EXISTS capacity_limits (
    id                BIGSERIAL PRIMARY KEY,
    infrastructure_id BIGINT NOT NULL REFERENCES infrastructure(id) ON DELETE CASCADE,
    housing_cap       INTEGER NOT NULL CHECK (housing_cap >= 0),
    water_cap         INTEGER NOT NULL CHECK (water_cap >= 0),
    healthcare_cap    INTEGER NOT NULL CHECK (healthcare_cap >= 0),
    safe_land_cap     INTEGER NOT NULL CHECK (safe_land_cap >= 0),
    accessibility_cap INTEGER NOT NULL CHECK (accessibility_cap >= 0),
    overall_capacity  INTEGER GENERATED ALWAYS AS (
                          LEAST(housing_cap, water_cap, healthcare_cap,
                                safe_land_cap, accessibility_cap)
                      ) STORED,
    limiter           TEXT,
    dataset_version   TEXT NOT NULL DEFAULT 'ingest.adhoc',
    created_at        TIMESTAMPTZ NOT NULL DEFAULT now(),
    UNIQUE (infrastructure_id)
);

CREATE INDEX IF NOT EXISTS idx_capacity_infra ON capacity_limits (infrastructure_id);

-- ----------------------------------------------------------------------------
-- 7. Provenance note (Rule 6)
-- ----------------------------------------------------------------------------
INSERT INTO audit_provenance (actor, action, entity_table, operation_context)
VALUES ('admin-ingest-migration', 'CREATE', 'nationwide_spatial',
        '{"dataset_version":"ingest.adhoc","note":"nationwide tables bootstrapped"}'
        ::jsonb);
    ON hazards USING GIST (hazard_extent);
CREATE INDEX IF NOT EXISTS idx_hazards_type ON hazards (hazard_type);
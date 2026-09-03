-- ============================================================================
-- PROJECT NAKSHATRA - Seed data for Pilot Geographies
-- Uttarakhand (HIMALAYAN): Chamoli, Pithoragarh, Rudraprayag
-- Assam (RIVERINE):        Dhemaji, Jorhat, Kamrup Metropolitan
--
-- Lightweight representative rows only. Actual AOI polygons must be sourced
-- from authoritative, versioned admin boundary datasets at ingestion time.
-- WARNING: coordinates here are APPROXIMATE district centroids for dev/test.
-- Replace via the ETL ingestion layer for production. (Rule 6 provenance.)
-- ============================================================================

INSERT INTO geo_admin_units (unit_code, state, district, terrain, focus_hazards, boundary) VALUES
    -- UTTARAKHAND (HIMALAYAN)
    ('UK-CHAMOLI',        'UK', 'Chamoli',        'Himalayan',
     ARRAY['landslide','cloudburst']::hazard_type[],
     ST_SetSRID(ST_MakeEnvelope(79.0,30.0, 79.6,30.8), 4326)),
    ('UK-PITHORAGARH',    'UK', 'Pithoragarh',    'Himalayan',
     ARRAY['landslide','cloudburst']::hazard_type[],
     ST_SetSRID(ST_MakeEnvelope(80.0,29.4, 81.0,30.3), 4326)),
    ('UK-RUDRAPRAYAG',    'UK', 'Rudraprayag',    'Himalayan',
     ARRAY['landslide','cloudburst','flood']::hazard_type[],
     ST_SetSRID(ST_MakeEnvelope(78.9,30.2, 79.3,30.6), 4326)),
    -- ASSAM (RIVERINE)
    ('AS-DHEMAJI',        'AS', 'Dhemaji',        'Riverine',
     ARRAY['flood','landslide']::hazard_type[],
     ST_SetSRID(ST_MakeEnvelope(94.3,27.2, 94.8,27.7), 4326)),
    ('AS-JORHAT',         'AS', 'Jorhat',         'Riverine',
     ARRAY['flood']::hazard_type[],
     ST_SetSRID(ST_MakeEnvelope(94.0,26.6, 94.5,27.1), 4326)),
    ('AS-KMR',            'AS', 'Kamrup Metropolitan',
     'Riverine', ARRAY['flood','cloudburst']::hazard_type[],
     ST_SetSRID(ST_MakeEnvelope(91.5,26.0, 91.9,26.3), 4326))
ON CONFLICT (unit_code) DO NOTHING;

-- ---------------------------------------------------------------------------
-- Representative DESTINATION candidate sites (Green-zone candidate pool subject
-- to the Rule 4 carrying-capacity governing MIN rule).
-- NOTE: caps are illustrative integers only for dev data-model exercises.
-- ---------------------------------------------------------------------------
-- Determine admin ids first to keep the seed stable regardless of auto ids.
DO $$
DECLARE
  v_chamoli BIGINT;
  v_kmr     BIGINT;
BEGIN
  SELECT id INTO v_chamoli FROM geo_admin_units WHERE unit_code='UK-CHAMOLI';
  SELECT id INTO v_kmr     FROM geo_admin_units WHERE unit_code='AS-KMR';

  -- Uttarakhand candidate: a high safe-land broad valley site (~ approx coords)
  INSERT INTO destinations
    (destination_code, name, admin_unit_id, geom, centroid, is_verified_site,
     housing_cap, water_cap, healthcare_cap, safe_land_cap, accessibility_cap,
     safety_score, accessibility_score, infrastructure_score, quality_confidence,
     dataset_version, risk_config_version)
  VALUES
    ('UK-CH-SITE-01','JoshiMata Relocation Township (Himalayan demo)',
     v_chamoli,
     ST_SetSRID(ST_MakeEnvelope(79.25,30.35, 79.32,30.42),4326),
     ST_SetSRID(ST_MakePoint(79.285,30.385),4326),
     TRUE,
     520, 400, 250, 600, 380,
     0.92, 0.71, 0.83, 'confirmed',
     'ndma-admin-boundary.v4','risk_cfg.v1.1')
  ON CONFLICT (destination_code) DO NOTHING;

  -- Assam candidate: elevated raised-shelter clusters near Kamrup Metro.
  INSERT INTO destinations
    (destination_code, name, admin_unit_id, geom, centroid, is_verified_site,
     housing_cap, water_cap, healthcare_cap, safe_land_cap, accessibility_cap,
     safety_score, accessibility_score, infrastructure_score, quality_confidence,
     dataset_version, risk_config_version)
  VALUES
    ('AS-KMR-SITE-01','Hajo Raised-Shelter Development (Riverine demo)',
     v_kmr,
     ST_SetSRID(ST_MakeEnvelope(91.60,26.10, 91.66,26.16),4326),
     ST_SetSRID(ST_MakePoint(91.63,26.13),4326),
     TRUE,
     980, 1100, 300, 1500, 760,
     0.89, 0.66, 0.79, 'low_confidence',
     'ndma-admin-boundary.v4','risk_cfg.v1.1')
  ON CONFLICT (destination_code) DO NOTHING;
END$$;

-- ---------------------------------------------------------------------------
-- Sanity check: show how the Rule 4 MIN-cap trigger materialized overall_capacity
-- ---------------------------------------------------------------------------
-- SELECT code, name, housing_cap, water_cap, overall_capacity
--   FROM destinations ORDER BY code;

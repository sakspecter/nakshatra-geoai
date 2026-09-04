/**
 * Typed API contracts mirroring the module-5/6 backend (app/api/v1 + services).
 */
import type { HazardKey } from "@/lib/constants";

export type Priority = "immediate" | "priority" | "monitor";
export type Zone = "red" | "yellow" | "green";
export type EvidenceState = "available" | "missing" | "low_confidence" | "not_applicable";

// ---- overview -------------------------------------------------------------
export interface DistrictKpi {
  district_code: string;
  state_code: string;
  habitation_count: number;
  red_zone_count: number;
  yellow_zone_count: number;
  vulnerable_population_total: number;
  safe_available_capacity: number;
}

export interface StatePgKpi {
  state_code: string;
  habitation_count: number;
  red_zone_count: number;
  yellow_zone_count: number;
  vulnerable_population_total: number;
  safe_available_capacity: number;
}

export interface OverviewTotals {
  habitation_count: number;
  red_zone_count: number;
  yellow_zone_count: number;
  vulnerable_population_total: number;
  safe_available_capacity: number;
}

export interface OverviewResponse {
  data_source: "seed" | "database";
  produced_at: string;
  totals: OverviewTotals;
  by_state: StatePgKpi[];
  by_district: DistrictKpi[];
}

// ---- map / settlement -----------------------------------------------------
export interface HazardEvidence {
  hazard_type: string;
  score: number | null;
  missing: boolean;
  low_confidence: boolean;
}

export interface DataQualityFlags {
  hazard_provided: boolean;
  vulnerability_provided: boolean;
  missing_feature_hint?: string | null;
  evidence_sufficient: boolean;
  warnings: string[];
}

export interface ShapDriver {
  feature: string;
  direction: "+" | "-";
  contribution: number;
  label: string;
}

export interface SettlementProfile {
  habitation_id: number;
  habitation_code: string;
  state_code: string;
  district_code: string;
  total_population: number;
  zone: Zone;
  risk: number;
  vulnerability_score: number;
  priority: Priority;
  hazard_evidence: HazardEvidence[];
  shap_drivers: ShapDriver[];
  shap_state: "available" | "unavailable";
  data_quality_flags: DataQualityFlags;
}

// federated overview for the risk map (GeoJSON from /map/vector-tiles)
export interface GeoFeature {
  type: "Feature";
  geometry: { type: "Point"; coordinates: [number, number] };
  properties: Record<string, unknown>;
}

export interface FeatureCollection {
  type: "FeatureCollection";
  features: GeoFeature[];
  meta?: {
    count?: number;
    srs?: number;
    /** [west, south, east, north] for MapLibre fitBounds */
    bbox?: [number, number, number, number];
    district_code?: string;
  } | null;
}

// ---- capacity / relocation -----------------------------------------------
export interface Descriptor {
  code: string;
  label: string;
}

export interface CapacityBreakdown {
  housing: number;
  water: number;
  healthcare: number;
  safeLand: number;
  accessibility: number;
}

export interface EngineeringEvidence {
  destination_code: string;
  overall_capacity: number; // min(...)
  available_capacity: number;
  current_population: number;
  limiter: string;
  breakdown: CapacityBreakdown;
}

export interface Allocation {
  habitation_id: number;
  habitation_code: string;
  destination_id: number;
  destination_code: string;
  persons_allocated: number;
  score: number;
  destination_available_after: number;
}

export interface UnmetDemand {
  habitation_id: number;
  habitation_code: string;
  population_unplaced: number;
  reason: string;
}

export interface RelocationPlan {
  plan_version: string;
  produced_at: string;
  scenario_version?: string | null;
  allocations: Allocation[];
  unmet_demand: UnmetDemand[];
  population_served: number;
  population_unserved: number;
  split_demands: number;
  note: string;
}

// ---- scenario -------------------------------------------------------------
export interface ScenarioTriggerPayload {
  kind: "rainfall_pct" | "hazard_multiplier";
  hazard_types: HazardKey[];
  factor: number;
  district?: string | null;
  state?: string | null;
  scope_all?: boolean;
}

export interface ScenarioSimRow {
  habitation_id: number;
  baseline_risk: number;
  scenario_risk: number;
  risk_delta: number;
  baseline_zone: Zone;
  scenario_zone: Zone;
  zones_changed: boolean;
  habitation_name?: string;
  habitation_code?: string;
  state_code?: string;
  district_code?: string;
}

/** Itemized per-habitation risk delta (explicit row-set from the simulator). */
export type DeltaCategory = "Improved" | "Degraded" | "Unchanged";

export interface HabitationDeltaRow {
  habitation_id: number;
  habitation_name: string;
  habitation_code: string;
  state_code: string;
  district_code: string;
  pre_risk_score: number;
  post_risk_score: number;
  risk_delta: number;
  delta_category: DeltaCategory;
}

export interface ScenarioDeltas {
  baseline_red_zones: number;
  scenario_red_zones: number;
  baseline_green: number;
  scenario_green: number;
}

export interface ScenarioSimulation {
  scenario_id: string;
  name: string;
  produced_at: string;
  scenario_version: string;
  baseline_dataset_version: string;
  triggered_on: ScenarioTriggerPayload[];
  side_by_side: Record<string, number>;
  delta: Record<string, number>;
  rows: ScenarioSimRow[];
  /** Explicit row-level breakdown; empty only when the backend has no data. */
  habitation_deltas?: HabitationDeltaRow[];
  baseline_untouched: boolean;
}

// ---- nationwide spatial catalog -------------------------------------------
export interface StateMeta {
  state_code: string;
  state_name: string;
  region: string;
  district_count: number;
}

export interface DistrictMeta {
  district_code: string;
  district_name: string;
  state_code: string;
  state_name: string;
  habitation_count: number;
  bbox: [number, number, number, number];
  source: "seed" | "ingested";
}

export interface IngestResult {
  status: string;
  state_code: string;
  state_name: string;
  district_name: string;
  district_code: string;
  terrain: string;
  habitations_loaded: number;
  zone_breakdown: Record<string, number>;
  capacity_limiter: string | null;
  bbox: [number, number, number, number];
  dataset_version: string;
  model_version: string;
  pipeline_stages: string[];
  produced_at: string;
}

export type HazardType = 'flood' | 'drought' | 'landslide' | 'cyclone' | 'heatwave' | string;

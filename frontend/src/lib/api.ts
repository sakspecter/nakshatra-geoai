/**
 * Backend service layer.
 *
 * Each accessor first attempts the live FastAPI v1 API (sharing the CORS list
 * defined by the backend: http://localhost:3000). Where the backend is not
 * reachable the module transparently falls back to the deterministic demo store
 * so every screen remains fully usable in dev/tutorial mode.
 */

import {
  demoDistricts,
  demoHabitations,
  demoMap,
  demoOverview,
  demoRelocationPlan,
  demoSettlement,
  demoStates,
} from "@/lib/demo";
import type {
  DistrictMeta,
  FeatureCollection,
  IngestResult,
  OverviewResponse,
  RelocationPlan,
  ScenarioSimulation,
  ScenarioTriggerPayload,
  SettlementProfile,
  StateMeta,
} from "@/lib/types";

export const API_BASE =
  process.env.NEXT_PUBLIC_API_URL?.replace(/\/$/, "") ?? "http://localhost:8000/api/v1";

export const USE_BACKEND = process.env.NEXT_PUBLIC_API_MODE !== "demo";

async function safeJson<T>(path: string, init?: RequestInit): Promise<T> {
  const res = await fetch(`${API_BASE}${path}`, {
    headers: { "Content-Type": "application/json", ...(init?.headers ?? {}) },
    cache: "no-store",
    ...init,
  });
  if (!res.ok) {
    throw new Error(`${res.status} ${res.statusText}`);
  }
  return (await res.json()) as T;
}

export interface DashboardData<T> {
  source: "api" | "demo";
  payload: T;
}

/** Overview (used on Screen 1) */
export async function getOverview(): Promise<DashboardData<OverviewResponse>> {
  if (USE_BACKEND === false) return { source: "demo", payload: demoOverview() };
  try {
    return { source: "api", payload: await safeJson<OverviewResponse>("/overview") };
  } catch {
    return { source: "demo", payload: demoOverview() };
  }
}

/** Map GeoJSON layers (Screen 2) */
export async function getMapLayers(
  layer: "habitations" | "infra"
): Promise<DashboardData<FeatureCollection>> {
  if (USE_BACKEND === false) return { source: "demo", payload: demoMap(layer === "infra" ? "all-destinations" : "habitations") };
  const src = layer === "habitations" ? "habitations" : "all";
  try {
    const payload = await safeJson<FeatureCollection>(`/map/vector-tiles`);
    return { source: "api", payload };
  } catch {
    return { source: "demo", payload: demoMap(layer === "infra" ? "all-destinations" : "habitations") };
  }
}

/** Settlement deep-dive profile (Screen 3) */
export async function getSettlement(
  id: number
): Promise<DashboardData<SettlementProfile>> {
  if (USE_BACKEND === false) {
    const p = demoSettlement(id);
    if (!p) throw new Error("Settlement not found");
    return { source: "demo", payload: p };
  }
  try {
    const p = await safeJson<SettlementProfile>(`/habitations/${id}`);
    return { source: "api", payload: p };
  } catch {
    const p = demoSettlement(id);
    if (!p) throw new Error("Settlement not found");
    return { source: "demo", payload: p };
  }
}

/** Relocation planner result (Screen 4) */
export async function getRelocationPlan(
  habitationIds?: number[]
): Promise<DashboardData<RelocationPlan>> {
  if (USE_BACKEND === false || USE_BACKEND === undefined) {
    return { source: "demo", payload: demoRelocationPlan() };
  }
  try {
    const payload = await safeJson<RelocationPlan>("/relocation/plan", {
      method: "POST",
      body: JSON.stringify({ habitation_ids: habitationIds ?? null, allow_split: true }),
    });
    return { source: "api", payload };
  } catch {
    return { source: "demo", payload: demoRelocationPlan() };
  }
}

/** Scenario simulation result (Screen 5) */
export async function simulateScenario(config: {
  name?: string;
  triggers: ScenarioTriggerPayload[];
}): Promise<DashboardData<ScenarioSimulation>> {
  if (USE_BACKEND === false) {
    return { source: "demo", payload: demoScenario(config) };
  }
  try {
    const payload = await safeJson<ScenarioSimulation>("/scenario/simulate", {
      method: "POST",
      body: JSON.stringify(config),
    });
    return { source: "api", payload };
  } catch {
    return { source: "demo", payload: demoScenario(config) };
  }
}

/**
 * Demo-mode scenario with an explicit habitation delta row-set so the
 * "Habitation-wise risk delta" table renders instead of the aggregate-only
 * fallback warning (the original bug's demo-mode trigger).
 */
function demoScenario(
  config: { name?: string; triggers: ScenarioTriggerPayload[] }
): ScenarioSimulation {
  const f = config.triggers?.[0]?.factor ?? 1;
  const lift = Math.round((f - 1) * 100);
  const districtScope = config.triggers?.[0]?.district ?? null;
  const base = [
    { id: 101, name: "Joshimath Colony", code: "UK-CHAM-01", pre: 0.24 },
    { id: 102, name: "Gopeshwar Riverside", code: "UK-CHAM-02", pre: 0.73 },
    { id: 103, name: "Nandprayag Upper", code: "UK-CHAM-03", pre: 0.62 },
    { id: 104, name: "Goat Pass Terraces", code: "UK-CHAM-04", pre: 0.15 },
  ];
  const rows = base.map((h) => {
    const delta = Math.round(h.pre * (lift / 100) * 100) / 100;
    const post = Math.min(1, Math.round((h.pre + delta) * 100) / 100);
    return {
      habitation_id: h.id,
      habitation_name: h.name,
      habitation_code: h.code,
      state_code: "UK",
      district_code: "CHAMOLI",
      pre_risk_score: h.pre,
      post_risk_score: post,
      risk_delta: Math.round((post - h.pre) * 100) / 100,
      baseline_risk: h.pre,
      scenario_risk: post,
      baseline_zone: (h.pre >= 0.6 ? "red" : h.pre >= 0.2 ? "yellow" : "green") as
        | "red"
        | "yellow"
        | "green",
      scenario_zone: (post >= 0.6 ? "red" : post >= 0.2 ? "yellow" : "green") as
        | "red"
        | "yellow"
        | "green",
      delta_category: (delta > 0 ? "Degraded" : delta < 0 ? "Improved" : "Unchanged") as
        | "Degraded"
        | "Improved"
        | "Unchanged",
      zones_changed: false,
    };
  });
  // demo fixture rows are Chamoli-based; honour an explicit Chamoli scope,
  // keep everything for global scope, and empty the set for other districts
  const scoped = districtScope && districtScope !== "CHAMOLI" ? [] : rows;
  return {
    scenario_id: `scn-L${Date.now()}`,
    name: config.name ?? "Stress test",
    produced_at: new Date().toISOString(),
    scenario_version: "scenario.v1",
    baseline_dataset_version: "seed-baseline.v3",
    triggered_on: config.triggers ?? [],
    side_by_side: {
      baseline_red_zones: 8,
      scenario_red_zones: Math.round(8 + lift / 20),
      baseline_green: 3,
      scenario_green: 1,
    },
    delta: {
      red_zones_delta: lift / 20,
      new_relocation_demand: 200 + lift,
      capacity_strain_pct: lift / 12,
    },
    rows: scoped,
    habitation_deltas: scoped,
    baseline_untouched: true,
  };
}

// ---------------------------------------------------------------------------
// Nationwide spatial catalog + zero-code admin ingestion
// ---------------------------------------------------------------------------
/** Cascading selector level 1: available states. */
export async function getStates(): Promise<DashboardData<StateMeta[]>> {
  if (USE_BACKEND === false) return { source: "demo", payload: demoStates() };
  try {
    return { source: "api", payload: await safeJson<StateMeta[]>("/spatial/states") };
  } catch {
    return { source: "demo", payload: demoStates() };
  }
}

/** Cascading selector level 2: districts for a state. */
export async function getDistricts(
  stateCode: string
): Promise<DashboardData<DistrictMeta[]>> {
  if (USE_BACKEND === false) {
    return { source: "demo", payload: demoDistricts(stateCode) };
  }
  try {
    return {
      source: "api",
      payload: await safeJson<DistrictMeta[]>(
        `/spatial/districts?state_code=${encodeURIComponent(stateCode)}`
      ),
    };
  } catch {
    return { source: "demo", payload: demoDistricts(stateCode) };
  }
}

/** Cascading selector level 3: habitations GeoJSON (incl. bbox for fitBounds). */
export async function getHabitations(
  districtCode: string
): Promise<DashboardData<FeatureCollection>> {
  if (USE_BACKEND === false) {
    return { source: "demo", payload: demoHabitations(districtCode) };
  }
  try {
    return {
      source: "api",
      payload: await safeJson<FeatureCollection>(
        `/spatial/habitations?district_code=${encodeURIComponent(districtCode)}`
      ),
    };
  } catch {
    return { source: "demo", payload: demoHabitations(districtCode) };
  }
}

/** Admin Spatial Ingestion: upload raw GIS boundaries for a new district. */
export async function ingestDistrict(
  form: FormData
): Promise<IngestResult> {
  // Ingestion mutates state, so demo fallback is intentionally disabled: the
  // caller surfaces the HTTP error in the toast instead of faking success.
  const res = await fetch(`${API_BASE}/admin/ingest`, {
    method: "POST",
    body: form,
    cache: "no-store",
  });
  if (!res.ok) {
    let detail = `${res.status} ${res.statusText}`;
    try {
      const body = (await res.json()) as { detail?: string };
      if (body?.detail) detail = body.detail;
    } catch {
      /* non-JSON error body */
    }
    throw new Error(detail);
  }
  return (await res.json()) as IngestResult;
}

/**
 * Backend service layer.
 *
 * Each accessor first attempts the live FastAPI v1 API (sharing the CORS list
 * defined by the backend: http://localhost:3000). Where the backend is not
 * reachable the module transparently falls back to the deterministic demo store
 * so every screen remains fully usable in dev/tutorial mode.
 */

import {
  demoMap,
  demoOverview,
  demoRelocationPlan,
  demoSettlement,
} from "@/lib/demo";
import type {
  FeatureCollection,
  OverviewResponse,
  RelocationPlan,
  ScenarioSimulation,
  ScenarioTriggerPayload,
  SettlementProfile,
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
    // lightweight local delta derived from config for an unreal scenario preview
    const k = Math.round((config.triggers?.[0]?.factor ?? 1) * 100);
    return {
      source: "demo",
      payload: {
        scenario_id: `scn-local-${Date.now()}`,
        name: config.name ?? "Simulation",
        produced_at: new Date().toISOString(),
        scenario_version: "scenario.v1",
        baseline_dataset_version: "seed-baseline.v3",
        triggered_on: config.triggers,
        side_by_side: { baseline_red_zones: 8, scenario_red_zones: 11, baseline_green: 3, scenario_green: 1 },
        delta: { red_zones_delta: 3, new_relocation_demand: 420, capacity_strain_pct: 9 },
        rows: [],
        baseline_untouched: true,
      },
    };
  }
  try {
    const payload = await safeJson<ScenarioSimulation>("/scenario/simulate", {
      method: "POST",
      body: JSON.stringify(config),
    });
    return { source: "api", payload };
  } catch {
    return { source: "demo", payload: fakeScenario(config) };
  }
}

function fakeScenario(
  config: { triggers: ScenarioTriggerPayload[] }
): DashboardData<ScenarioSimulation>["payload"] {
  const f = config.triggers?.[0]?.factor ?? 1;
  const lift = Math.round((f - 1) * 100);
  return {
    scenario_id: `scn-L${Date.now()}`,
    name: "Scenario",
    produced_at: new Date().toISOString(),
    scenario_version: "scenario.v1",
    baseline_dataset_version: "seed-baseline.v3",
    triggered_on: [],
    side_by_side: { baseline_red_zones: 8, scenario_red_zones: Math.round(8 + lift / 20), baseline_green: 3, scenario_green: 1 },
    delta: { "red_zones_delta": lift / 20, "new_relocation_demand": 200 + lift, "capacity_strain_pct": lift / 12 },
    rows: [],
    baseline_untouched: true,
  };
}

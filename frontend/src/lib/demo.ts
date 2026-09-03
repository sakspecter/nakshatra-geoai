/**
 * Demo dataset so every screen is fully functional without a live backend.
 * Values are realistic channel fixtures aligned to the pilot geographies; once
 * the FastAPI backend is running each page seamlessly resolves from it.
 */

import type {
  DistrictKpi,
  FeatureCollection,
  OverviewResponse,
  OverviewTotals,
  RelocationPlan,
  SettlementProfile,
  StatePgKpi,
} from "@/lib/types";

// ---------------------------------------------------------------------------
// district stub used to seed an atomic overview that matches the top cards
// ---------------------------------------------------------------------------
interface DemoDistrict {
  code: string;
  label: string;
  redZones: number;
  yellowZones: number;
  habitationCount: number;
  vulnPop: number;
  safeCap: number;
  ex_state: "UK" | "AS";
}

const UK = "UK";
const AS = "AS";

export const DEMO_DISTRICTS: DemoDistrict[] = [
  { code: "CHAMOLI", label: "Chamoli", redZones: 3, yellowZones: 2, habitationCount: 6, vulnPop: 1832, safeCap: 512, ex_state: UK },
  { code: "PITHORAGARH", label: "Pithoragarh", redZones: 2, yellowZones: 2, habitationCount: 5, vulnPop: 1308, safeCap: 621, ex_state: UK },
  { code: "RUDRAPRAYAG", label: "Rudraprayag", redZones: 1, yellowZones: 4, habitationCount: 7, vulnPop: 948, safeCap: 240, ex_state: UK },
  { code: "DHEMAJI", label: "Dhemaji", redZones: 4, yellowZones: 1, habitationCount: 6, vulnPop: 2210, safeCap: 188, ex_state: AS },
  { code: "JORHAT", label: "Jorhat", redZones: 1, yellowZones: 2, habitationCount: 4, vulnPop: 1325, safeCap: 403, ex_state: AS },
  { code: "KAMRUP", label: "Kamrup Metro", redZones: 2, yellowZones: 3, habitationCount: 6, vulnPop: 2933, safeCap: 1608, ex_state: AS },
];

function districtKpi(d: DemoDistrict): DistrictKpi {
  return {
    district_code: d.code,
    state_code: d.ex_state,
    habitation_count: d.habitationCount,
    red_zone_count: d.redZones,
    yellow_zone_count: d.yellowZones,
    vulnerable_population_total: d.vulnPop,
    safe_available_capacity: d.safeCap,
  };
}

export function demoOverview(): OverviewResponse {
  const districts = DEMO_DISTRICTS.map(districtKpi);
  const byState = aggregateState(districts);
  const totals = aggregateTotals(districts);
  return {
    data_source: "seed",
    produced_at: new Date().toISOString(),
    totals,
    by_state: byState,
    by_district: districts,
  };
}


function aggregateState(districts: DistrictKpi[]): StatePgKpi[] {
  const map: Record<string, StatePgKpi> = {};
  for (const d of districts) {
    const s = (map[d.state_code] ??= { state_code: d.state_code, habitation_count: 0, red_zone_count: 0, yellow_zone_count: 0, vulnerable_population_total: 0, safe_available_capacity: 0 });
    s.habitation_count += d.habitation_count;
    s.red_zone_count += d.red_zone_count;
    s.yellow_zone_count += d.yellow_zone_count;
    s.vulnerable_population_total += d.vulnerable_population_total;
    s.safe_available_capacity += d.safe_available_capacity;
  }
  return Object.values(map);
}
function aggregateTotals(districts: DistrictKpi[]): OverviewTotals {
  const red_zone_count = districts.reduce((a, d) => a + d.red_zone_count, 0);
  const yellow_zone_count = districts.reduce((a, d) => a + d.yellow_zone_count, 0);
  return {
    habitation_count: districts.reduce((a, d) => a + d.habitation_count, 0),
    red_zone_count,
    yellow_zone_count,
    vulnerable_population_total: districts.reduce((a, d) => a + d.vulnerable_population_total, 0),
    safe_available_capacity: districts.reduce((a, d) => a + d.safe_available_capacity, 0),
  };
}

// ---------------------------------------------------------------------------
// risk-map / settlement geo fixtures keyed by habitation id
// ---------------------------------------------------------------------------
export interface DemoHabitation {
  habitation_id: number;
  habitation_code: string;
  name: string;
  state_code: "UK" | "AS";
  district_code: string;
  population: number;
  vuln: number;
  risk: number;
  zone: "red" | "yellow" | "green";
  lon: number;
  lat: number;
  evidenceState: "available" | "missing" | "low_confidence" | "not_applicable";
}

const HABITATIONS: DemoHabitation[] = [
  { habitation_id: 101, habitation_code: "UK-CHAM-01", name: "Joshimath Colony", state_code: UK, district_code: "CHAMOLI", population: 642, vuln: 0.41, risk: 0.24, zone: "yellow", lon: 79.55, lat: 30.55, evidenceState: "available" },
  { habitation_id: 102, habitation_code: "UK-CHAM-02", name: "Gopeshwar Riverside", state_code: UK, district_code: "CHAMOLI", population: 215, vuln: 0.88, risk: 0.73, zone: "red", lon: 79.31, lat: 30.39, evidenceState: "low_confidence" },
  { habitation_id: 103, habitation_code: "UK-CHAM-03", name: "Nandprayag Upper", state_code: UK, district_code: "CHAMOLI", population: 388, vuln: 0.72, risk: 0.62, zone: "red", lon: 79.34, lat: 30.46, evidenceState: "available" },
  { habitation_id: 104, habitation_code: "UK-CHAM-04", name: "Goat Pass Terraces", state_code: UK, district_code: "CHAMOLI", population: 176, vuln: 0.6, risk: 0.15, zone: "green", lon: 79.62, lat: 30.63, evidenceState: "missing" },
  { habitation_id: 111, habitation_code: "UK-PITH-01", name: "Dharchula Edge", state_code: UK, district_code: "PITHORAGARH", population: 420, vuln: 0.66, risk: 0.6, zone: "red", lon: 80.12, lat: 29.85, evidenceState: "available" },
  { habitation_id: 121, habitation_code: "UK-RUD-01", name: "Rudraprayag Sripur", state_code: UK, district_code: "RUDRAPRAYAG", population: 510, vuln: 0.55, risk: 0.44, zone: "yellow", lon: 79.14, lat: 30.28, evidenceState: "available" },
  { habitation_id: 201, habitation_code: "AS-DHE-01", name: "Dhemaji Bargaon", state_code: AS, district_code: "DHEMAJI", population: 976, vuln: 0.62, risk: 0.55, zone: "yellow", lon: 94.55, lat: 27.47, evidenceState: "available" },
  { habitation_id: 202, habitation_code: "AS-DHE-02", name: "Dhemaji Lower Flats", state_code: AS, district_code: "DHEMAJI", population: 433, vuln: 0.93, risk: 0.82, zone: "red", lon: 94.56, lat: 27.45, evidenceState: "available" },
  { habitation_id: 203, habitation_code: "AS-DHE-03", name: "Bond Stretch", state_code: AS, district_code: "DHEMAJI", population: 322, vuln: 0.9, risk: 0.61, zone: "red", lon: 94.58, lat: 27.42, evidenceState: "low_confidence" },
  { habitation_id: 211, habitation_code: "AS-JOR-01", name: "Jorhat Riverine", state_code: AS, district_code: "JORHAT", population: 549, vuln: 0.58, risk: 0.31, zone: "yellow", lon: 94.21, lat: 26.75, evidenceState: "available" },
];

function centroid(district_code: string): [number, number] {
  const centroids: Record<string, [number, number]> = {
    CHAMOLI: [79.4, 30.4],
    PITHORAGARH: [80.2, 29.6],
    RUDRAPRAYAG: [79.1, 30.2],
    DHEMAJI: [94.6, 27.5],
    JORHAT: [94.2, 26.7],
    KAMRUP: [91.8, 26.1],
  };

  return centroids[district_code.toUpperCase()] ?? [79.4, 30.4];
}

export function demoMap(featureSource: "all-destinations" | "habitations" = "habitations"): FeatureCollection {
  const habitFeatures = HABITATIONS.filter((h) => h.evidenceState !== "missing").map((h) => ({
    type: "Feature" as const,
    geometry: { type: "Point" as const, coordinates: [h.lon, h.lat] },
    properties: {
      kind: "habitation",
      habitation_id: h.habitation_id,
      code: h.habitation_code,
      name: h.name,
      state_code: h.state_code,
      district_code: h.district_code,
      zone: h.zone,
      risk: Number(h.risk.toFixed(3)),
      population: h.population,
      victim_pop: Math.round(h.population * h.vuln),
      evidence: h.evidenceState,
    },
  }));

  const destinationFeatures = DEMO_DESTINATIONS.map((d) => ({
    type: "Feature" as const,
    geometry: { type: "Point" as const, coordinates: [d.lon, d.lat] },
    properties: { kind: "destination", name: d.name, destination_code: d.code, available_capacity: d.available, limiter: d.limiter, state_code: d.state_code, district_code: d.district_code, safety: d.safety },
  }));

  return {
    type: "FeatureCollection",
    features: (featureSource === "habitations" ? habitFeatures : destinationFeatures) as any,
    meta: { count: habitFeatures.length + destinationFeatures.length, srs: 4326 },
  };
}

// ---------------------------------------------------------------------------
// capacity / relocation fixtures
// ---------------------------------------------------------------------------
export interface DemoDestination {
  name: string;
  code: string;
  district_code: string;
  state_code: "UK" | "AS";
  housing: number;
  water: number;
  healthcare: number;
  safeLand: number;
  accessibility: number;
  current: number;
  available: number; // = max(0, min(caps) - current)
  limiter: string;
  safety: number;
  access: number;
  infra: number;
  distanceKm: number;
  lon: number;
  lat: number;
  mlcdScore: number;
  allowsSplit: boolean;
}

export const DEMO_DESTINATIONS: DemoDestination[] = [
  { name: "Chamoli High Ground West", code: "UK-GRN-CHAM-A1", district_code: "CHAMOLI", state_code: UK, housing: 900, water: 650, healthcare: 500, safeLand: 820, accessibility: 700, current: 210, available: 290, limiter: "Healthcare", safety: 0.86, access: 0.72, infra: 0.66, distanceKm: 12.4, lon: 79.5, lat: 30.6, mlcdScore: 0.81, allowsSplit: true },
  { name: "Pithoragarh Saddle", code: "UK-GRN-PITH-B2", district_code: "PITHORAGARH", state_code: UK, housing: 600, water: 400, healthcare: 380, safeLand: 1000, accessibility: 520, current: 95, available: 285, limiter: "Healthcare", safety: 0.9, access: 0.6, infra: 0.72, distanceKm: 18.2, lon: 80.2, lat: 29.5, mlcdScore: 0.84, allowsSplit: false },
  { name: "Rudraprayag Saddle North", code: "UK-GRN-RUD-C1", district_code: "RUDRAPRAYAG", state_code: UK, housing: 320, water: 260, healthcare: 140, safeLand: 300, accessibility: 240, current: 45, available: 95, limiter: "Healthcare", safety: 0.81, access: 0.67, infra: 0.7, distanceKm: 6.8, lon: 79.1, lat: 30.3, mlcdScore: 0.72, allowsSplit: true },
  { name: "Dhemaji Raised Bund North", code: "AS-GRN-DHE-C3", district_code: "DHEMAJI", state_code: AS, housing: 800, water: 720, healthcare: 300, safeLand: 420, accessibility: 600, current: 130, available: 170, limiter: "Safe Land", safety: 0.83, access: 0.81, infra: 0.74, distanceKm: 3.1, lon: 94.53, lat: 27.49, mlcdScore: 0.88, allowsSplit: true },
  { name: "Johrat Platform E", code: "AS-GRN-JOR-D4", district_code: "JORHAT", state_code: AS, housing: 500, water: 460, healthcare: 210, safeLand: 380, accessibility: 460, current: 80, available: 130, limiter: "Healthcare", safety: 0.8, access: 0.78, infra: 0.71, distanceKm: 4.4, lon: 94.2, lat: 26.7, mlcdScore: 0.79, allowsSplit: false },
];

function sum(caps: number[]) {
  return caps.reduce((a, b) => a + b, 0);
}

function availableFor(d: Omit<DemoDestination, "available" | "limiter"> & { limiter?: string }): number {
  return Math.max(0, Math.min(d.housing, d.water, d.healthcare, d.safeLand, d.accessibility) - d.current);
}

export function demoRelocationPlan(): RelocationPlan {
  const dem: DemoDestination[] = DEMO_DESTINATIONS.map((d) => ({ ...d, available: availableFor(d), limiter: d.limiter }));
  // match red habitations to local destinations within state
  const redHabit = HABITATIONS.filter((h) => h.zone === "red");
  let served = 0;
  const allocations = redHabit.flatMap((h) => {
    const matches = dem.filter((d) => d.state_code === h.state_code && d.available > 0).sort((a, b) => b.mlcdScore - a.mlcdScore);
    if (matches.length === 0) return [];
    const take = Math.min(Math.round(h.population), matches[0].available);
    served += take;
    return [
      {
        habitation_id: h.habitation_id,
        habitation_code: h.habitation_code,
        destination_id: matches[0].code.length,
        destination_code: matches[0].code,
        persons_allocated: take,
        score: matches[0].mlcdScore,
        destination_available_after: matches[0].available - take,
      },
    ];
  });
  return {
    plan_version: "demo-plan-v1",
    produced_at: new Date().toISOString(),
    allocations,
    unmet_demand: [],
    population_served: served,
    population_unserved: 0,
    split_demands: allocatedRowSplitCount(allocations),
    note: "Advisory allocation only - relocation needs human authorization.",
  };
}

function allocatedRowSplitCount(records: { habitation_id: number; destination_code: string }[]): number {
  const byHabit = new Map<number, Set<string>>();
  for (const r of records) {
    if (!byHabit.has(r.habitation_id)) byHabit.set(r.habitation_id, new Set());
    byHabit.get(r.habitation_id)!.add(r.destination_code);
  }
  let count = 0;
  byHabit.forEach((sites) => {
    if (sites.size > 1) count += 1;
  });
  return count;
}

// ---- settlement fixture (used at settle/[id]) -----------------------------
export function demoSettlement(id?: number | string): SettlementProfile | undefined {
  const h = HABITATIONS.find((x) => String(x.habitation_id) === String(id)) ?? HABITATIONS[0];
  if (!h) return undefined;
  // plausible SHAP drivers calibrated from risk
  const red_hazard = h.risk > 0.6;
  const shap: SettlementProfile["shap_drivers"] = red_hazard
    ? [
        { feature: "Slope", direction: "+", contribution: 0.18, label: "Slope +0.35" },
        { feature: "Rainfall", direction: "+", contribution: 0.14, label: "Rainfall +0.28" },
        { feature: "Dist river", direction: "-", contribution: 0.06, label: "Dist river -0.12" },
        { feature: "Geology", direction: "+", contribution: 0.11, label: "Geology +0.21" },
        { feature: "Hg homes", direction: "+", contribution: 0.05, label: "Hg homes +0.09" },
      ]
    : [
        { feature: "Slope", direction: "-", contribution: 0.05, label: "Slope -0.08" },
        { feature: "Rainfall", direction: "-", contribution: 0.04, label: "Rainfall -0.06" },
        { feature: "Geology", direction: "+", contribution: 0.03, label: "Geology +0.04" },
      ];

  const hazardEvidence = [
    { hazard_type: "flood", score: h.zone === "red" ? 0.12 : 0.04, missing: false, low_confidence: false },
    { hazard_type: "landslide", score: red_hazard ? 0.78 : 0.2, missing: false, low_confidence: h.evidenceState === "low_confidence" },
    { hazard_type: "coastal_erosion", score: null, missing: true, low_confidence: false },
    { hazard_type: "cloudburst", score: red_hazard ? 0.62 : 0.16, missing: h.evidenceState === "missing", low_confidence: false },
  ];

  return {
    habitation_id: h.habitation_id,
    habitation_code: h.habitation_code,
    state_code: h.state_code,
    district_code: h.district_code,
    total_population: h.population,
    zone: h.zone,
    risk: h.risk,
    vulnerability_score: h.vuln,
    priority: h.zone === "red" ? "immediate" : h.zone === "yellow" ? "priority" : "monitor",
    hazard_evidence: hazardEvidence,
    shap_drivers: shap,
    shap_state: "available",
    data_quality_flags: {
      hazard_provided: true,
      vulnerability_provided: true,
      evidence_sufficient: h.evidenceState !== "missing",
      warnings: h.evidenceState === "missing" ? ["Landslide reading missing. Treated as unknown, never as zero."] : [],
    },
  };
}

export function demoScenarioDemo(): { red: number; yellow: number; green: number } {
  return { red: 0, yellow: 0, green: 0 };
}

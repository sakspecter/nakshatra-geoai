/**
 * Domain constants & the immutable disaster-command "visual language".
 *
 * Zones are intentionally high contrast.
 * Evidence `missing`/`low_confidence` always render as grey/dashed states and are
 * NEVER collapsed into a bright zone or dropped.
 */

// ---------------------------------------------------------------------------
// Zone visual language (must stay source-of-truth for map + legends + charts)
// ---------------------------------------------------------------------------
export type ZoneKey = "red" | "yellow" | "green";

export const ZONE_META: Record<
  ZoneKey | "missing" | "low_confidence",
  { label: string; fill: string; stroke: string; badge: string }
> = {
  red: {
    label: "High risk",
    fill: "hsl(var(--zone-red))",
    stroke: "hsl(var(--zone-red))",
    badge: "bg-zone-red text-white",
  },
  yellow: {
    label: "Medium risk",
    fill: "hsl(var(--zone-yellow))",
    stroke: "hsl(var(--zone-yellow))",
    badge: "bg-zone-yellow text-black",
  },
  green: {
    label: "Low risk / safe",
    fill: "hsl(var(--zone-green))",
    stroke: "hsl(var(--zone-green))",
    badge: "bg-zone-green text-white",
  },
  missing: {
    label: "No evidence",
    fill: "transparent",
    stroke: "hsl(var(--zone-missing))",
    badge: "border border-dashed border-zinc-500 text-zinc-400",
  },
  low_confidence: {
    label: "Low confidence",
    fill: "hsl(var(--zone-low) / 0.18)",
    stroke: "hsl(var(--zone-low))",
    badge: "border border-dashed text-zinc-300",
  },
};

export type HazardKey = "flood" | "landslide" | "coastal_erosion" | "cloudburst";

export const HAZARD_META: Record<HazardKey, { label: string; color: string }> = {
  flood: { label: "Flood", color: "#38bdf8" },
  landslide: { label: "Landslide", color: "#fb923c" },
  coastal_erosion: { label: "Coastal erosion", color: "#2dd4bf" },
  cloudburst: { label: "Cloudburst", color: "#a78bfa" },
};

export interface DistrictDescriptor {
  code: string;
  label: string;
  state: StateCode;
  boundaryColor: string;
}

/**
 * State codes are no longer a closed union: the nationwide catalog is driven by
 * the backend (`/spatial/states`). UK/AS remain the typed pilot convenience
 * members; `string` allows any newly ingested state (e.g. SK - Sikkim).
 */
export type StateCode = "UK" | "AS" | "SK" | (string & {});

export const STATES: Array<{
  code: StateCode;
  label: string;
}> = [
  { code: "UK", label: "Uttarakhand" },
  { code: "AS", label: "Assam" },
  { code: "SK", label: "Sikkim" },
];

// the six "district comparison" cards across the two pilot geographies
export const DISTRICT_DESCRIPTORS: DistrictDescriptor[] = [
  { code: "CHAMOLI", label: "Chamoli", state: "UK", boundaryColor: "#22d3ee" },
  { code: "PITHORAGARH", label: "Pithoragarh", state: "UK", boundaryColor: "#38bdf8" },
  { code: "RUDRAPRAYAG", label: "Rudraprayag", state: "UK", boundaryColor: "#818cf8" },
  { code: "DHEMAJI", label: "Dhemaji", state: "AS", boundaryColor: "#fb923c" },
  { code: "JORHAT", label: "Jorhat", state: "AS", boundaryColor: "#fb7185" },
  { code: "KAMRUP", label: "Kamrup Metro", state: "AS", boundaryColor: "#a3e635" },
];

export const PRIORITY_LABEL: Record<string, string> = {
  immediate: "Immediate",
  priority: "Priority",
  monitor: "Monitor",
};

export function toPct(value: number, digits = 1): string {
  return `${(value * 100).toFixed(digits)}%`;
}

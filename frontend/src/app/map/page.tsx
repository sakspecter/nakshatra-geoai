"use client";

import * as React from "react";
import dynamic from "next/dynamic";
import Link from "next/link";
import { Layers, MapPin } from "lucide-react";
import CommandShell from "@/components/layout/command-shell";
import type { LayerVis } from "@/components/map/risk-map";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Switch } from "@/components/ui/switch";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogHeader,
  DialogTitle,
} from "@/components/ui/dialog";
import { getHabitations, getDistricts, getStates, getMapLayers } from "@/lib/api";
import type {
  DistrictMeta,
  FeatureCollection,
  StateMeta,
} from "@/lib/types";
import { cn } from "@/lib/utils";

// Maplibre must never touch the server during SSR — load inside the browser.
const RiskMap = dynamic(
  () => import("@/components/map/risk-map").then((m) => m.RiskMap),
  { ssr: false, loading: () => <div className="grid h-full place-items-center text-sm text-muted-foreground">Loading map canvas…</div> }
);

const HAZARD_TOGGLES: Array<{ key: keyof LayerVis; label: string; note: string }> = [
  { key: "flood", label: "Flood", note: "Riverine extent" },
  { key: "landslide", label: "Landslide", note: "Slope instability" },
  { key: "coastal", label: "Coastal", note: "Coastal erosion" },
  { key: "cloudburst", label: "Cloudburst", note: "Flash rainfall" },
];

const ZONE_TOGGLES: Array<{ key: keyof LayerVis; label: string; color: string }> = [
  { key: "red", label: "Red (High risk)", color: "#ef4444" },
  { key: "yellow", label: "Yellow (Medium)", color: "#facc15" },
  { key: "green", label: "Green (Low/safe)", color: "#22c55e" },
];

export default function MapPage() {
  const [hab, setHab] = React.useState<FeatureCollection | null>(null);
  const [infra, setInfra] = React.useState<FeatureCollection | null>(null);
  const [vis, setVis] = React.useState<LayerVis>({
    flood: true,
    landslide: false,
    coastal: false,
    cloudburst: true,
    red: true,
    yellow: true,
    green: true,
    infra: true,
  });
  const [summary, setSummary] = React.useState<Record<string, unknown> | null>(null);

  // cascading district focus (nationwide)
  const [states, setStates] = React.useState<StateMeta[]>([]);
  const [districts, setDistricts] = React.useState<DistrictMeta[]>([]);
  const [focusState, setFocusState] = React.useState<string>("UK");
  const [focusDistrict, setFocusDistrict] = React.useState<string>("CHAMOLI");
  const [bounds, setBounds] = React.useState<[[number, number], [number, number]] | null>(null);

  React.useEffect(() => {
    getMapLayers("habitations").then((d) => setHab(d.payload));
    getMapLayers("infra").then((d) => setInfra(d.payload));
    getStates().then((d) => setStates(d.payload));
  }, []);

  // load districts whenever the focused state changes
  React.useEffect(() => {
    if (focusState === "ALL") return;
    getDistricts(focusState).then((d) => {
      setDistricts(d.payload);
      if (!d.payload.some((x) => x.district_code === focusDistrict)) {
        const first = d.payload[0]?.district_code ?? "";
        setFocusDistrict(first);
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [focusState]);

  // selecting a district (incl. freshly ingested ones) re-renders its zones
  // and flies the camera to the district bounding box
  React.useEffect(() => {
    if (!focusDistrict || focusState === "ALL") return;
    let alive = true;
    getHabitations(focusDistrict).then((d) => {
      if (!alive) return;
      setHab(d.payload);
      const bbox = d.payload.meta?.bbox;
      if (bbox && bbox.length === 4 && bbox[0] !== bbox[2]) {
        setBounds([
          [bbox[0], bbox[1]],
          [bbox[2], bbox[3]],
        ]);
      }
    });
    return () => {
      alive = false;
    };
  }, [focusDistrict, focusState]);

  const toggle = (key: keyof LayerVis) => setVis((v) => ({ ...v, [key]: !v[key] }));

  const selected = summary?.properties
    ? (summary.properties as Record<string, unknown>)
    : null;

  return (
    <CommandShell active="map">
      <div className="grid h-full grid-cols-1 gap-4 lg:grid-cols-[300px_1fr]">
        {/* layer panel */}
        <div className="space-y-4">
          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <MapPin className="h-4 w-4" /> District focus
              </CardTitle>
              <CardDescription>
                Nationwide catalog — freshly ingested districts appear here instantly
              </CardDescription>
            </CardHeader>
            <CardContent className="space-y-2">
              <Select value={focusState} onValueChange={(v) => { setFocusState(v); setBounds(null); }}>
                <SelectTrigger>
                  <SelectValue placeholder="State" />
                </SelectTrigger>
                <SelectContent>
                  {states.map((s) => (
                    <SelectItem key={s.state_code} value={s.state_code}>
                      {s.state_name}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <Select
                value={focusDistrict}
                onValueChange={setFocusDistrict}
                disabled={districts.length === 0}
              >
                <SelectTrigger>
                  <SelectValue placeholder="District" />
                </SelectTrigger>
                <SelectContent>
                  {districts.map((d) => (
                    <SelectItem key={d.district_code} value={d.district_code}>
                      {d.district_name} · {d.habitation_count}
                    </SelectItem>
                  ))}
                </SelectContent>
              </Select>
              <p className="text-xs text-muted-foreground">
                Selecting a district loads its Red/Yellow/Green zones and flies the
                camera to its bounding box.
              </p>
            </CardContent>
          </Card>

          <Card>
            <CardHeader className="pb-3">
              <CardTitle className="flex items-center gap-2 text-sm">
                <Layers className="h-4 w-4" /> Layer controls
              </CardTitle>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <p className="text-xs font-medium uppercase text-muted-foreground">
                  Hazard overlays
                </p>
                {HAZARD_TOGGLES.map((h) => (
                  <div
                    key={h.key}
                    className="flex items-center justify-between rounded-md border border-border px-3 py-2"
                  >
                    <div>
                      <p className="text-sm">{h.label}</p>
                      <p className="text-xs text-muted-foreground">{h.note}</p>
                    </div>
                    <Switch checked={vis[h.key]} onCheckedChange={() => toggle(h.key)} />
                  </div>
                ))}
              </div>

              <div className="space-y-2">
                <p className="text-xs font-medium uppercase text-muted-foreground">
                  Habitation zones
                </p>
                {ZONE_TOGGLES.map((z) => (
                  <div
                    key={z.key}
                    className="flex items-center justify-between gap-2 rounded-md border border-border px-3 py-2"
                  >
                    <span
                      className="inline-flex items-center gap-2 text-sm"
                    >
                      <span
                        className="inline-block h-3 w-3 rounded-full"
                        style={{ background: z.color }}
                      />
                      {z.label}
                    </span>
                    <Switch checked={vis[z.key]} onCheckedChange={() => toggle(z.key)} />
                  </div>
                ))}
              </div>

              <div className="flex items-center justify-between rounded-md border border-border px-3 py-2">
                <span className="text-sm">Expedition / safe sites</span>
                <Switch
                  checked={vis.infra}
                  onCheckedChange={() => toggle("infra")}
                />
              </div>
            </CardContent>
          </Card>

          {/* Visual language legend */}
          <Card>
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Zone legend</CardTitle>
            </CardHeader>
            <CardContent className="space-y-1 text-sm">
              <LegendDot color="#ef4444" label="Red - immediate/high" />
              <LegendDot color="#facc15" label="Yellow - moderate" />
              <LegendDot color="#22c55e" label="Green - low/safe" />
              <LegendDot color="grey" label="Missing/low-confindence (grey/dashed)" dashed />
            </CardContent>
          </Card>
        </div>

        {/* map column */}
        <div className="relative h-[65vh] lg:h-auto">
          {hab ? (
            <RiskMap
              habitations={hab}
              destinations={infra}
              layerVis={vis}
              fitBounds={bounds}
              onSelectFeatures={(p) => setSummary(p ? { properties: p } : null)}
            />
          ) : (
            <div className="grid h-full place-items-center rounded-lg bg-muted text-sm text-muted-foreground">
              Loading map layers…
            </div>
          )}

          <div className="absolute left-3 top-3 z-20 flex items-center gap-2">
            <Badge>Interactive risk map</Badge>
            <Badge variant="outline">WGS84 / EPSG:4326</Badge>
          </div>
        </div>
      </div>

      {/* quick-drawer summary with link into settlement analysis */}
      <Dialog open={!!selected} onOpenChange={(o) => !o && setSummary(null)}>
        <DialogContent className="sm:max-w-md">
          <DialogHeader>
            <DialogTitle>
              {String(selected?.name ?? selected?.code ?? "Habitation")}
            </DialogTitle>
            <DialogDescription>
              Click a habitation marker to inspect its profile…
            </DialogDescription>
          </DialogHeader>
          {selected && (
            <div className="space-y-3 text-sm">
              <dl className="grid grid-cols-2 gap-2">
                <Meta k="Habitation" v={selected.habitation_id?.toString() ?? "-"} />
                <Meta k="District" v={String(selected.district_code ?? "-")} />
                <Meta k="Risk" v={selected.risk !== null ? String(Number(selected.risk).toFixed(2)) : "-"} />
                <Meta k="Pop" v={selected.population?.toString() ?? "-"} />
              </dl>
              <p
                className={cn(
                  "text-xs",
                  (selected?.zone ?? "") === "red"
                    ? "text-red-300"
                    : (selected?.zone ?? "") === "yellow"
                      ? "text-yellow-300"
                      : "text-emerald-300"
                )}
              >
                Zone: {String(selected.zone ?? "unknown")}
              </p>
              <div className="flex flex-wrap gap-2">
                <Button asChild>
                  <Link href={`/settlement/${selected.habitation_id}`}>
                    Open settlement analysis →
                  </Link>
                </Button>
              </div>
            </div>
          )}
        </DialogContent>
      </Dialog>
    </CommandShell>
  );
}

function LegendDot({
  color,
  label,
  dashed,
}: {
  color: string;
  label: string;
  dashed?: boolean;
}) {
  return (
    <div className="flex items-center gap-2">
      <span
        className="inline-block h-3 w-3 rounded-full"
        style={{ background: color === "grey" ? (dashed ? "transparent" : "#71717a") : color, ...(dashed ? { border: "1.5px dashed #52525b" } : {}) }}
      />
      <span className="text-muted-foreground">{label}</span>
    </div>
  );
}

function Meta({ k, v }: { k: string; v: string }) {
  return (
    <div>
      <dt className="text-xs text-muted-foreground">{k}</dt>
      <dd className="font-medium">{v}</dd>
    </div>
  );
}

"use client";

import * as React from "react";
import Link from "next/link";
import { notFound, useParams } from "next/navigation";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
  LabelList,
} from "recharts";
import { ArrowUpRight, HardHat, ShieldCheck } from "lucide-react";
import CommandShell from "@/components/layout/command-shell";
import { ZoneBadge } from "@/components/shared/zone-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { getSettlement } from "@/lib/api";
import { DEMO_DESTINATIONS, demoSettlement } from "@/lib/demo";
import { formatNumber, cn } from "@/lib/utils";
import { HAZARD_META } from "@/lib/constants";
import type { HazardType } from "@/lib/types";

export default function ProfileView() {
  const params = useParams<{ id: string }>();
  const id = Number(params.id);
  const [state, setState] = React.useState<{ data: ReturnType<typeof demoSettlement>; source: string } | null>(null);

  React.useEffect(() => {
    getSettlement(id).then((d) => {
      setState({ data: demoSettlement(id) ?? undefined, source: d.source });
    });
  }, [id]);

  if (!state) return <CommandShell active="settlement"><p className="p-10 text-muted-foreground">Loading settlement…</p></CommandShell>;
  const s = state.data;
  if (!s) return notFound();

  const colorFor = s.zone === "red" ? "#ef4444" : s.zone === "yellow" ? "#facc15" : "#22c55e";

  return (
    <CommandShell active="settlement">
      <div className="mb-5 flex items-center justify-between">
        <div>
          <p className="text-xs text-muted-foreground">Settlement Analysis</p>
          <h1 className="text-2xl font-semibold tracking-tight">
            {s.habitation_code}{" "}
            <span className="ml-1 text-base text-muted-foreground">
              #{s.habitation_id}
            </span>
          </h1>
          <p className="text-sm text-muted-foreground">
            {s.district_code} · {s.state_code}
          </p>
        </div>
        <div className="flex flex-wrap items-center gap-2">
          <ZoneBadge zone={s.zone} label={`Band: ${s.zone.toUpperCase()}`} />
          <Badge variant="outline">confidence {evidenceLabel(s)}</Badge>
          <MapLink id={s.habitation_id} district_code={s.district_code} zone={s.zone} />
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="space-y-6 lg:col-span-1">
          {/* headline */}
          <Card>
            <CardHeader>
              <CardTitle>Risk profile</CardTitle>
            </CardHeader>
            <CardContent className="space-y-4">
              <div>
                <p className="text-xs text-muted-foreground">Quantitative Risk</p>
                <div className="mt-1 flex items-end gap-2">
                  <span className="text-4xl font-bold" style={{ color: colorFor }}>
                    {s.risk.toFixed(2)}
                  </span>
                  <span className="mb-1 text-sm text-muted-foreground">/ 1.0</span>
                </div>
              </div>
              <div className="grid grid-cols-2 gap-3">
                <Stat label="Total population" value={formatNumber(s.total_population)} />
                <Stat label="Vulnerability idx" value={(s.vulnerability_score ?? 0).toFixed(2)} />
                <Stat label="Priority" value={s.priority} />
              </div>
              <div className="rounded-md border border-border bg-muted/20 p-3 text-xs">
                <p className="mb-1 flex items-center gap-1.5 font-medium text-muted-foreground">
                  <HardHat className="h-3.5 w-3.5" /> Capacity &amp; evidence
                </p>
                <EvidenceList evidence={s.hazard_evidence} />
              </div>
            </CardContent>
          </Card>
        </div>

        <div className="space-y-6 lg:col-span-2">
          <Card>
            <CardHeader>
              <CardTitle>SHAP driver decomposition</CardTitle>
              <CardDescription>
                Local feature contributions to {s.habitation_code} risk
              </CardDescription>
            </CardHeader>
            <CardContent>
              <ShapChart drivers={s.shap_drivers} />
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <ShieldCheck className="h-4 w-4 text-emerald-400" /> Safe relocation
                evidence
              </CardTitle>
              <CardDescription>
                Governing bottleneck = min(housing·water·healthcare·land·access)
              </CardDescription>
            </CardHeader>
            <CardContent className="grid gap-3 sm:grid-cols-2">
              {safeEvidence(s.district_code, s.state_code).map((dest) => {
                const minCap = Math.min(dest.housing, dest.water, dest.healthcare, dest.safeLand, dest.accessibility);
                const bottleneck = minCap === dest.healthcare ? "Healthcare" : minCap === dest.safeLand ? "Safe Land" : minCap === dest.accessibility ? "Accessibility" : minCap === dest.water ? "Water" : "Housing";
                return (
                  <div key={dest.code} className="rounded-lg border border-border p-4 text-sm">
                    <div className="flex items-start justify-between">
                      <div>
                        <p className="font-medium">{dest.name}</p>
                        <p className="text-xs text-muted-foreground">{dest.code}</p>
                      </div>
                      <span className="text-xs uppercase text-emerald-300">
                        avail {Math.max(0, minCap - dest.current)}
                      </span>
                    </div>
                    <div className="mt-3 grid grid-cols-5 gap-1 text-center text-[10px]">
                      <Mini name="Housing" v={dest.housing} />
                      <Mini name="Water" v={dest.water} />
                      <Mini name="Health" v={dest.healthcare} />
                      <Mini name="Land" v={dest.safeLand} />
                      <Mini name="Access" v={dest.accessibility} />
                      <p className="col-span-5 mt-1 text-left text-muted-foreground">
                        bottleneck: <span className="text-amber-300">{bottleneck}</span>{" "}
                        (overall {Math.max(0, minCap - dest.current)} headroom)
                      </p>
                      <p className="col-span-5 text-left text-[10px] text-muted-foreground">
                        last updated {fresh(dest.code)}
                      </p>
                    </div>
                  </div>
                );
              })}
            </CardContent>
          </Card>
        </div>
      </div>
    </CommandShell>
  );
}

function evidenceLabel(s: { hazard_evidence: { low_confidence: boolean; missing: boolean }[] }): string {
  return s.hazard_evidence?.some((h) => h.low_confidence || h.missing) ? "partial" : "confirmed";
}

function MapLink({
  id,
  district_code,
  zone,
}: {
  id: number;
  district_code: string;
  zone: string;
}) {
  return (
    <Button variant="outline" size="sm" asChild>
      <Link
        href={`/map?focus=${id}`}
        className="inline-flex items-center gap-1.5"
      >
        Locate on map <ArrowUpRight className="h-3.5 w-3.5" />
      </Link>
    </Button>
  );
}

function ShapChart({ drivers }: { drivers: NonNullable<ReturnType<typeof demoSettlement>>["shap_drivers"] }) {
  const data = drivers.map((d) => ({
    name: d.feature,
    ...d,
  }));
  return (
    <div className="h-64">
      <ResponsiveContainer width="100%" height="100%">
        <BarChart data={data as Array<Record<string, unknown>>} layout="vertical" margin={{ left: 40 }}>
          <CartesianGrid strokeDasharray="3 3" horizontal={false} opacity={0.2} />
          <XAxis type="number" hide allowDecimals={false} />
          <YAxis type="category" dataKey="name" width={110} tick={{ fill: "#a1a1aa", fontSize: 11 }} />
          <Tooltip />
          <Bar dataKey="contribution" radius={[0, 4, 4, 0]} barSize={18}>
            {(data as unknown as Array<{ contribution: number; direction: string }>).map((d, idx) => (
              <Cell key={idx} fill={d.direction === "+" ? "#f87171" : "#34d399"} />
            ))}
          </Bar>
        </BarChart>
      </ResponsiveContainer>
    </div>
  );
}

function EvidenceList({ evidence }: { evidence: NonNullable<ReturnType<typeof demoSettlement>>["hazard_evidence"] }) {
  return (
    <ul className="space-y-1">
      {evidence.map((h) => {
        const meta = HAZARD_META[h.hazard_type as keyof typeof HAZARD_META] ?? { label: h.hazard_type };
        const stateClass = h.missing
          ? "border-dashed border-zinc-500 text-zinc-400"
          : h.low_confidence
            ? "border-dashed text-zinc-300"
            : "";
        return (
          <li key={h.hazard_type} className={cn("rounded border px-2 py-1", stateClass, !h.missing && !h.low_confidence && "border-border")}>
            <span className="flex items-center justify-between">
              <span>{meta.label}</span>
              <span>{h.score?.toFixed(2) ?? "—"} {h.missing && "missing"}</span>
            </span>
          </li>
        );
      })}
    </ul>
  );
}

function Stat({ label, value }: { label: string; value: string }) {
  return (
    <div>
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className="text-lg font-semibold">{value}</p>
    </div>
  );
}

function Mini({ name, v }: { name: string; v: number }) {
  return (
    <span>
      <span className="block text-[10px] uppercase text-muted-foreground">{name}</span>
      <span className="block">{v}</span>
    </span>
  );
}

function safeEvidence(district: string, state: string) {
  const out = DEMO_DESTINATIONS.filter((d) => d.district_code === district && d.state_code === state);
  return out.length ? out.slice(0, 2) : DEMO_DESTINATIONS.slice(0, 2);
}

function fresh(code: string): string {
  return `${new Date(Date.now() - code.length * 3600_000).toISOString().slice(0, 16)} UTC`;
}

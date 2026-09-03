"use client";

import { useEffect, useState } from "react";
import {
  Bar,
  BarChart,
  CartesianGrid,
  Cell,
  Legend,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from "recharts";
import {
  ShieldAlert,
  ShieldCheck,
  Gauge,
  AlertTriangle,
} from "lucide-react";
import CommandShell from "@/components/layout/command-shell";
import { Badge } from "@/components/ui/badge";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import {
  DISTRICT_DESCRIPTORS,
  HAZARD_META,
  STATES,
} from "@/lib/constants";
import { formatNumber } from "@/lib/utils";
import type { OverviewResponse, DistrictKpi } from "@/lib/types";
import { getOverview } from "@/lib/api";

export default function OverviewPage() {
  const [data, setData] = useState<OverviewResponse | null>(null);
  const [source, setSource] = useState("demo");

  useEffect(() => {
    getOverview().then((d) => {
      setData(d.payload);
      setSource(d.source);
    });
  }, []);

  if (!data) {
    return (
      <CommandShell active="overview">
        <OverviewSkeleton />
      </CommandShell>
    );
  }

  const t = data.totals;
  const immediate = data.by_district.reduce((a, d) => a + d.red_zone_count * 92, 0);
  const priority = data.by_district.reduce((a, d) => a + d.yellow_zone_count * 48, 0);

  const uk = data.by_district
    .filter((d) => d.state_code === "UK")
    .map((d) => ({ ...d, label: districtLabel(d.district_code) }));
  const as = data.by_district
    .filter((d) => d.state_code === "AS")
    .map((d) => ({ ...d, label: districtLabel(d.district_code) }));

  const prize = [
    { name: "Immediate", value: immediate, fill: "#ef4444" },
    { name: "Priority", value: priority, fill: "#facc15" },
  ];

  return (
    <CommandShell active="overview">
      <div className="space-y-6">
        <div className="flex flex-wrap items-center justify-between gap-2">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">
              Overview Dashboard
            </h1>
            <p className="text-sm text-muted-foreground">
              Regional exposure and relocation demand across Uttarakhand &amp;
              Assam pilots
            </p>
          </div>
          <Badge variant="outline">
            {source === "api" ? "Live API" : "Demo dataset"}
          </Badge>
        </div>

        {/* KPI cards */}
        <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
          <Kpi
            icon={<ShieldAlert className="h-5 w-5" />}
            label="Total Exposed Population"
            value={formatNumber(t.vulnerable_population_total)}
            delta={`N/A (${data.by_state.length} states)`}
            tone="amber"
          />
          <Kpi
            icon={<AlertTriangle className="h-5 w-5" />}
            label="Red Zone Habitations"
            value={`${t.red_zone_count} / ${t.habitation_count}`}
            delta="Highest risk priority"
            tone="red"
          />
          <Kpi
            icon={<Gauge className="h-5 w-5" />}
            label="Relocation Demand"
            value={`${formatNumber(immediate)}`}
            delta={`Immediate ${formatNumber(immediate)} · Priority ${formatNumber(priority)}`}
            tone="yellow"
          />
          <Kpi
            icon={<ShieldCheck className="h-5 w-5" />}
            label="Available Safe Capacity"
            value={formatNumber(t.safe_available_capacity)}
            delta="persons (all safe sites)"
            tone="green"
          />
        </div>

        {/* District comparison (two geographies) */}
        <div className="grid grid-cols-1 gap-6 xl:grid-cols-2">
          <DistrictGroup title="Uttarakhand" rows={uk} accent="#22d3ee" />
          <DistrictGroup title="Assam" rows={as} accent="#fb923c" />
        </div>

        {/* charts */}
        <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
          <Card className="lg:col-span-2">
            <CardHeader>
              <CardTitle>Hazard exposure by district</CardTitle>
              <CardDescription>
                Stacked relative hazard contribution per district
              </CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-72">
                <ResponsiveContainer width="100%" height="100%">
                  <BarChart data={hazardData()} layout="vertical" margin={{ left: 8 }}>
                    <CartesianGrid strokeDasharray="3 3" opacity={0.2} />
                    <XAxis type="number" hide allowDecimals={false} />
                    <YAxis
                      type="category"
                      dataKey="name"
                      width={130}
                      tick={{ fill: "#a1a1aa", fontSize: 12 }}
                    />
                    <Tooltip />
                    <Legend />
                    {Object.values(HAZARD_META).map((h) => (
                      <Bar
                        key={h.label}
                        dataKey={h.label}
                        stackId="haz"
                        fill={h.color}
                      />
                    ))}
                  </BarChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle>Relocation priority</CardTitle>
              <CardDescription>Demand split by priority class</CardDescription>
            </CardHeader>
            <CardContent>
              <div className="h-64">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={prize}
                      dataKey="value"
                      nameKey="name"
                      innerRadius={48}
                      outerRadius={80}
                      paddingAngle={3}
                    >
                      {prize.map((e) => (
                        <Cell key={e.name} fill={e.fill} />
                      ))}
                    </Pie>
                    <Tooltip />
                  </PieChart>
                </ResponsiveContainer>
              </div>
            </CardContent>
          </Card>
        </div>
      </div>
    </CommandShell>
  );
}

function districtLabel(code: string): string {
  const found = DISTRICT_DESCRIPTORS.find((x) => x.code === code);
  return found?.label ?? code;
}

function hazardData() {
  return DISTRICT_DESCRIPTORS.map((d) => {
    const base = { name: d.label };
    const seed =
      d.code === "CHAMOLI"
        ? { "Landslide": 0.55, "Cloudburst": 0.35, "Flood": 0.05, "Coastal erosion": 0.05 }
        : d.code === "DHEMAJI" || d.code === "JORHAT"
          ? { "Flood": 0.62, "Cloudburst": 0.18, "Landslide": 0.1, "Coastal erosion": 0.1 }
          : d.code === "RUDRAPRAYAG"
            ? { "Cloudburst": 0.4, "Flood": 0.22, "Landslide": 0.3, "Coastal erosion": 0.08 }
            : { "Flood": 0.2, "Landslide": 0.4, "Cloudburst": 0.25, "Coastal erosion": 0.15 };
    return { ...base, ...seed };
  });
}

function DistrictGroup({
  title,
  rows,
  accent,
}: {
  title: string;
  rows: (DistrictKpi & { label: string })[];
  accent: string;
}) {
  return (
    <Card>
      <CardHeader>
        <CardTitle className="flex items-center gap-2 text-base">
          <span className="h-2.5 w-2.5 rounded-full" style={{ background: accent }} />
          {title}
        </CardTitle>
        <CardDescription>Vulnerable exposure vs available safe capacity</CardDescription>
      </CardHeader>
      <CardContent className="grid grid-cols-1 gap-3 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.district_code} className="rounded-lg border border-border bg-muted/30 p-4">
            <p className="text-sm font-medium">{row.label}</p>
            <dl className="mt-2 space-y-1 text-sm">
              <RowPair k="Red zones" v={String(row.red_zone_count)} accent="text-red-300" />
              <RowPair k="Vulnerable pop" v={formatNumber(row.vulnerable_population_total)} accent="text-amber-200" />
              <RowPair k="Safe capacity" v={formatNumber(row.safe_available_capacity)} accent="text-emerald-300" />
              <RowPair k="Habs monitored" v={`${row.habitation_count}`} />
            </dl>
          </div>
        ))}
      </CardContent>
    </Card>
  );
}

function RowPair({
  k,
  v,
  accent,
}: {
  k: string;
  v: string;
  accent?: string;
}) {
  return (
    <div className="flex items-center justify-between gap-2">
      <dt className="text-muted-foreground">{k}</dt>
      <dd className={accent ?? "text-foreground"}>{v}</dd>
    </div>
  );
}

function Kpi({
  icon,
  label,
  value,
  delta,
  tone,
}: {
  icon: React.ReactNode;
  label: string;
  value: string;
  delta: string;
  tone: "red" | "green" | "amber" | "yellow";
}) {
  return (
    <Card>
      <CardHeader className="flex flex-row items-center gap-3 space-y-0 pb-2">
        <div
          className={`grid h-10 w-10 place-items-center rounded-lg ${
            tone === "red"
              ? "bg-red-500/10 text-red-400"
              : tone === "green"
                ? "bg-emerald-500/10 text-emerald-400"
                : "bg-amber-500/10 text-amber-400"
          }`}
        >
          {icon}
        </div>
        <CardTitle className="text-sm font-medium text-muted-foreground">
          {label}
        </CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-3xl font-semibold tracking-tight">{value}</p>
        <p className="mt-1 text-xs text-muted-foreground">{delta}</p>
      </CardContent>
    </Card>
  );
}

function OverviewSkeleton() {
  return (
    <div className="space-y-6">
      <div className="h-8 w-64 animate-pulse rounded bg-muted" />
      <div className="grid grid-cols-1 gap-4 sm:grid-cols-2 xl:grid-cols-4">
        {Array.from({ length: 4 }).map((_, i) => (
          <div key={i} className="h-32 animate-pulse rounded-lg bg-muted" />
        ))}
      </div>
    </div>
  );
}

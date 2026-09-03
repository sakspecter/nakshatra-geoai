"use client";


import * as React from "react";
import { ArrowRight, AlertTriangle } from "lucide-react";
import CommandShell from "@/components/layout/command-shell";
import { ZoneBadge } from "@/components/shared/zone-badge";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { DEMO_DESTINATIONS, DEMO_DISTRICTS, demoRelocationPlan } from "@/lib/demo";
import { formatNumber } from "@/lib/utils";
import type { RelocationPlan } from "@/lib/types";

export default function RelocationPage() {
  const [plan, setPlan] = React.useState<RelocationPlan | null>(null);
  React.useEffect(() => {
    setPlan(demoRelocationPlan());
  }, []);
  const p = plan ?? demoRelocationPlan();

  // ranked destinations by availability * mcd distance
  const dests = [...DEMO_DESTINATIONS].sort((a, b) => b.mlcdScore - a.mlcdScore);

  const totalDemandAsterisk = DEMO_DISTRICTS.reduce((a, d) => a + d.redZones, 0);

  return (
    <CommandShell active="relocation">
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="text-2xl font-semibold tracking-tight">Relocation Planner</h1>
            <p className="text-sm text-muted-foreground">
              Advisory allocation of at-risk habitations to safe carrying-capacity sites.
            </p>
          </div>
          <Alert variant="info" className="my-0 max-w-sm">
            <AlertTitle>Advisory only</AlertTitle>
            <AlertDescription>
              Relocation needs human authorization — numbers below never auto-act.
            </AlertDescription>
          </Alert>
        </div>

        <div className="grid grid-cols-2 gap-4 lg:grid-cols-4">
          <LeadStat label="Red zones" value={String(totalDemandAsterisk)} hint="demand sources" />
          <LeadStat label="People served" value={formatNumber(p.population_served)} hint={`plan ${p.plan_version}`} />
          <LeadStat label="Splits required" value={String(p.split_demands)} hint="population across &gt;1 site" warn={p.split_demands > 0} />
          <LeadStat label="Unmet" value={formatNumber(p.population_unserved)} hint="would remain in place" />
        </div>

        {/* demand x destination matrix */}
        <Card>
          <CardHeader>
            <CardTitle>Allocation demand matrix</CardTitle>
            <CardDescription>
              Red zone habitations → safe carrying capacity sites (min-governed)
            </CardDescription>
          </CardHeader>
          <CardContent>
            {p.allocations.length === 0 ? (
              <p className="py-6 text-center text-sm text-muted-foreground">
                No allocation matched the current demand set.
              </p>
            ) : (
              <div className="overflow-x-auto rounded-md border">
                <table className="w-full text-left text-sm">
                  <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                    <tr>
                      <th className="px-3 py-2">Habitation</th>
                      <th className="px-3 py-2 text-center" title="carrying cap of each site">
                        Overall cap
                      </th>
                      <th className="px-3 py-2">Assigned safe site</th>
                      <th className="px-3 py-2 text-right">People</th>
                      <th className="px-3 py-2 text-center">MCDA</th>
                      <th className="px-3 py-2 text-center">Split</th>
                    </tr>
                  </thead>
                  <tbody>
                    {p.allocations.map((a, i) => {
                      const d = DEMO_DESTINATIONS.find((dd) => dd.code === a.destination_code);
                      const split = p.split_demands > 0;
                      return (
                        <tr key={`${a.habitation_id}-${i}`} className="border-t border-border">
                          <td className="px-3 py-2 font-medium">
                            {a.habitation_code}
                            <span className="ml-2 text-xs text-muted-foreground">#{a.habitation_id}</span>
                          </td>
                          <td className="px-3 py-2 text-center">
                            <span className="inline-flex items-center gap-1 rounded bg-emerald-500/10 px-1.5 py-0.5 text-emerald-300">
                              {d ? bottleneckOverall(d.housing, d.water, d.healthcare, d.safeLand, d.accessibility) : "-"}
                            </span>
                          </td>
                          <td className="px-3 py-2">
                            {d?.name ?? a.destination_code}
                            {d && (
                              <span className="ml-1 rounded border border-border px-1 text-[10px] text-amber-300">
                                {d.limiter}
                              </span>
                            )}
                          </td>
                          <td className="px-3 py-2 text-right">{formatNumber(a.persons_allocated)}</td>
                          <td className="px-3 py-2 text-center">{a.score.toFixed(2)}</td>
                          <td className="px-3 py-2 text-center">
                            {d?.allowsSplit ? (
                              <Badge
                                variant={split ? "destructive" : "secondary"}
                                className="gap-1"
                              >
                                <AlertTriangle className="h-3 w-3" />
                                split
                              </Badge>
                            ) : (
                              <span className="text-xs text-muted-foreground">—</span>
                            )}
                          </td>
                        </tr>
                      );
                    })}
                  </tbody>
                </table>
              </div>
            )}
          </CardContent>
        </Card>

        {/* destination ranking table */}
        <Card>
          <CardHeader>
            <CardTitle>Destination ranking</CardTitle>
            <CardDescription>
              MCDA utility = safety·w + access·w + capacity(overall)·w + infra·w − dist·w
            </CardDescription>
          </CardHeader>
          <CardContent className="overflow-x-auto">
            <table className="w-full text-left text-sm">
              <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                <tr>
                  <th className="px-3 py-2">Rank</th>
                  <th className="px-3 py-2">Destination</th>
                  <th className="px-3 py-2">District</th>
                  <th className="px-3 py-2 text-center">MCDA score</th>
                  <th className="px-3 py-2 text-right">Distance (km)</th>
                  <th className="px-3 py-2 text-center">Overall cap</th>
                  <th className="px-3 py-2 text-center">Available</th>
                  <th className="px-3 py-2">Governing bottleneck</th>
                </tr>
              </thead>
              <tbody>
                {dests.map((d, idx) => {
                  const overall = Math.min(d.housing, d.water, d.healthcare, d.safeLand, d.accessibility);
                  const minName =
                    overall === d.healthcare
                      ? "Healthcare"
                      : overall === d.safeLand
                        ? "Safe Land"
                        : overall === d.accessibility
                          ? "Accessibility"
                          : overall === d.water
                            ? "Water"
                            : "Housing";
                  return (
                    <tr key={d.code} className="border-t border-border">
                      <td className="px-3 py-2">{idx + 1}</td>
                      <td className="px-3 py-2 font-medium">{d.name}</td>
                      <td className="px-3 py-2 text-muted-foreground">{d.district_code}</td>
                      <td className="px-3 py-2 text-center">{d.mlcdScore.toFixed(2)}</td>
                      <td className="px-3 py-2 text-right">{d.distanceKm.toFixed(1)}</td>
                      <td className="px-3 py-2 text-center">{overall}</td>
                      <td className="px-3 py-2 text-center text-emerald-300">{d.available}</td>
                      <td className="px-3 py-2">
                        <span className="inline-flex items-center gap-1 rounded border border-amber-500/40 bg-amber-500/10 px-1.5 py-0.5 text-xs text-amber-200">
                          {minName} = min(…)= {overall}
                        </span>
                      </td>
                    </tr>
                  );
                })}
              </tbody>
            </table>
          </CardContent>
        </Card>

        <div className="flex flex-wrap gap-3">
          <Button variant="outline">
            <ArrowRight className="mr-1 h-4 w-4" /> Review authorised workflow
          </Button>
        </div>
      </div>
    </CommandShell>
  );
}

function bottleneckOverall(h: number, w: number, hc: number, l: number, a: number): number {
  return Math.min(h, w, hc, l, a);
}

function LeadStat({
  label,
  value,
  hint,
  warn,
}: {
  label: string;
  value: string;
  hint: string;
  warn?: boolean;
}) {
  return (
    <Card className={warn ? "border-amber-500/50" : ""}>
      <CardHeader className="pb-2">
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent>
        <p className="text-2xl font-semibold">{value}</p>
        <p className="text-xs text-muted-foreground">{hint}</p>
      </CardContent>
    </Card>
  );
}

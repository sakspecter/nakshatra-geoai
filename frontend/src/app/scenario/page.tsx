"use client";

import * as React from "react";
import { FlaskConical, Info } from "lucide-react";
import CommandShell from "@/components/layout/command-shell";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from "@/components/ui/card";
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from "@/components/ui/select";
import { Slider } from "@/components/ui/slider";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Label } from "@/components/ui/label";
import { simulateScenario, getStates, getDistricts } from "@/lib/api";
import { demoOverview } from "@/lib/demo";
import type {
  DistrictMeta,
  ScenarioSimulation,
  ScenarioTriggerPayload,
  StateMeta,
  HabitationDeltaRow,
} from "@/lib/types";
import { HAZARD_META } from "@/lib/constants";

const HAZ_KEYS = Object.keys(HAZARD_META) as Array<keyof typeof HAZARD_META>;

export default function ScenarioPage() {
  const [pct, setPct] = React.useState(15);
  const [hazard, setHazard] = React.useState("cloudburst");
  // cascading geography: State -> District (nationwide, backend-driven)
  const [stateScope, setStateScope] = React.useState<string>("UK");
  const [districtScope, setDistrictScope] = React.useState<string>("CHAMOLI");
  const [states, setStates] = React.useState<StateMeta[]>([]);
  const [districts, setDistricts] = React.useState<DistrictMeta[]>([]);
  const [result, setResult] = React.useState<ScenarioSimulation | null>(null);
  const [running, setRunning] = React.useState(false);

  const baseline = demoOverview();

  React.useEffect(() => {
    getStates().then((d) => setStates(d.payload));
  }, []);

  React.useEffect(() => {
    setDistricts([]);
    if (stateScope === "ALL") return;
    getDistricts(stateScope).then((d) => {
      setDistricts(d.payload);
      if (!d.payload.some((x) => x.district_code === districtScope)) {
        setDistrictScope(d.payload[0]?.district_code ?? "");
      }
    });
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [stateScope]);

  async function run() {
    const scopeAll = stateScope === "ALL";
    const triggers: ScenarioTriggerPayload[] = [
      {
        kind: "rainfall_pct",
        factor: 1 + pct / 100,
        hazard_types: [hazard as ScenarioTriggerPayload["hazard_types"][number]],
        district: !scopeAll && districtScope ? districtScope : null,
        state: !scopeAll ? stateScope : null,
        scope_all: scopeAll,
      },
    ];
    setRunning(true);
    try {
      const r = await simulateScenario({ name: "Stress test", triggers });
      setResult(r.payload);
    } finally {
      setRunning(false);
    }
  }

  const deltaRed = result ? result.side_by_side.scenario_red_zones - result.side_by_side.baseline_red_zones : 0;
  const newDemand = result ? Math.round(result.delta.new_relocation_demand ?? 0) : 0;
  const strain = result ? Math.round(Number(result.delta.capacity_strain_pct ?? 0) * 10) / 10 : 0;

  return (
    <CommandShell active="scenario">
      <div className="grid grid-cols-1 gap-6 xl:grid-cols-[380px_1fr]">
        <div className="space-y-4">
          {/* Non-negotiable banner */}
          <Alert variant="warning">
            <Info className="h-4 w-4" />
            <AlertTitle className="tracking-wide">SIMULATION MODE — baseline data remains immutable</AlertTitle>
            <AlertDescription>
              Every run computes against the versioned snapshot and never edits the
              live baseline (Rule 5). Results are exploratory, not operational.
            </AlertDescription>
          </Alert>

          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <FlaskConical className="h-4 w-4" /> Simulation trigger
              </CardTitle>
              <CardDescription>Stress-test rainfall on a regional hazard</CardDescription>
            </CardHeader>
            <CardContent className="space-y-5">
              <div className="space-y-2">
                <div className="flex items-center justify-between text-sm">
                  <Label htmlFor="rain">+ Rainfall intensity</Label>
                  <Badge variant="outline">+{pct}%</Badge>
                </div>
                <Slider
                  value={[pct]}
                  onValueChange={(v) => setPct(v[0])}
                  min={0}
                  max={50}
                  step={5}
                  id="rain"
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="hazard">Hazard to stress</Label>
                <Select value={hazard} onValueChange={setHazard}>
                  <SelectTrigger id="hazard">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {HAZ_KEYS.map((k) => (
                      <SelectItem key={k} value={k}>
                        {HAZARD_META[k].label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>

              <div className="space-y-2">
                <Label>Region scope</Label>
                <div className="grid grid-cols-2 gap-2">
                  <Select value={stateScope} onValueChange={setStateScope}>
                    <SelectTrigger>
                      <SelectValue placeholder="State" />
                    </SelectTrigger>
                    <SelectContent>
                      <SelectItem value="ALL">All states</SelectItem>
                      {states.map((s) => (
                        <SelectItem key={s.state_code} value={s.state_code}>
                          {s.state_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                  <Select
                    value={districtScope}
                    onValueChange={setDistrictScope}
                    disabled={stateScope === "ALL"}
                  >
                    <SelectTrigger>
                      <SelectValue placeholder="District" />
                    </SelectTrigger>
                    <SelectContent>
                      {districts.map((d) => (
                        <SelectItem key={d.district_code} value={d.district_code}>
                          {d.district_name}
                        </SelectItem>
                      ))}
                    </SelectContent>
                  </Select>
                </div>
              </div>

              <Button className="w-full" onClick={run} disabled={running}>
                {running ? "Running simulation…" : "Run simulation"}
              </Button>

              {result && (
                <p className="text-center text-xs text-muted-foreground">
                  scenario <span className="text-primary">{result.scenario_id}</span>
                </p>
              )}
            </CardContent>
          </Card>

          <Card className="border-amber-500/40 bg-amber-500/5">
            <CardHeader className="pb-2">
              <CardTitle className="text-sm">Immutable guard</CardTitle>
            </CardHeader>
            <CardContent className="text-xs text-muted-foreground">
              Trigger = +{pct}% {HAZARD_META[hazard as keyof typeof HAZARD_META]?.label ?? hazard} at scope{" "}
              {stateScope === "ALL" ? "all states" : `${stateScope} · ${districtScope || "-"}`}. Baseline remains {baseline.totals.red_zone_count} red /{" "}
              {baseline.totals.habitation_count} habitations.
            </CardContent>
          </Card>
        </div>

        {/* side-by-side comparison */}
        <div className="space-y-6">
          {!result ? (
            <EmptyComparison />
          ) : (
            <>
              <div className="grid grid-cols-3 gap-4">
                <DeltaCard label="Red-zone count" baseline={result.side_by_side.baseline_red_zones} scenario={result.side_by_side.scenario_red_zones} delta={deltaRed} />
                <DeltaCard label="New relocation demand" baseline={0} scenario={newDemand} delta={newDemand} units="people" />
                <DeltaCard label="Capacity strain" baseline={0} scenario={strain} delta={strain} units="%" />
              </div>

              <Card>
                <CardHeader>
                  <CardTitle>Side-by-side snapshot vs baseline</CardTitle>
                  <CardDescription>
                    Advisory pipeline comparing live baseline (source:{" "}
                    {result.baseline_dataset_version}) against simulated variant
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  <table className="w-full text-left text-sm">
                    <thead className="bg-muted/40 text-xs uppercase text-muted-foreground">
                      <tr>
                        <th className="px-3 py-2">Metric</th>
                        <th className="px-3 py-2 text-right">Baseline</th>
                        <th className="px-3 py-2 text-right">Scenario</th>
                        <th className="px-3 py-2 text-right">Δ</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y divide-border">
                      <CompareRow title="Red zones" a={bl(result, "baseline_red_zones")} b={bl(result, "scenario_red_zones")} />
                      <CompareRow title="Green (safe)" a={bl(result, "baseline_green")} b={bl(result, "scenario_green")} invert />
                      <CompareRow title="Relocation demand" a={result.delta.new_relocation_demand ? 0 : 0} b={bl(result, "scenario_relocation_demand") || Number(result.delta.new_relocation_demand ?? 0)} />
                    </tbody>
                  </table>
                  <p className="mt-3 flex items-center gap-1 text-xs text-amber-300">
                    <Info className="h-3.5 w-3.5" />
                    All cells rendered from {result.triggered_on.length ?? 0} trigger set. Baseline untouched.
                  </p>
                </CardContent>
              </Card>

              <Card>
                <CardHeader>
                  <CardTitle>Habitation-wise risk delta</CardTitle>
                  <CardDescription>
                    Itemized row-set: pre/post risk scores and zone movement per settlement
                  </CardDescription>
                </CardHeader>
                <CardContent>
                  {(() => {
                    const deltaRows = normalizeDeltaRows(result);
                    if (deltaRows.length === 0) {
                      return (
                        <p className="py-6 text-center text-sm text-muted-foreground">
                          No row-level data was produced for this run (the backend returned
                          neither habitation_deltas nor rows). Verify the simulator workspace.
                        </p>
                      );
                    }
                    const degraded = deltaRows.filter((r) => r.delta_category === "Degraded").length;
                    const improved = deltaRows.filter((r) => r.delta_category === "Improved").length;
                    return (
                      <div className="space-y-2">
                        <div className="flex flex-wrap items-center gap-2 pb-1">
                          <Badge variant="outline">{deltaRows.length} rows</Badge>
                          <Badge className="bg-red-500/15 text-red-300">{degraded} degraded</Badge>
                          <Badge className="bg-emerald-500/15 text-emerald-300">{improved} improved</Badge>
                        </div>
                        <div className="max-h-80 overflow-y-auto rounded-md border">
                          <table className="w-full text-left text-sm">
                            <thead className="sticky top-0 z-10 bg-muted/95 text-xs uppercase text-muted-foreground backdrop-blur">
                              <tr>
                                <th className="px-3 py-2">Habitation</th>
                                <th className="px-3 py-2">District</th>
                                <th className="px-2 py-2 text-right">Pre</th>
                                <th className="px-2 py-2 text-right">Post</th>
                                <th className="px-2 py-2 text-right">Δ risk</th>
                                <th className="px-3 py-2">Category</th>
                              </tr>
                            </thead>
                            <tbody className="divide-y divide-border">
                              {deltaRows.map((r) => (
                                <tr key={r.habitation_id} className="hover:bg-muted/40">
                                  <td className="px-3 py-2">
                                    <span className="font-medium">{r.habitation_name || `#${r.habitation_id}`}</span>
                                    <span className="ml-2 text-xs text-muted-foreground">{r.habitation_code}</span>
                                  </td>
                                  <td className="px-3 py-2 text-muted-foreground">{r.district_code || "—"}</td>
                                  <td className="px-2 py-2 text-right tabular-nums">{r.pre_risk_score.toFixed(3)}</td>
                                  <td className="px-2 py-2 text-right tabular-nums">{r.post_risk_score.toFixed(3)}</td>
                                  <td
                                    className={`px-2 py-2 text-right tabular-nums ${
                                      r.risk_delta > 0
                                        ? "text-amber-300"
                                        : r.risk_delta < 0
                                          ? "text-emerald-300"
                                          : ""
                                    }`}
                                  >
                                    {r.risk_delta > 0 ? "+" : ""}
                                    {r.risk_delta.toFixed(3)}
                                  </td>
                                  <td className="px-3 py-2">
                                    <span
                                      className={`inline-flex items-center rounded border px-1.5 py-0.5 text-xs ${
                                        r.delta_category === "Degraded"
                                          ? "border-red-500/40 bg-red-500/10 text-red-300"
                                          : r.delta_category === "Improved"
                                            ? "border-emerald-500/40 bg-emerald-500/10 text-emerald-300"
                                            : "border-border text-muted-foreground"
                                      }`}
                                    >
                                      {r.delta_category}
                                    </span>
                                  </td>
                                </tr>
                              ))}
                            </tbody>
                          </table>
                        </div>
                      </div>
                    );
                  })()}
                </CardContent>
              </Card>
            </>
          )}
        </div>
      </div>
    </CommandShell>
  );
}

function bl(r: ScenarioSimulation, key: string): number {
  return Number(r.side_by_side[key] ?? 0);
}

/**
 * Normalize the simulator response into itemized delta rows.
 *
 * Prefers the explicit `habitation_deltas` row-set; transparently derives an
 * equivalent set from the legacy `rows` contract (adding names/categories) so
 * older payloads and demo fallbacks still render the table. Returns [] only
 * when the run genuinely produced no row-level data.
 */
function normalizeDeltaRows(result: ScenarioSimulation): HabitationDeltaRow[] {
  const explicit = result.habitation_deltas ?? [];
  if (explicit.length > 0) return explicit;

  return (result.rows ?? []).map((r) => {
    const delta = r.risk_delta ?? 0;
    return {
      habitation_id: r.habitation_id,
      habitation_name: r.habitation_name ?? "",
      habitation_code: r.habitation_code ?? "",
      state_code: r.state_code ?? "",
      district_code: r.district_code ?? "",
      pre_risk_score: r.baseline_risk,
      post_risk_score: r.scenario_risk,
      risk_delta: delta,
      delta_category:
        delta > 0 ? "Degraded" : delta < 0 ? "Improved" : "Unchanged",
    };
  });
}

function EmptyComparison() {
  return (
    <div className="grid place-items-center rounded-xl border border-dashed border-border p-12 text-center">
      <p className="text-lg font-medium text-muted-foreground">No simulation yet</p>
      <p className="max-w-md text-sm text-muted-foreground">
        Adjust the trigger and press <b>Run simulation</b>. Output is always
        advisory and explicitly flagged SIMULATION MODE.
      </p>
    </div>
  );
}

function DeltaCard({
  label,
  baseline,
  scenario,
  delta,
  units,
}: {
  label: string;
  baseline: number;
  scenario: number;
  delta: number;
  units?: string;
}) {
  return (
    <Card>
      <CardHeader className="pb-0">
        <CardTitle className="text-sm text-muted-foreground">{label}</CardTitle>
      </CardHeader>
      <CardContent className="pt-3">
        <p className="text-2xl font-semibold">
          {baseline} <span className="mx-1 text-sm text-muted-foreground">→</span> {scenario}
          {units && <span className="ml-1 text-xs text-muted-foreground">{units}</span>}
        </p>
        <Badge variant={delta > 0 ? "destructive" : delta < 0 ? "secondary" : "outline"} className="mt-1">
          {delta > 0 ? "Δ +" + delta : delta < 0 ? "Δ " + delta : "no change"}
        </Badge>
      </CardContent>
    </Card>
  );
}

function CompareRow({ title, a, b, invert }: { title: string; a: number; b: number; invert?: boolean }) {
  const delta = invert ? a - b : b - a;
  return (
    <tr className="text-xs">
      <td className="px-3 py-2 text-muted-foreground">{title}</td>
      <td className="px-3 py-2 text-right">{a}</td>
      <td className="px-3 py-2 text-right font-medium">{b}</td>
      <td className={`px-3 py-2 text-right ${delta > 0 ? "text-amber-300" : delta < 0 ? "text-emerald-300" : ""}`}>
        {delta > 0 ? "+" : ""}
        {delta}
      </td>
    </tr>
  );
}

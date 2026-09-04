"use client";

/**
 * Admin Spatial Ingestion - zero-code nationwide district onboarding.
 *
 * Upload raw GIS boundaries (GeoJSON / JSON / Zipped Shapefile / Geopackage)
 * for ANY Indian district; the backend runs the spatial pipeline
 * (CRS normalize -> joins -> ML inference -> capacity) and the district is
 * immediately available to the dashboard selectors and the risk map.
 */

import * as React from "react";
import {
  CloudUpload,
  Database,
  FileUp,
  Loader2,
  MapPinned,
  RotateCcw,
  Sparkles,
  TriangleAlert,
  Wand2,
} from "lucide-react";
import CommandShell from "@/components/layout/command-shell";
import { Alert, AlertDescription, AlertTitle } from "@/components/ui/alert";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Card,
  CardContent,
  CardDescription,
  CardHeader,
  CardTitle,
} from "@/components/ui/card";
import { Input } from "@/components/ui/input";
import { Label } from "@/components/ui/label";
import { Progress } from "@/components/ui/progress";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Tabs, TabsContent, TabsList, TabsTrigger } from "@/components/ui/tabs";
import { ToastProvider, useToast } from "@/components/ui/toast";
import {
  getGeoOptions,
  ingestDistrict,
  ingestDistrictAuto,
} from "@/lib/api";
import type { IngestResult } from "@/lib/types";
import { cn } from "@/lib/utils";

/** Stages mirrored 1:1 from the backend pipeline (PIPELINE_STAGES). */
const STAGES = [
  "Uploading",
  "Normalizing CRS",
  "Spatial Joins",
  "Running ML Inference",
  "Computing Capacity Limits",
  "Complete",
] as const;

const ACCEPTED = ".json,.geojson,.zip,.gpkg";

export default function AdminUploadPage() {
  // toast context must wrap the consumer, so the workspace mounts it here
  return (
    <ToastProvider>
      <AdminUploadInner />
    </ToastProvider>
  );
}

function AdminUploadInner() {
  const { toast } = useToast();
  const [tab, setTab] = React.useState<"quick" | "upload">("quick");

  // shared pipeline state
  const [stageIndex, setStageIndex] = React.useState(-1);
  const [error, setError] = React.useState<string | null>(null);
  const [result, setResult] = React.useState<IngestResult | null>(null);
  const running = stageIndex >= 0 && stageIndex < STAGES.length - 1;

  // ---- Quick Ingest state (auto-fetch from GADM) ----
  const [states, setStates] = React.useState<string[]>([]);
  const [districts, setDistricts] = React.useState<string[]>([]);
  const [quickState, setQuickState] = React.useState<string>("");
  const [quickDistrict, setQuickDistrict] = React.useState<string>("");
  const [nSettlements, setNSettlements] = React.useState(15);

  React.useEffect(() => {
    let alive = true;
    getGeoOptions()
      .then((d) => {
        if (alive) setStates(d.states ?? []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, []);

  React.useEffect(() => {
    if (!quickState) return;
    let alive = true;
    setDistricts([]);
    setQuickDistrict("");
    getGeoOptions(quickState)
      .then((d) => {
        if (alive) setDistricts(d.districts ?? []);
      })
      .catch(() => {});
    return () => {
      alive = false;
    };
  }, [quickState]);

  const startQuick = React.useCallback(async () => {
    if (!quickState.trim() || !quickDistrict.trim()) {
      setError("Pick both a state and a district.");
      return;
    }
    setError(null);
    setResult(null);
    setStageIndex(0);

    const timers: ReturnType<typeof setTimeout>[] = [];
    for (let i = 1; i < STAGES.length - 1; i++) {
      timers.push(setTimeout(() => setStageIndex(i), 700 * i));
    }

    try {
      const res = await ingestDistrictAuto({
        stateName: quickState.trim(),
        districtName: quickDistrict.trim(),
        nSettlements,
      });
      timers.forEach(clearTimeout);
      setStageIndex(STAGES.length - 1);
      setResult(res);
      toast(
        `District ${res.district_name} (${res.state_name}) successfully processed: ${res.habitations_loaded} habitations loaded.`,
        { title: "Ingestion complete", variant: "success" }
      );
    } catch (e) {
      timers.forEach(clearTimeout);
      setStageIndex(-1);
      const message = e instanceof Error ? e.message : "Ingestion failed.";
      setError(message);
      toast(message, { title: "Ingestion failed", variant: "error" });
    }
  }, [quickState, quickDistrict, nSettlements, toast]);

  // ---- File Upload state ----
  const [stateName, setStateName] = React.useState("Sikkim");
  const [districtName, setDistrictName] = React.useState("Namchi");
  const [file, setFile] = React.useState<File | null>(null);
  const [dragOver, setDragOver] = React.useState(false);
  const inputRef = React.useRef<HTMLInputElement>(null);

  const startUpload = React.useCallback(async () => {
    if (!stateName.trim() || !districtName.trim()) {
      setError("Both a state name and a district name are required.");
      return;
    }
    if (!file) {
      setError("Attach a .json / .geojson / .zip (shapefile) / .gpkg boundary file.");
      return;
    }
    setError(null);
    setResult(null);
    setStageIndex(0);

    const timers: ReturnType<typeof setTimeout>[] = [];
    for (let i = 1; i < STAGES.length - 1; i++) {
      timers.push(setTimeout(() => setStageIndex(i), 700 * i));
    }

    const form = new FormData();
    form.append("state_name", stateName.trim());
    form.append("district_name", districtName.trim());
    form.append("file", file);

    try {
      const res = await ingestDistrict(form);
      timers.forEach(clearTimeout);
      setStageIndex(STAGES.length - 1);
      setResult(res);
      toast(
        `District ${res.district_name} (${res.state_name}) successfully processed: ${res.habitations_loaded} habitations loaded.`,
        { title: "Ingestion complete", variant: "success" }
      );
    } catch (e) {
      timers.forEach(clearTimeout);
      setStageIndex(-1);
      const message = e instanceof Error ? e.message : "Ingestion failed.";
      setError(message);
      toast(message, { title: "Ingestion failed", variant: "error" });
    }
  }, [stateName, districtName, file, toast]);

  const reset = () => {
    setStageIndex(-1);
    setResult(null);
    setError(null);
    setFile(null);
  };

  return (
    <CommandShell active="admin">
      <div className="space-y-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <h1 className="flex items-center gap-2 text-2xl font-semibold tracking-tight">
              <MapPinned className="h-6 w-6" /> Admin · Spatial Ingestion
            </h1>
            <p className="mt-1 max-w-2xl text-sm text-muted-foreground">
              Onboard any Indian district without code changes. Pick a state and
              district to auto-fetch the boundary, or upload your own file.
            </p>
          </div>
          <Badge variant="outline" className="uppercase">
            Zero-code nationwide expansion
          </Badge>
        </div>

        <Alert variant="info">
          <Sparkles className="h-4 w-4" />
          <AlertTitle>Advisory pipeline with full provenance</AlertTitle>
          <AlertDescription>
            Every ingested settlement carries a dataset version and an explicit
            confidence flag. Missing terrain layers are marked low-confidence —
            never fabricated as safe (Rule 2).
          </AlertDescription>
        </Alert>

        <div className="grid grid-cols-1 gap-6 xl:grid-cols-[420px_1fr]">
          <Card>
            <CardHeader>
              <CardTitle className="flex items-center gap-2 text-base">
                <Database className="h-4 w-4" /> Ingestion method
              </CardTitle>
              <CardDescription>
                Quick Ingest auto-fetches the district boundary — no file needed
              </CardDescription>
            </CardHeader>
            <CardContent>
              <Tabs
                value={tab}
                onValueChange={(v) => setTab(v as "quick" | "upload")}
                className="w-full"
              >
                <TabsList className="grid w-full grid-cols-2">
                  <TabsTrigger value="quick">
                    <Wand2 className="mr-2 h-4 w-4" /> Quick Ingest
                  </TabsTrigger>
                  <TabsTrigger value="upload">
                    <FileUp className="mr-2 h-4 w-4" /> Upload File
                  </TabsTrigger>
                </TabsList>

                <TabsContent value="quick" className="mt-4 space-y-4">
                  <div className="space-y-1.5">
                    <Label>State</Label>
                    <Select value={quickState} onValueChange={setQuickState}>
                      <SelectTrigger>
                        <SelectValue placeholder="Select state" />
                      </SelectTrigger>
                      <SelectContent>
                        {states.length === 0 && (
                          <SelectItem value="__loading" disabled>
                            Loading states…
                          </SelectItem>
                        )}
                        {states.map((s) => (
                          <SelectItem key={s} value={s}>
                            {s}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label>District</Label>
                    <Select
                      value={quickDistrict}
                      onValueChange={setQuickDistrict}
                      disabled={!quickState || districts.length === 0}
                    >
                      <SelectTrigger>
                        <SelectValue
                          placeholder={quickState ? "Select district" : "Pick state first"}
                        />
                      </SelectTrigger>
                      <SelectContent>
                        {districts.map((d) => (
                          <SelectItem key={d} value={d}>
                            {d}
                          </SelectItem>
                        ))}
                      </SelectContent>
                    </Select>
                  </div>
                  <div className="space-y-1.5">
                    <Label htmlFor="n-settlements">
                      Settlements: {nSettlements}
                    </Label>
                    <input
                      id="n-settlements"
                      type="range"
                      min={3}
                      max={50}
                      value={nSettlements}
                      onChange={(e) => setNSettlements(Number(e.target.value))}
                      className="w-full"
                    />
                    <p className="text-xs text-muted-foreground">
                      Number of representative settlements generated inside the district
                    </p>
                  </div>
                  {tab === "quick" && error && (
                    <Alert variant="destructive">
                      <TriangleAlert className="h-4 w-4" />
                      <AlertDescription>{error}</AlertDescription>
                    </Alert>
                  )}
                  <div className="flex gap-2">
                    <Button className="flex-1" onClick={startQuick} disabled={running}>
                      {running ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processing…
                        </>
                      ) : (
                        <>
                          <Wand2 className="mr-2 h-4 w-4" /> Fetch &amp; Ingest
                        </>
                      )}
                    </Button>
                    <Button variant="outline" onClick={reset} disabled={running}>
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  </div>
                </TabsContent>

                <TabsContent value="upload" className="mt-4 space-y-4">
                  <div className="grid grid-cols-2 gap-3">
                    <div className="space-y-1.5">
                      <Label htmlFor="ing-state">State name</Label>
                      <Input
                        id="ing-state"
                        value={stateName}
                        onChange={(e) => setStateName(e.target.value)}
                        placeholder="Sikkim"
                        disabled={running}
                      />
                    </div>
                    <div className="space-y-1.5">
                      <Label htmlFor="ing-district">District name</Label>
                      <Input
                        id="ing-district"
                        value={districtName}
                        onChange={(e) => setDistrictName(e.target.value)}
                        placeholder="Namchi"
                        disabled={running}
                      />
                    </div>
                  </div>

                  <DropZone
                    file={file}
                    dragOver={dragOver}
                    disabled={running}
                    onFile={(f) => {
                      setFile(f);
                      setError(null);
                    }}
                    onDragOverChange={setDragOver}
                    onBrowse={() => inputRef.current?.click()}
                  />
                  <input
                    ref={inputRef}
                    type="file"
                    accept={ACCEPTED}
                    className="hidden"
                    onChange={(e) => {
                      const f = e.target.files?.[0] ?? null;
                      if (f) setFile(f);
                      e.target.value = "";
                    }}
                  />

                  {tab === "upload" && error && (
                    <Alert variant="destructive">
                      <TriangleAlert className="h-4 w-4" />
                      <AlertDescription>{error}</AlertDescription>
                    </Alert>
                  )}

                  <div className="flex gap-2">
                    <Button className="flex-1" onClick={startUpload} disabled={running}>
                      {running ? (
                        <>
                          <Loader2 className="mr-2 h-4 w-4 animate-spin" /> Processing…
                        </>
                      ) : (
                        <>
                          <CloudUpload className="mr-2 h-4 w-4" /> Start ingestion
                        </>
                      )}
                    </Button>
                    <Button variant="outline" onClick={reset} disabled={running}>
                      <RotateCcw className="h-4 w-4" />
                    </Button>
                  </div>
                </TabsContent>
              </Tabs>
            </CardContent>
          </Card>

          <div className="space-y-4">
            <PipelineProgress stageIndex={stageIndex} />
            {result && <ResultCard result={result} />}
            {!result && !running && (
              <Card className="border-dashed">
                <CardContent className="py-10 text-center text-sm text-muted-foreground">
                  No ingestion yet. Use <b>Quick Ingest</b> to auto-fetch a district, or{" "}
                  <b>Upload File</b> with your own boundaries.
                </CardContent>
              </Card>
            )}
          </div>
        </div>
      </div>
    </CommandShell>
  );
}

function DropZone({
  file,
  dragOver,
  disabled,
  onFile,
  onDragOverChange,
  onBrowse,
}: {
  file: File | null;
  dragOver: boolean;
  disabled: boolean;
  onFile: (f: File | null) => void;
  onDragOverChange: (v: boolean) => void;
  onBrowse: () => void;
}) {
  return (
    <div
      role="button"
      tabIndex={0}
      aria-label="Drag and drop a GIS boundary file or browse"
      onClick={() => !disabled && onBrowse()}
      onKeyDown={(e) => {
        if ((e.key === "Enter" || e.key === " ") && !disabled) onBrowse();
      }}
      onDragOver={(e) => {
        e.preventDefault();
        if (!disabled) onDragOverChange(true);
      }}
      onDragLeave={() => onDragOverChange(false)}
      onDrop={(e) => {
        e.preventDefault();
        onDragOverChange(false);
        if (disabled) return;
        const f = e.dataTransfer.files?.[0];
        if (f) onFile(f);
      }}
      className={cn(
        "grid cursor-pointer place-items-center rounded-lg border-2 border-dashed p-6 text-center transition",
        dragOver ? "border-primary bg-primary/10" : "border-border hover:border-primary/60",
        disabled && "cursor-not-allowed opacity-60"
      )}
    >
      <CloudUpload className="mb-2 h-8 w-8 text-muted-foreground" />
      {file ? (
        <p className="text-sm">
          <span className="font-medium">{file.name}</span>{" "}
          <span className="text-muted-foreground">
            ({(file.size / 1024).toFixed(1)} KB)
          </span>
        </p>
      ) : (
        <>
          <p className="text-sm font-medium">Drag &amp; drop the boundary file here</p>
          <p className="mt-1 text-xs text-muted-foreground">
            .json · .geojson · .zip (shapefile) · .gpkg — or click to browse
          </p>
        </>
      )}
    </div>
  );
}

function PipelineProgress({ stageIndex }: { stageIndex: number }) {
  const pct = stageIndex < 0 ? 0 : ((stageIndex + 1) / STAGES.length) * 100;
  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base">Ingestion pipeline</CardTitle>
        <CardDescription>
          {stageIndex < 0
            ? "Idle — awaiting upload"
            : stageIndex === STAGES.length - 1
              ? "Complete"
              : `${STAGES[stageIndex]}…`}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-4">
        <Progress value={pct} className="h-2" />
        <ol className="space-y-2">
          {STAGES.map((stage, idx) => {
            const state =
              idx < stageIndex ? "done" : idx === stageIndex ? "active" : "pending";
            return (
              <li key={stage} className="flex items-center gap-3 text-sm">
                <span
                  className={cn(
                    "grid h-6 w-6 place-items-center rounded-full border text-xs",
                    state === "done" &&
                      "border-emerald-500/60 bg-emerald-500/15 text-emerald-300",
                    state === "active" && "border-primary bg-primary/15 text-primary",
                    state === "pending" && "border-border text-muted-foreground"
                  )}
                >
                  {state === "done" ? "✓" : idx + 1}
                </span>
                <span
                  className={cn(
                    state === "pending" && "text-muted-foreground",
                    state === "active" && "font-medium"
                  )}
                >
                  {stage}
                  {state === "active" && (
                    <Loader2 className="ml-2 inline h-3.5 w-3.5 animate-spin" />
                  )}
                </span>
              </li>
            );
          })}
        </ol>
      </CardContent>
    </Card>
  );
}

function ResultCard({ result }: { result: IngestResult }) {
  const zones = result.zone_breakdown ?? {};
  return (
    <Card className="border-emerald-500/40 bg-emerald-500/5">
      <CardHeader className="pb-2">
        <CardTitle className="flex items-center gap-2 text-base text-emerald-300">
          <MapPinned className="h-4 w-4" /> {result.district_name} is live
        </CardTitle>
        <CardDescription>
          {result.district_code} · {result.state_name} · terrain: {result.terrain} ·{" "}
          {result.model_version}
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        <div className="grid grid-cols-2 gap-3 sm:grid-cols-4">
          <Stat label="Habitations" value={String(result.habitations_loaded)} />
          <Stat label="Red zones" value={String(zones.red ?? 0)} tone="text-red-300" />
          <Stat label="Yellow zones" value={String(zones.yellow ?? 0)} tone="text-amber-300" />
          <Stat label="Green zones" value={String(zones.green ?? 0)} tone="text-emerald-300" />
        </div>
        <p className="text-xs text-muted-foreground">
          Governing capacity bottleneck:{" "}
          <b className="text-foreground">{result.capacity_limiter ?? "n/a"}</b> · bbox [
          {result.bbox.map((v) => v.toFixed(3)).join(", ")}] · dataset{" "}
          {result.dataset_version}
        </p>
      </CardContent>
    </Card>
  );
}

function Stat({
  label,
  value,
  tone,
}: {
  label: string;
  value: string;
  tone?: string;
}) {
  return (
    <div className="rounded-lg border border-border bg-background/60 p-3">
      <p className="text-xs text-muted-foreground">{label}</p>
      <p className={cn("text-xl font-semibold", tone)}>{value}</p>
    </div>
  );
}
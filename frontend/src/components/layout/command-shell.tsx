"use client";

import * as React from "react";
import Link from "next/link";
import { usePathname } from "next/navigation";
import {
  ArrowRightLeft,
  Database,
  FlaskConical,
  LayoutDashboard,
  Map,
  Users,
} from "lucide-react";
import { cn } from "@/lib/utils";
import { STATES } from "@/lib/constants";
import { Badge } from "@/components/ui/badge";
import { Button } from "@/components/ui/button";
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from "@/components/ui/select";
import { Separator } from "@/components/ui/separator";
import { useAppState } from "@/contexts/app-state";

type ScreenKey =
  | "overview"
  | "map"
  | "settlement"
  | "relocation"
  | "scenario";

const NAV: Array<{ key: ScreenKey; href: string; label: string; icon: React.ElementType }> = [
  { key: "overview", href: "/overview", label: "Overview Dashboard", icon: LayoutDashboard },
  { key: "map", href: "/map", label: "Multi-Layer Risk Map", icon: Map },
  { key: "settlement", href: "/settlement/102", label: "Settlement Analysis", icon: Users },
  { key: "relocation", href: "/relocation", label: "Relocation Planner", icon: ArrowRightLeft },
  { key: "scenario", href: "/scenario", label: "Scenario Simulator", icon: FlaskConical },
];

export default function CommandShell({
  active,
  children,
}: {
  active: ScreenKey;
  children: React.ReactNode;
}) {
  const pathname = usePathname();
  const { activeState, setActiveState, confidenceState, scenarioVersion, riskConfigVersion } =
    useAppState();

  return (
    <div className="flex h-screen overflow-hidden bg-background">
      {/* Sidebar */}
      <aside className="hidden w-72 shrink-0 flex-col border-r border-border bg-card md:flex">
        <div className="flex h-16 items-center gap-3 border-b border-border px-5">
          <div className="grid h-9 w-9 place-items-center rounded-lg bg-primary text-primary-foreground">
            <Database className="h-5 w-5" />
          </div>
          <div className="leading-tight">
            <p className="text-sm font-semibold text-foreground">Project Nakshatra</p>
            <p className="text-xs text-muted-foreground">Command Dashboard</p>
          </div>
        </div>
        <nav className="flex-1 space-y-1 overflow-y-auto p-3">
          {NAV.map((item) => {
            const selected =
              item.key === active ||
              (item.key === "settlement" && pathname.startsWith("/settlement"));
            return (
              <Button
                key={item.key}
                asChild
                variant={selected ? "secondary" : "ghost"}
                className={cn(
                  "w-full justify-start gap-3 text-sm font-medium",
                  selected && "bg-secondary text-secondary-foreground"
                )}
              >
                <Link href={item.href}>
                  <item.icon className="h-4 w-4 opacity-80" />
                  <span className="flex-1 truncate text-left">{item.label}</span>
                </Link>
              </Button>
            );
          })}
        </nav>
        <Separator />
        <div className="p-5 text-xs text-muted-foreground">
          <p className="mb-1 flex items-center gap-2">
            <span className="inline-block h-2 w-2 rounded-full bg-emerald-400" />
            System operational
          </p>
          <p>UK &amp; Assam pilots · versioned analysis (Rule 6)</p>
        </div>
      </aside>

      {/* Main column */}
      <div className="flex min-w-0 flex-1 flex-col">
        {/* Top bar */}
        <header className="flex h-16 shrink-0 items-center justify-between gap-4 border-b border-border bg-card px-5">
          <div className="flex items-center gap-3 md:hidden">
            <span className="text-sm font-semibold">Nakshatra</span>
          </div>

          {/* Active status + geography */}
          <div className="flex items-center gap-2 text-sm">
            <span className="hidden items-center gap-1.5 sm:inline-flex">
              <span className="h-2.5 w-2.5 animate-pulse rounded-full bg-emerald-400" />
              <span className="font-medium">LIVE</span>
            </span>
            <Badge variant="outline" className="uppercase">
              Geo: {activeState === "ALL" ? "All Pilots" : STATES.find((s) => s.code === activeState)?.label ?? activeState}
            </Badge>
            <Badge
              variant={confidenceState === "confirmed" ? "secondary" : "outline"}
              className="uppercase"
            >
              Data {confidenceState}
            </Badge>
            <Badge variant="outline">{scenarioVersion}</Badge>
            <span className="hidden text-xs text-muted-foreground lg:inline">
              risk_cfg {riskConfigVersion}
            </span>
          </div>

          <div className="flex items-center gap-2">
            <span className="text-xs font-medium uppercase text-muted-foreground">
              Geography
            </span>
            <GeographySelect
              value={activeState}
              onChange={(v) => setActiveState(v as "UK" | "AS" | "ALL")}
            />
          </div>
        </header>

        <main className="min-h-0 flex-1 overflow-y-auto p-5 lg:p-6">{children}</main>
      </div>
    </div>
  );
}

function GeographySelect({
  value,
  onChange,
}: {
  value: string;
  onChange: (v: string) => void;
}) {
  return (
    <Select value={value} onValueChange={onChange}>
      <SelectTrigger className="h-9 w-44">
        <SelectValue placeholder="All Pilots" />
      </SelectTrigger>
      <SelectContent>
        <SelectItem value="ALL">All Pilots</SelectItem>
        <SelectItem value="UK">Uttarakhand</SelectItem>
        <SelectItem value="AS">Assam</SelectItem>
      </SelectContent>
    </Select>
  );
}

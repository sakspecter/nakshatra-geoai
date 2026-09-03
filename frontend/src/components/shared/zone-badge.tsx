"use client";

import type { Zone } from "@/lib/types";
import { cn } from "@/lib/utils";

const ZONE_CLASS: Record<Zone | "missing" | "low_confidence", string> = {
  red: "bg-zone-red/15 text-red-300 border-red-500/40",
  yellow: "bg-zone-yellow/15 text-yellow-300 border-yellow-400/40",
  green: "bg-zone-green/15 text-emerald-300 border-emerald-500/40",
  missing: "border-dashed border-zinc-500 text-zinc-400 bg-transparent",
  low_confidence: "border-dashed border-zinc-400 text-zinc-300 bg-zinc-800/30",
};

export function ZoneBadge({
  zone,
  evidence,
  label,
  className,
  dashed,
}: {
  zone: Zone;
  evidence?: "available" | "missing" | "low_confidence" | "not_applicable";
  label?: string;
  className?: string;
  dashed?: boolean;
}) {
  const effective =
    evidence === "missing"
      ? ("missing" as const)
      : evidence === "low_confidence"
        ? ("low_confidence" as const)
        : zone;
  const text =
    label ??
    (effective === "red"
      ? "High risk"
      : effective === "yellow"
        ? "Medium risk"
        : effective === "green"
          ? "Low risk"
          : effective === "low_confidence"
            ? "Low confidence"
            : "No evidence");

  return (
    <span
      className={cn(
        "inline-flex items-center gap-1.5 rounded-md border px-2 py-0.5 text-xs font-medium",
        ZONE_CLASS[effective],
        (dashed || evidence === "missing" || evidence === "low_confidence") &&
          "border-dashed",
        className
      )}
    >
      <span
        className={cn(
          "inline-block h-2 w-2 rounded-full",
          effective === "red" && "bg-zone-red",
          effective === "yellow" && "bg-zone-yellow",
          effective === "green" && "bg-zone-green",
          (effective === "missing" || effective === "low_confidence") &&
            "bg-zinc-400"
        )}
      />
      {text}
    </span>
  );
}

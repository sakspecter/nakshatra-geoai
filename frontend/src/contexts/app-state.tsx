"use client";

import {
  createContext,
  useContext,
  useMemo,
  useState,
  type ReactNode,
} from "react";
import type { StateCode } from "@/lib/constants";
import type { EvidenceState } from "@/lib/types";

export interface AppStateValue {
  activeState: StateCode | "ALL";
  setActiveState: (s: StateCode | "ALL") => void;
  /** display filter that surfaces a deliberately grey/dashed state for rows
   * whose evidence is missing or low-confidence */
  evidenceFilter: EvidenceState | "all-available";
  setEvidenceFilter: (e: EvidenceState | "all-available") => void;
  confidenceState: "confirmed" | "low_confidence" | "missing";
  scenarioVersion: string;
  datasetVersion: string;
  riskConfigVersion: string;
}

const AppStateContext = createContext<AppStateValue | null>(null);

// Rule 6 version pins surfaced as a top-bar badge
const DEFAULT_DATASET = "seed-baseline.v3";
const DEFAULT_SCENARIO = "scenario.v1";
const DEFAULT_RISK_CFG = "risk_cfg.v1.1";

export function AppStateProvider({ children }: { children: ReactNode }) {
  const [activeState, setActiveState] = useState<StateCode | "ALL">("ALL");
  const [evidenceFilter, setEvidenceFilter] = useState<
    EvidenceState | "all-available"
  >("all-available");

  const confidenceState: AppStateValue["confidenceState"] = "confirmed";

  const value = useMemo<AppStateValue>(
    () => ({
      activeState,
      setActiveState,
      evidenceFilter,
      setEvidenceFilter,
      confidenceState,
      scenarioVersion: DEFAULT_SCENARIO,
      datasetVersion: DEFAULT_DATASET,
      riskConfigVersion: DEFAULT_RISK_CFG,
    }),
    [activeState, evidenceFilter, confidenceState]
  );

  return <AppStateContext.Provider value={value}>{children}</AppStateContext.Provider>;
}

export function useAppState(): AppStateValue {
  const ctx = useContext(AppStateContext);
  if (!ctx) throw new Error("useAppState must be used inside <AppStateProvider>");
  return ctx;
}

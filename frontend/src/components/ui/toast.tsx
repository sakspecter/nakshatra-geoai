"use client";

/**
 * Minimal toast primitive (dependency-free).
 *
 * Wraps the page in <ToastProvider> and calls `toast()` from useToast().
 * Toasts auto-dismiss after `duration` ms and stack bottom-right.
 */

import * as React from "react";
import { AlertCircle, CheckCircle2, Info, X } from "lucide-react";
import { cn } from "@/lib/utils";

type ToastVariant = "success" | "error" | "info";

interface ToastItem {
  id: number;
  title?: string;
  message: string;
  variant: ToastVariant;
}

interface ToastContextValue {
  toast: (message: string, opts?: { title?: string; variant?: ToastVariant; duration?: number }) => void;
}

const ToastContext = React.createContext<ToastContextValue | null>(null);

let nextId = 1;

export function ToastProvider({ children }: { children: React.ReactNode }) {
  const [items, setItems] = React.useState<ToastItem[]>([]);

  const dismiss = React.useCallback((id: number) => {
    setItems((prev) => prev.filter((t) => t.id !== id));
  }, []);

  const toast = React.useCallback<ToastContextValue["toast"]>(
    (message, opts) => {
      const id = nextId++;
      const item: ToastItem = {
        id,
        message,
        title: opts?.title,
        variant: opts?.variant ?? "info",
      };
      setItems((prev) => [...prev, item]);
      window.setTimeout(() => dismiss(id), opts?.duration ?? 6000);
    },
    [dismiss]
  );

  const value = React.useMemo(() => ({ toast }), [toast]);

  return (
    <ToastContext.Provider value={value}>
      {children}
      <div className="pointer-events-none fixed bottom-4 right-4 z-[100] flex w-96 max-w-[calc(100vw-2rem)] flex-col gap-2">
        {items.map((t) => (
          <div
            key={t.id}
            role="status"
            className={cn(
              "pointer-events-auto flex items-start gap-3 rounded-lg border p-4 shadow-lg backdrop-blur",
              t.variant === "success" &&
                "border-emerald-500/50 bg-emerald-950/90 text-emerald-100",
              t.variant === "error" && "border-red-500/50 bg-red-950/90 text-red-100",
              t.variant === "info" && "border-border bg-card text-card-foreground"
            )}
          >
            {t.variant === "success" ? (
              <CheckCircle2 className="mt-0.5 h-4 w-4 shrink-0" />
            ) : t.variant === "error" ? (
              <AlertCircle className="mt-0.5 h-4 w-4 shrink-0" />
            ) : (
              <Info className="mt-0.5 h-4 w-4 shrink-0" />
            )}
            <div className="min-w-0 flex-1">
              {t.title && <p className="text-sm font-semibold">{t.title}</p>}
              <p className="text-sm opacity-90">{t.message}</p>
            </div>
            <button
              type="button"
              aria-label="Dismiss notification"
              className="rounded p-0.5 opacity-70 transition hover:opacity-100"
              onClick={() => dismiss(t.id)}
            >
              <X className="h-4 w-4" />
            </button>
          </div>
        ))}
      </div>
    </ToastContext.Provider>
  );
}

export function useToast(): ToastContextValue {
  const ctx = React.useContext(ToastContext);
  if (!ctx) throw new Error("useToast must be used inside <ToastProvider>");
  return ctx;
}
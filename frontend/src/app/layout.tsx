import type { Metadata } from "next";
import type { ReactNode } from "react";
import "./globals.css";
import { AppStateProvider } from "@/contexts/app-state";

export const metadata: Metadata = {
  title: "Project Nakshatra · Command Dashboard",
  description:
    "GeoAI disaster command & control: risk map, settlement analysis, relocation planning and scenario simulation for the UK & Assam pilots.",
};

export default function RootLayout({
  children,
}: {
  children: ReactNode;
}) {
  return (
    <html lang="en" suppressHydrationWarning>
      <body className="min-h-screen bg-background font-sans text-foreground">
        <AppStateProvider>{children}</AppStateProvider>
      </body>
    </html>
  );
}

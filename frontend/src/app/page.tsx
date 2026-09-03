"use client";

import { useEffect } from "react";
import { useRouter } from "next/navigation";

export default function Home() {
  const router = useRouter();
  useEffect(() => {
    router.replace("/overview");
  }, [router]);
  return (
    <div className="grid min-h-screen place-items-center bg-background text-sm text-muted-foreground">
      <p>Loading command dashboard…</p>
    </div>
  );
}

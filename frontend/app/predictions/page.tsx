"use client";

import dynamic from "next/dynamic";
import { Suspense } from "react";

const PredictionsStudio = dynamic(
  () => import("@/components/PredictionsStudio"),
  {
    ssr: false,
    loading: () => (
      <div className="h-[calc(100vh-8rem)] flex items-center justify-center text-accent font-mono text-xs font-bold tracking-widest uppercase animate-pulse">
        Initializing ST-GCN Canvas...
      </div>
    ),
  }
);

export default function PredictionsPage() {
  return (
    <Suspense fallback={<div className="h-[calc(100vh-8rem)] flex items-center justify-center text-accent font-mono text-xs font-bold tracking-widest uppercase animate-pulse">Initializing ST-GCN Canvas...</div>}>
      <PredictionsStudio />
    </Suspense>
  );
}

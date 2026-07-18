"use client";

import dynamic from "next/dynamic";
import { Skeleton } from "@/components/ui/Skeleton";

const CorrelationNetworkGraph = dynamic(
  () => import("@/components/CorrelationNetworkGraph"),
  {
    ssr: false,
    loading: () => (
      <div className="min-h-[calc(100vh-8rem)] flex flex-col gap-6 w-full max-w-[1600px] mx-auto p-4 md:p-6 justify-center items-center">
        <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10 w-full animate-pulse">
          <div>
            <div className="h-10 w-64 bg-text/10 rounded" />
            <div className="h-4 w-96 bg-text/10 rounded mt-2" />
          </div>
          <div className="h-10 w-80 bg-text/10 rounded" />
        </div>
        <Skeleton className="w-full h-[720px] shape-squircle" />
      </div>
    ),
  }
);

export default function GraphPage() {
  return <CorrelationNetworkGraph />;
}
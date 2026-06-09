import React from "react";

export function TableSkeleton({ rows = 10 }: { rows?: number }) {
  return (
    <div className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] overflow-hidden">
      <div className="h-12 bg-[#2a2a2a] animate-pulse"/>
      {[...Array(rows)].map((_,i) => (
        <div key={i} className="flex gap-4 px-4 py-3 border-t border-[#2a2a2a]">
          {[...Array(6)].map((_,j) => (
            <div key={j} className="h-4 bg-[#2a2a2a] rounded animate-pulse flex-1"/>
          ))}
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] p-6"
      style={{ height }}>
      <div className="h-4 w-48 bg-[#2a2a2a] rounded animate-pulse mb-4"/>
      <div className="h-full bg-[#2a2a2a] rounded animate-pulse opacity-50"/>
    </div>
  );
}

export function StatCardSkeleton() {
  return (
    <div className="bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] p-6">
      <div className="h-3 w-24 bg-[#2a2a2a] rounded animate-pulse mb-3"/>
      <div className="h-8 w-32 bg-[#2a2a2a] rounded animate-pulse mb-2"/>
      <div className="h-3 w-16 bg-[#2a2a2a] rounded animate-pulse"/>
    </div>
  );
}

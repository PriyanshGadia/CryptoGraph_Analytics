import React from "react";

export function TableSkeleton({ rows = 10 }: { rows?: number }) {
  return (
    <div className="glass-flat shape-squircle overflow-hidden border-white/5">
      <div className="h-14 bg-[rgba(var(--text),0.06)] animate-pulse border-b border-white/5"/>
      {[...Array(rows)].map((_,i) => (
        <div key={i} className="flex gap-4 px-6 py-4 border-b border-white/5 last:border-b-0">
          {[...Array(6)].map((_,j) => (
            <div key={j} className="h-5 bg-[rgba(var(--text),0.06)] shape-facet-sm animate-pulse flex-1 relative overflow-hidden">
                <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-[rgba(var(--text),0.06)] to-transparent" />
            </div>
          ))}
        </div>
      ))}
    </div>
  );
}

export function ChartSkeleton({ height = 280 }: { height?: number }) {
  return (
    <div className="glass-flat shape-squircle p-6 relative overflow-hidden" style={{ height }}>
      <div className="h-5 w-64 bg-[rgba(var(--text),0.06)] shape-facet-sm animate-pulse mb-6"/>
      <div className="h-full bg-[rgba(var(--text),0.06)] shape-facet animate-pulse flex items-end px-4 gap-2 pb-4">
        {[...Array(12)].map((_,i) => (
          <div key={i} className="w-full bg-[rgba(var(--text),0.06)] shape-facet-sm" style={{ height: `${Math.max(20, Math.random() * 100)}%` }} />
        ))}
      </div>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_2.5s_infinite] bg-gradient-to-r from-transparent via-[rgba(var(--text),0.06)] to-transparent pointer-events-none" />
    </div>
  );
}

export function StatCardSkeleton() {
  return (
    <div className="glass-flat shape-facet p-6 relative overflow-hidden">
      <div className="h-3 w-24 bg-[rgba(var(--text),0.06)] shape-facet-sm animate-pulse mb-4"/>
      <div className="h-10 w-32 bg-[rgba(var(--text),0.06)] shape-facet-sm animate-pulse mb-3"/>
      <div className="h-3 w-16 bg-[rgba(var(--text),0.06)] shape-facet-sm animate-pulse"/>
      <div className="absolute inset-0 -translate-x-full animate-[shimmer_2s_infinite] bg-gradient-to-r from-transparent via-[rgba(var(--text),0.06)] to-transparent pointer-events-none" />
    </div>
  );
}

"use client";

import useSWR from "swr";
import { fetcher } from "@/lib/api";

function timeAgo(isoString: string | null): string {
  if (!isoString) return "never"
  const diff = Date.now() - new Date(isoString).getTime()
  const hours = Math.floor(diff / 3600000)
  const mins  = Math.floor(diff / 60000)
  if (mins < 60)  return `${mins}m ago`
  if (hours < 24) return `${hours}h ago`
  return `${Math.floor(hours/24)}d ago`
}

export function StatusIndicator({ compact = false }: { compact?: boolean }) {
  const { data } = useSWR("/api/status", fetcher, { refreshInterval: 60000 });

  if (!data) return (
    <div className="flex items-center gap-3">
        <div className="relative flex h-4 w-4">
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-warning opacity-75"></span>
            <span className="relative inline-flex rounded-full h-4 w-4 border-2 border-warning bg-transparent"></span>
        </div>
        {!compact && <span className="text-[9px] uppercase tracking-widest text-text-muted font-mono">Initializing...</span>}
    </div>
  );

  const ohlcvAge = data?.ohlcv_last_updated
    ? (Date.now() - new Date(data.ohlcv_last_updated).getTime()) / 1000 / 3600
    : 999
  const statusColor =
    ohlcvAge < 6  ? "success" :
    ohlcvAge < 24 ? "warning" : "danger"

  return (
    <div className="flex flex-col gap-1 w-full group">
      <div className="flex items-center gap-3">
        {/* Radar Ring */}
        <div className="relative flex h-3 w-3 items-center justify-center">
          <span className={`absolute inline-flex h-6 w-6 rounded-full opacity-40 animate-[ping_2s_cubic-bezier(0,0,0.2,1)_infinite] ${
            statusColor === "success" ? "bg-success" :
            statusColor === "warning" ? "bg-warning" :
            "bg-danger"
          }`}></span>
          <span className={`relative inline-flex rounded-full h-2 w-2 shadow-[0_0_8px_currentColor] ${
            statusColor === "success" ? "bg-success text-success" :
            statusColor === "warning" ? "bg-warning text-warning" :
            "bg-danger text-danger"
          }`}></span>
        </div>
        {!compact && (
          <span className={`text-[10px] uppercase tracking-widest font-mono font-bold transition-colors ${
            statusColor === "success" ? "text-success" :
            statusColor === "warning" ? "text-warning" :
            "text-danger"
          }`}>
            {statusColor === "success" ? "System Online" :
             statusColor === "warning" ? "Sync Pending" :
             "Data Stale"}
          </span>
        )}
      </div>
      {!compact && (
        <div className="flex flex-col gap-0.5 ml-6 opacity-0 max-h-0 overflow-hidden group-hover:opacity-100 group-hover:max-h-20 transition-all duration-300 ease-in-out">
          <span className="text-[8px] text-text-muted uppercase tracking-wider font-mono">Market Data: {timeAgo(data.ohlcv_last_updated)}</span>
          <span className="text-[8px] text-text-muted uppercase tracking-wider font-mono">Predictions: {timeAgo(data.predictions_last_updated)}</span>
        </div>
      )}
    </div>
  );
}

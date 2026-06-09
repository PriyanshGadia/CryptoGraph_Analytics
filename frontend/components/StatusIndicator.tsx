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

export function StatusIndicator() {
  const { data } = useSWR("/api/status", fetcher, { refreshInterval: 60000 });

  if (!data) return <div className="p-4 text-xs text-textMuted">Loading status...</div>;

  const ohlcvAge = data?.ohlcv_last_updated
    ? (Date.now() - new Date(data.ohlcv_last_updated).getTime()) / 1000 / 3600
    : 999
  const statusColor =
    ohlcvAge < 6  ? "green" :
    ohlcvAge < 24 ? "yellow" : "red"

  return (
    <div className="px-4 py-3 border-t border-[#2a2a2a]">
      <div className="flex items-center gap-2 mb-1">
        <div className={`w-2 h-2 rounded-full ${
          statusColor === "green" ? "bg-green-400 animate-pulse" :
          statusColor === "yellow" ? "bg-yellow-400" :
          "bg-red-400"
        }`}/>
        <span className={`text-xs font-mono font-bold ${
          statusColor === "green" ? "text-green-400" :
          statusColor === "yellow" ? "text-yellow-400" :
          "text-red-400"
        }`}>
          {statusColor === "green" ? "Data current" :
           statusColor === "yellow" ? "Syncing soon" :
           "Run scheduler"}
        </span>
      </div>
      <div className="text-xs text-[#64748b]">
        Last sync: {timeAgo(data.ohlcv_last_updated)}
      </div>
      <div className="text-xs text-[#64748b] mt-0.5">
        Predictions: {timeAgo(data.predictions_last_updated)}
      </div>
    </div>
  );
}

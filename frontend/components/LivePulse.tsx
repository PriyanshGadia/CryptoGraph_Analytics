"use client";

import { useEffect, useState } from "react";

export function LivePulse() {
  const [pulse, setPulse] = useState(false);
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");

  useEffect(() => {
    let ws: WebSocket | null = null;
    let pulseTimeout: NodeJS.Timeout;

    const connect = () => {
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const wsUrl = baseUrl.replace(/^http/, "ws") + "/api/stream/predictions";

      ws = new WebSocket(wsUrl);

      ws.onopen = () => setStatus("connected");

      ws.onmessage = () => {
        setPulse(true);
        clearTimeout(pulseTimeout);
        pulseTimeout = setTimeout(() => setPulse(false), 1000);
      };

      ws.onclose = () => {
        setStatus("disconnected");
        setTimeout(connect, 5000);
      };

      ws.onerror = (error) => {
        console.error("WebSocket error:", error);
        ws?.close();
      };
    };

    connect();

    return () => {
      if (ws) ws.close();
      clearTimeout(pulseTimeout);
    };
  }, []);

  return (
    <div className="flex items-center gap-3 px-3 py-1.5 glass-panel rounded-sm">
      <div className="flex items-center gap-1">
        {/* Node 1 */}
        <div className={`w-1.5 h-1.5 rounded-full transition-all duration-500 ${status === 'connected' ? 'bg-success shadow-[0_0_8px_rgba(34,197,94,0.8)]' : status === 'connecting' ? 'bg-warning animate-pulse' : 'bg-danger'}`} />
        
        {/* Synapse line */}
        <div className={`w-3 h-[1px] transition-all duration-500 ${pulse ? 'bg-accent-2 shadow-[0_0_5px_rgba(var(--accent-2),0.8)]' : 'bg-white/20'}`} />
        
        {/* Node 2 */}
        <div className={`w-2 h-2 rounded-full transition-all duration-300 ${pulse ? 'bg-accent-2 shadow-[0_0_10px_rgba(var(--accent-2),1)] scale-125' : 'bg-surface border border-white/20'}`} />
        
        {/* Synapse line */}
        <div className={`w-3 h-[1px] transition-all duration-700 ${pulse ? 'bg-accent-2 shadow-[0_0_5px_rgba(var(--accent-2),0.8)]' : 'bg-white/20'}`} />
        
        {/* Node 3 */}
        <div className={`w-1.5 h-1.5 rounded-full transition-all duration-1000 ${status === 'connected' ? 'bg-success/60' : status === 'connecting' ? 'bg-warning/60' : 'bg-danger/60'}`} />
      </div>
      <span className={`text-[9px] font-mono font-bold tracking-[0.2em] uppercase transition-colors duration-300 ${status === 'connected' ? 'text-success' : status === 'connecting' ? 'text-warning' : 'text-danger'}`}>
        {status === "connected" ? "Live Stream" : status === "connecting" ? "Syncing..." : "Offline"}
      </span>
    </div>
  );
}


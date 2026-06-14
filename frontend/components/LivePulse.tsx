"use client";

import { useEffect, useState } from "react";
import { Activity } from "lucide-react";

export function LivePulse() {
  const [pulse, setPulse] = useState(false);
  const [status, setStatus] = useState<"connecting" | "connected" | "disconnected">("connecting");

  useEffect(() => {
    let ws: WebSocket | null = null;
    let pulseTimeout: NodeJS.Timeout;

    const connect = () => {
      // Use the NEXT_PUBLIC_API_URL or fallback to localhost, but convert http:// to ws://
      const baseUrl = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
      const wsUrl = baseUrl.replace(/^http/, "ws") + "/api/stream/predictions";

      ws = new WebSocket(wsUrl);

      ws.onopen = () => {
        setStatus("connected");
      };

      ws.onmessage = (event) => {
        // We received a new set of predictions!
        setPulse(true);
        // Pulse the indicator for 1 second
        clearTimeout(pulseTimeout);
        pulseTimeout = setTimeout(() => {
          setPulse(false);
        }, 1000);
      };

      ws.onclose = () => {
        setStatus("disconnected");
        // Attempt to reconnect after 5 seconds
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
    <div className="mt-auto px-4 py-3">
      <div className="flex items-center gap-2">
        <div className="relative flex h-3 w-3">
          {status === "connected" && pulse && (
            <span className="animate-ping absolute inline-flex h-full w-full rounded-full bg-success opacity-75"></span>
          )}
          <span
            className={`relative inline-flex rounded-full h-3 w-3 ${
              status === "connected" ? "bg-success" : status === "connecting" ? "bg-warning animate-pulse" : "bg-danger"
            }`}
          ></span>
        </div>
        <span className="text-xs font-medium text-textMuted uppercase tracking-wider">
          {status === "connected" ? "Live Stream Active" : status === "connecting" ? "Connecting..." : "Stream Offline"}
        </span>
      </div>
    </div>
  );
}

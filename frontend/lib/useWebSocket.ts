"use client";

import { useEffect, useRef, useState, useCallback } from "react";
import { useAppStore } from "./store";

const BASE_URL = process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000";
const WS_BASE = BASE_URL.replace(/^http/, "ws");

interface WebSocketOptions {
  onMessage?: (data: any) => void;
  onOpen?: () => void;
  onClose?: () => void;
  onError?: (err: any) => void;
  shouldConnect?: boolean;
}

export function useWebSocket(endpointPath: string, options: WebSocketOptions = {}) {
  const { onMessage, onOpen, onClose, onError, shouldConnect = true } = options;
  const wsRef = useRef<WebSocket | null>(null);
  const reconnectCountRef = useRef(0);
  const reconnectTimerRef = useRef<NodeJS.Timeout | null>(null);
  const [localStatus, setLocalStatus] = useState<"connecting" | "connected" | "disconnected">("disconnected");
  
  // Connect Zustand status updater
  const updateStoreStatus = useAppStore((state) => state.updateWsStatus);

  const setStatus = useCallback((status: "connecting" | "connected" | "disconnected") => {
    setLocalStatus(status);
    updateStoreStatus(endpointPath, status);
  }, [endpointPath, updateStoreStatus]);

  const connect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }

    if (wsRef.current) {
      wsRef.current.close();
    }

    setStatus("connecting");

    // Construct url with credentials/key if needed
    const apiKey = process.env.NEXT_PUBLIC_API_KEY || "";
    const prefix = endpointPath.startsWith("/") ? "" : "/";
    const connector = endpointPath.includes("?") ? "&" : "?";
    const finalUrl = `${WS_BASE}${prefix}${endpointPath}${connector}api_key=${apiKey}`;

    const ws = new WebSocket(finalUrl);
    wsRef.current = ws;

    ws.onopen = () => {
      reconnectCountRef.current = 0; // reset backoff
      setStatus("connected");
      if (onOpen) onOpen();
    };

    ws.onmessage = (event) => {
      try {
        const parsed = JSON.parse(event.data);
        if (onMessage) {
          onMessage(parsed);
        }
      } catch (err) {
        console.error("WebSocket message parsing error:", err);
      }
    };

    ws.onclose = (event) => {
      setStatus("disconnected");
      if (onClose) onClose();

      // Only reconnect if not closed intentionally (wasn't garbage collected / unmounted)
      if (shouldConnect && wsRef.current === ws) {
        const backoffDelay = Math.min(1000 * Math.pow(2, reconnectCountRef.current), 30000);
        reconnectCountRef.current += 1;
        console.log(`WebSocket disconnected. Reconnecting in ${backoffDelay}ms (attempt ${reconnectCountRef.current})`);
        reconnectTimerRef.current = setTimeout(() => {
          connect();
        }, backoffDelay);
      }
    };

    ws.onerror = (err) => {
      if (onError) onError(err);
      ws.close();
    };
  }, [endpointPath, shouldConnect, setStatus, onOpen, onMessage, onClose, onError]);

  const disconnect = useCallback(() => {
    if (reconnectTimerRef.current) {
      clearTimeout(reconnectTimerRef.current);
      reconnectTimerRef.current = null;
    }
    if (wsRef.current) {
      const socket = wsRef.current;
      wsRef.current = null; // nullify ref first to avoid reconnect loops in onclose
      socket.close();
    }
    setStatus("disconnected");
  }, [setStatus]);

  const send = useCallback((msg: any) => {
    if (wsRef.current && wsRef.current.readyState === WebSocket.OPEN) {
      wsRef.current.send(typeof msg === "string" ? msg : JSON.stringify(msg));
    } else {
      console.warn("WebSocket is not connected. Message not sent.");
    }
  }, []);

  useEffect(() => {
    if (shouldConnect) {
      connect();
    } else {
      disconnect();
    }

    return () => {
      // Intentional cleanup on unmount
      if (reconnectTimerRef.current) {
        clearTimeout(reconnectTimerRef.current);
      }
      if (wsRef.current) {
        const socket = wsRef.current;
        wsRef.current = null; // nullify ref first to avoid reconnect loops in onclose
        socket.close();
      }
    };
  }, [shouldConnect, connect, disconnect]);

  return {
    status: localStatus,
    send,
    disconnect,
    reconnect: connect,
  };
}

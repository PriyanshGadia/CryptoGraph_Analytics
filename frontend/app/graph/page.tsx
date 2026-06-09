"use client";

import useSWR from "swr";
import { fetcher, GraphResponse } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import { RefreshCcw, ZoomIn } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useRef, useState, useEffect, useCallback } from "react";
import * as d3 from "d3-force";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => <Skeleton className="w-full h-[600px] rounded-xl" />,
});

const SECTOR_COLORS: Record<string, string> = {
  layer1: "#6366f1",
  defi: "#22c55e",
  exchange: "#f59e0b",
  payment: "#06b6d4",
  gaming: "#a855f7",
  privacy: "#ef4444",
  storage: "#f97316",
  other: "#64748b",
};

const SECTOR_LABELS: Record<string, string> = {
  layer1: "Layer 1", defi: "DeFi", exchange: "Exchange", payment: "Payment",
  gaming: "Gaming", privacy: "Privacy", storage: "Storage", other: "Other",
};

const EDGE_STYLES: Record<string, { color: string; opacity: number; widthMul: number }> = {
  correlation: { color: "#6366f1", opacity: 0.6, widthMul: 3 },
  sector:      { color: "#22c55e", opacity: 0.4, widthMul: 2 },
  market_cap:  { color: "#f59e0b", opacity: 0.4, widthMul: 2 },
};
const DEFAULT_EDGE = { color: "#94a3b8", opacity: 0.3, widthMul: 1 };

function getNodeRadius(marketCap: number | null | undefined): number {
  if (!marketCap) return 7;
  if (marketCap > 100_000_000_000) return 18;
  if (marketCap > 10_000_000_000) return 14;
  if (marketCap > 1_000_000_000) return 10;
  return 7;
}

function formatMarketCap(val: number | null | undefined): string {
  if (!val) return "N/A";
  if (val >= 1e12) return `$${(val / 1e12).toFixed(1)}T`;
  if (val >= 1e9) return `$${(val / 1e9).toFixed(1)}B`;
  if (val >= 1e6) return `$${(val / 1e6).toFixed(0)}M`;
  return `$${val.toLocaleString()}`;
}

function hexToRgb(hex: string): string {
  const r = parseInt(hex.slice(1, 3), 16);
  const g = parseInt(hex.slice(3, 5), 16);
  const b = parseInt(hex.slice(5, 7), 16);
  return `${r},${g},${b}`;
}

export default function GraphPage() {
  const { data, error, isLoading, mutate } = useSWR<GraphResponse>("/api/graph/latest", fetcher, {
    revalidateOnFocus: false, dedupingInterval: 30000,
  });

  const graphRef = useRef<any>(null);
  const hasZoomed = useRef(false);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: containerRef.current.clientHeight || 600,
        });
      }
    };
    update();
    window.addEventListener("resize", update);
    return () => window.removeEventListener("resize", update);
  }, [isLoading]);

  // Zoom to fit after graph settles
  useEffect(() => {
    if (graphRef.current && data) {
      setTimeout(() => graphRef.current?.zoomToFit(400, 40), 500);
    }
  }, [data]);

  useEffect(() => {
    if (graphRef.current) {
      graphRef.current.d3Force('link')?.strength((link: any) =>
        (link.weight || 0.5) * 0.8
      );
      graphRef.current.d3Force('charge')?.strength(-120);
      graphRef.current.d3Force('collision', 
        d3.forceCollide().radius((node: any) => getNodeRadius(node.market_cap_usd) + 2)
      );
    }
  }, [data]);

  const graphData = useMemo(() => {
    if (!data) return { nodes: [], links: [] };
    const nodes = data.nodes.map((n: any) => ({
      ...n,
      radius: getNodeRadius(n.market_cap_usd),
      color: SECTOR_COLORS[n.sector] || "#64748b",
    }));
    const nodeIds = new Set(nodes.map((n: any) => n.symbol));
    const links = data.edges
      .filter((e) => nodeIds.has(e.source) && nodeIds.has(e.target))
      .map((e) => ({ source: e.source, target: e.target, weight: e.weight, edge_type: e.edge_type }));
    return { nodes, links };
  }, [data]);

  const nodeCanvasObject = useCallback((node: any, ctx: CanvasRenderingContext2D) => {
    const r = node.radius || 7;
    const color = node.color || "#64748b";
    // Circle fill
    ctx.beginPath();
    ctx.arc(node.x, node.y, r, 0, 2 * Math.PI);
    ctx.fillStyle = color;
    ctx.fill();
    // White border
    ctx.strokeStyle = "rgba(255,255,255,0.8)";
    ctx.lineWidth = 1.5;
    ctx.stroke();
    // Label below
    ctx.font = "10px monospace";
    ctx.textAlign = "center";
    ctx.fillStyle = "#ffffff";
    ctx.fillText(node.symbol, node.x, node.y + r + 12);
  }, []);

  const linkColor = useCallback((link: any) => {
    const style = EDGE_STYLES[link.edge_type] || DEFAULT_EDGE;
    return `rgba(${hexToRgb(style.color)}, ${style.opacity})`;
  }, []);

  const linkWidth = useCallback((link: any) => {
    const style = EDGE_STYLES[link.edge_type] || DEFAULT_EDGE;
    return (link.weight || 0.5) * style.widthMul;
  }, []);

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full space-y-4">
        <div className="text-danger bg-danger/10 p-4 rounded-md border border-danger/20">
          Failed to load graph data
        </div>
        <button onClick={() => mutate()} className="flex items-center gap-2 px-4 py-2 bg-surface hover:bg-border transition-colors rounded-md text-text border border-border">
          <RefreshCcw size={16} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-full flex flex-col">
      <div className="mb-4">
        <h1 className="text-3xl font-bold text-text">Network Graph</h1>
        <p className="text-textMuted mt-1">Spatial-Temporal Graph — {graphData.nodes.length} assets, {graphData.links.length} connections</p>
      </div>

      <div ref={containerRef} className="flex-1 w-full bg-surface rounded-xl border border-border overflow-hidden relative" style={{ minHeight: "calc(100vh - 160px)" }}>
        {isLoading || !data ? (
          <Skeleton className="w-full h-full" />
        ) : (
          <ForceGraph2D
            ref={graphRef}
            width={dimensions.width}
            height={dimensions.height}
            graphData={graphData}
            nodeId="symbol"
            nodeCanvasObject={nodeCanvasObject}
            nodePointerAreaPaint={(node: any, color: string, ctx: CanvasRenderingContext2D) => {
              ctx.beginPath();
              ctx.arc(node.x, node.y, node.radius || 7, 0, 2 * Math.PI);
              ctx.fillStyle = color;
              ctx.fill();
            }}
            linkColor={linkColor}
            linkWidth={linkWidth}
            backgroundColor="#0f0f0f"
            d3AlphaDecay={0.02}
            d3VelocityDecay={0.3}
            cooldownTime={8000}
            onEngineStop={() => {
              if (graphRef.current && !hasZoomed.current) {
                graphRef.current.zoomToFit(400, 40);
                hasZoomed.current = true;
              }
            }}
            onNodeClick={(node: any) => setSelectedNode(node)}
          />
        )}

        {/* Controls panel */}
        <div className="absolute top-4 right-4 bg-[#1a1a1a] p-4 rounded-lg border border-border space-y-3 z-10">
          <div className="text-xs font-mono font-bold text-textMuted uppercase tracking-wider">Controls</div>
          <button onClick={() => graphRef.current?.zoomToFit(400, 40)} className="w-full flex items-center gap-2 px-3 py-2 bg-accent/10 hover:bg-accent/20 text-accent rounded text-xs font-bold transition-colors">
            <ZoomIn size={14} /> Zoom to Fit
          </button>
          <button onClick={() => mutate()} className="w-full flex items-center gap-2 px-3 py-2 bg-surface hover:bg-border text-text rounded text-xs transition-colors">
            <RefreshCcw size={14} /> Reload
          </button>
          <div className="flex gap-2 text-xs">
            <span className="px-2 py-1 bg-accent/10 text-accent rounded font-mono">{graphData.nodes.length} Assets</span>
            <span className="px-2 py-1 bg-surface text-textMuted rounded font-mono">{graphData.links.length} Edges</span>
          </div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 left-4 bg-black/80 p-3 rounded-lg border border-border backdrop-blur-sm z-10">
          <div className="text-xs font-mono font-bold text-textMuted mb-2 uppercase tracking-wider">Sectors</div>
          {Object.entries(SECTOR_LABELS).map(([key, label]) => (
            <div key={key} className="flex items-center gap-2 mb-1 text-xs text-text">
              <div className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: SECTOR_COLORS[key] }} /> {label}
            </div>
          ))}
          <div className="border-t border-border my-2" />
          <div className="text-xs font-mono font-bold text-textMuted mb-2 uppercase tracking-wider">Edges</div>
          {Object.entries({ correlation: "Correlation", sector: "Sector", market_cap: "Market Cap" }).map(([key, label]) => (
            <div key={key} className="flex items-center gap-2 mb-1 text-xs text-text">
              <div className="w-4 h-0.5 rounded" style={{ backgroundColor: EDGE_STYLES[key]?.color }} /> {label}
            </div>
          ))}
        </div>

        {/* Selected node panel */}
        {selectedNode && (
          <div className="absolute top-4 left-4 w-64 bg-[#1a1a1a] p-4 rounded-lg border border-border z-20 space-y-3">
            <div className="flex justify-between items-start">
              <div className="font-mono text-2xl font-bold text-text">{selectedNode.symbol}</div>
              <button onClick={() => setSelectedNode(null)} className="text-textMuted hover:text-text text-xs">✕</button>
            </div>
            <span className="inline-block px-2 py-1 rounded-full text-xs font-bold" style={{ backgroundColor: selectedNode.color + "20", color: selectedNode.color }}>
              {selectedNode.sector || "other"}
            </span>
            <div className="text-sm text-textMuted">
              Market Cap: <span className="text-text font-mono">{formatMarketCap(selectedNode.market_cap_usd)}</span>
            </div>
            {selectedNode.predicted_direction && (
              <div className="text-sm text-textMuted">
                Prediction: <span className={`font-bold ${selectedNode.predicted_direction?.includes("up") ? "text-success" : selectedNode.predicted_direction?.includes("down") ? "text-danger" : "text-textMuted"}`}>
                  {selectedNode.predicted_direction}
                </span>
              </div>
            )}
            {selectedNode.confidence != null && (
              <div className="text-sm text-textMuted">
                Confidence: <span className="text-accent font-mono">{(selectedNode.confidence * 100).toFixed(1)}%</span>
              </div>
            )}
          </div>
        )}
      </div>
    </div>
  );
}

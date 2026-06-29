"use client";

import useSWR from "swr";
import { fetcher, GraphResponse } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import { RefreshCcw, ZoomIn, Activity } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useRef, useState, useEffect, useCallback } from "react";
import { useChartPalette } from "@/lib/useChartPalette";
import * as d3 from "d3-force";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => <Skeleton className="w-full h-[600px] shape-squircle" />,
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
  const palette = useChartPalette();
  
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

  useEffect(() => {
    let observer: IntersectionObserver;
    if (containerRef.current) {
      observer = new IntersectionObserver(
        ([entry]) => {
          if (!document.hidden) {
            if (entry.isIntersecting) {
              graphRef.current?.resumeAnimation();
            } else {
              graphRef.current?.pauseAnimation();
            }
          }
        },
        { threshold: 0.1 }
      );
      observer.observe(containerRef.current);
    }
    
    const handleVisibilityChange = () => {
      if (document.hidden) {
        graphRef.current?.pauseAnimation();
      } else {
        // Only resume if visible in viewport
        if (containerRef.current) {
          const rect = containerRef.current.getBoundingClientRect();
          const isVisible = (
            rect.top < (window.innerHeight || document.documentElement.clientHeight) &&
            rect.bottom > 0
          );
          if (isVisible) graphRef.current?.resumeAnimation();
        }
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (observer) observer.disconnect();
    };
  }, []);

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
        <div className="text-danger bg-danger/10 p-4 rounded-sm border border-danger/20">
          Failed to load graph data
        </div>
        <button onClick={() => mutate()} className="flex items-center gap-2 px-6 py-3 glass hover:bg-white/10 transition-colors rounded-sm text-text border border-white/10">
          <RefreshCcw size={16} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="h-[calc(100vh-8rem)] flex flex-col relative w-full pt-8 p-6 glass-2 shape-seal overflow-hidden">
      <div className="mb-6 relative z-10 px-4 max-w-6xl mx-auto w-full">
        <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight font-sans">Topological Graph</h1>
        <p className="text-text-muted font-light tracking-wide mt-2">Spatial-Temporal Graph — {graphData.nodes.length} assets, {graphData.links.length} connections</p>
      </div>

      <div ref={containerRef} className="flex-1 w-full relative glass-flat shape-squircle overflow-hidden">
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
            backgroundColor="transparent"
            d3AlphaDecay={0.06}
            d3VelocityDecay={0.4}
            cooldownTime={4000}
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
        <div className="absolute top-4 right-4 glass-3 shape-facet-sm p-5 border border-white/5 space-y-4 z-10 w-64 shadow-2xl backdrop-blur-2xl">
          <div className="text-[10px] font-mono font-bold text-accent uppercase tracking-widest flex items-center gap-2">
            <Activity size={14} /> Network Controls
          </div>
          <button onClick={() => graphRef.current?.zoomToFit(400, 40)} className="w-full flex justify-center items-center gap-2 px-4 py-2.5 glass bg-accent/10 hover:bg-accent/20 text-accent rounded-sm text-xs font-bold transition-all border border-accent/20 shadow-[0_0_15px_rgba(var(--accent),0.1)]">
            <ZoomIn size={14} /> Center Graph
          </button>
          <button onClick={() => mutate()} className="w-full flex justify-center items-center gap-2 px-4 py-2.5 glass bg-surface/50 hover:bg-white/10 text-text rounded-sm text-xs transition-colors border border-white/5">
            <RefreshCcw size={14} /> Refresh Data
          </button>
          <div className="flex gap-2 text-[10px] uppercase tracking-widest font-mono pt-2 border-t border-white/10">
            <span className="flex-1 text-center py-1.5 bg-success/10 text-success rounded-sm border border-success/20">{graphData.nodes.length} Nodes</span>
            <span className="flex-1 text-center py-1.5 bg-warning/10 text-warning rounded-sm border border-warning/20">{graphData.links.length} Edges</span>
          </div>
        </div>

        {/* Legend */}
        <div className="absolute bottom-4 left-4 glass-3 shape-facet-sm p-5 border border-white/5 shadow-2xl backdrop-blur-2xl z-10">
          <div className="text-[10px] font-mono font-bold text-accent mb-3 uppercase tracking-widest">Sectors</div>
          <div className="grid grid-cols-2 gap-x-6 gap-y-2">
              {Object.entries(SECTOR_LABELS).map(([key, label]) => (
                <div key={key} className="flex items-center gap-2 text-xs text-text/80 font-medium">
                  <div className="w-2 h-2 rounded-full shadow-[0_0_8px_currentColor]" style={{ backgroundColor: SECTOR_COLORS[key], color: SECTOR_COLORS[key] }} /> {label}
                </div>
              ))}
          </div>
          <div className="border-t border-white/10 my-4" />
          <div className="text-[10px] font-mono font-bold text-accent mb-3 uppercase tracking-widest">Connection Types</div>
          <div className="space-y-2.5">
              {Object.entries({ correlation: "Price Correlation", sector: "Sector Relation", market_cap: "Size Equivalence" }).map(([key, label]) => (
                <div key={key} className="flex items-center gap-3 text-xs text-text/80 font-medium">
                  <div className="w-6 h-0.5 rounded shadow-[0_0_8px_currentColor]" style={{ backgroundColor: EDGE_STYLES[key]?.color, color: EDGE_STYLES[key]?.color }} /> {label}
                </div>
              ))}
          </div>
        </div>

        {/* Selected node panel */}
        {selectedNode && (
          <div className="absolute top-4 left-4 w-72 glass-3 shape-facet-sm p-6 border border-white/10 z-20 space-y-4 shadow-2xl backdrop-blur-2xl animate-in fade-in slide-in-from-left-4">
            <div className="flex justify-between items-start">
              <div className="font-sans text-3xl font-black text-text tracking-tight">{selectedNode.symbol}</div>
              <button onClick={() => setSelectedNode(null)} className="text-text-muted hover:text-text text-sm transition-colors w-6 h-6 flex items-center justify-center rounded-full hover:bg-white/10">✕</button>
            </div>
            
            <div className="inline-flex px-3 py-1 rounded-sm text-[10px] font-bold uppercase tracking-widest border" style={{ backgroundColor: selectedNode.color + "15", color: selectedNode.color, borderColor: selectedNode.color + "30" }}>
              {selectedNode.sector || "other"}
            </div>
            
            <div className="space-y-3 pt-2">
                <div className="flex flex-col gap-0.5">
                  <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono">Market Cap</span>
                  <span className="text-lg font-mono font-bold text-text">{formatMarketCap(selectedNode.market_cap_usd)}</span>
                </div>
                
                {selectedNode.predicted_direction && (
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono">AI Signal</span>
                    <span className={`text-sm font-bold uppercase tracking-widest ${selectedNode.predicted_direction?.includes("up") ? "text-success" : selectedNode.predicted_direction?.includes("down") ? "text-danger" : "text-text-muted"}`}>
                      {selectedNode.predicted_direction.replace('_', ' ')}
                    </span>
                  </div>
                )}
                
                {selectedNode.confidence != null && (
                  <div className="flex flex-col gap-0.5">
                    <span className="text-[10px] text-text-muted uppercase tracking-widest font-mono">Confidence Matrix</span>
                    <span className="text-xl font-mono font-black text-text">{(selectedNode.confidence * 100).toFixed(1)}%</span>
                  </div>
                )}
            </div>
          </div>
        )}
      </div>
    </div>
  );
}


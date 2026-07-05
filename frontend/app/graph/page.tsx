"use client";
import useSWR from "swr";
import { fetcher, GraphResponse } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import { RefreshCcw, ZoomIn, Activity } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useRef, useState, useEffect, useCallback } from "react";
import { useChartPalette } from "@/lib/useChartPalette";
import { useTheme } from "next-themes";
import * as d3 from "d3-force";
import * as THREE from "three";
import { useRouter } from "next/navigation";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d"), {
  ssr: false,
  loading: () => <Skeleton className="w-full h-[600px] shape-squircle" />,
});

const ForceGraph3D = dynamic(() => import("react-force-graph-3d"), {
  ssr: false,
  loading: () => <Skeleton className="w-full h-[600px] shape-squircle" />,
});

const SECTOR_COLORS: Record<string, string> = {
  "Layer 1": "#6366f1",
  "Layer 2": "#3b82f6",
  "DeFi": "#22c55e",
  "Infrastructure": "#f59e0b",
  "Gaming": "#a855f7",
  "Meme": "#ec4899",
  "Other": "#64748b",
};

const SECTOR_LABELS: Record<string, string> = {
  "Layer 1": "Layer 1",
  "Layer 2": "Layer 2",
  "DeFi": "DeFi",
  "Infrastructure": "Infrastructure",
  "Gaming": "Gaming",
  "Meme": "Meme",
  "Other": "Other",
};

const EDGE_STYLES: Record<string, { color: string; opacity: number; widthMul: number }> = {
  positive_correlation: { color: "#39ff14", opacity: 0.95, widthMul: 6 }, // Neon green
  negative_correlation: { color: "#ff073a", opacity: 0.95, widthMul: 6 }, // Neon red
};

const DEFAULT_EDGE = { color: "#d4a547", opacity: 0.8, widthMul: 4 };

function interpolateColor(color1: string, color2: string, t: number): string {
  const hex = (x: string) => {
    const val = x.replace("#", "");
    if (val.length === 3) {
      return [parseInt(val[0] + val[0], 16), parseInt(val[1] + val[1], 16), parseInt(val[2] + val[2], 16)];
    }
    return [parseInt(val.slice(0, 2), 16), parseInt(val.slice(2, 4), 16), parseInt(val.slice(4, 6), 16)];
  };
  try {
    const c1 = hex(color1);
    const c2 = hex(color2);
    const r = Math.round(c1[0] * (1 - t) + c2[0] * t);
    const g = Math.round(c1[1] * (1 - t) + c2[1] * t);
    const b = Math.round(c1[2] * (1 - t) + c2[2] * t);
    return `rgb(${r},${g},${b})`;
  } catch (e) {
    return color1;
  }
}

// Resolves a node's signal color from the current theme's CHART_HEX palette (instead of
// ad hoc hex literals) so graph node colors correctly re-theme between day/night.
function getSignalColor(dir: string | null | undefined, pal: { success: string; danger: string; warning: string; muted: string }): string {
  const d = dir?.toLowerCase() || "";
  if (d.includes("up")) return pal.success;
  if (d.includes("down")) return pal.danger;
  if (d.includes("recalibrating")) return pal.warning;
  return pal.muted;
}

function getNodeRadius(marketCap: number | null | undefined): number {
  if (!marketCap) return 3.5;
  if (marketCap > 100_000_000_000) return 6.0;
  if (marketCap > 10_000_000_000) return 5.0;
  if (marketCap > 1_000_000_000) return 4.2;
  return 3.5;
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
  const { resolvedTheme } = useTheme();
  const router = useRouter();
  
  const [sliderVal, setSliderVal] = useState<number>(2.0); // Smooth continuous float [0.0 - 4.0]
  const [is3D, setIs3D] = useState(true);
  const [mounted, setMounted] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0); // State trigger for 2D image-load repaints & timeline updates
  const failedIcons = useRef<Set<string>>(new Set()); // Cache icon 404s to prevent repeated loads
  const sliderInitialized = useRef(false); // Track whether initial zoom has occurred

  useEffect(() => {
    setMounted(true);
  }, []);
  
  const { data: histData } = useSWR<GraphResponse>("/api/graph/latest?mode=historical", fetcher, { revalidateOnFocus: false, dedupingInterval: 60000 });
  const { data: hist30Data } = useSWR<GraphResponse>("/api/graph/latest?mode=historical_30", fetcher, { revalidateOnFocus: false, dedupingInterval: 60000 });
  const { data: liveData, error, isLoading, mutate } = useSWR<GraphResponse>("/api/graph/latest?mode=live", fetcher, { revalidateOnFocus: false, dedupingInterval: 60000 });
  const { data: proj15Data } = useSWR<GraphResponse>("/api/graph/latest?mode=projected_15", fetcher, { revalidateOnFocus: false, dedupingInterval: 60000 });
  const { data: proj30Data } = useSWR<GraphResponse>("/api/graph/latest?mode=projected", fetcher, { revalidateOnFocus: false, dedupingInterval: 60000 });

  const graphRef = useRef<any>(null);
  const graphRef2D = useRef<any>(null);
  const hasZoomed = useRef(false);
  const [selectedNode, setSelectedNode] = useState<any>(null);
  const [dimensions, setDimensions] = useState({ width: 800, height: 600 });
  const containerRef = useRef<HTMLDivElement>(null);

  // Smooth slider transition state (keeps node/link reference identical, updates in-place)
  const [graphDataState, setGraphDataState] = useState<{ nodes: any[], links: any[] }>({ nodes: [], links: [] });
  const [minCorrelationThreshold, setMinCorrelationThreshold] = useState<number>(0.25);
  const graphInitialized = useRef(false);

  const displayGraphData = useMemo(() => {
    // ALWAYS sanitize link source and target to plain symbol string IDs so d3-force can correctly map nodes
    const rawLinks = graphDataState.links.map((l: any) => ({
      ...l,
      source: typeof l.source === "object" ? (l.source.symbol || l.source.id) : l.source,
      target: typeof l.target === "object" ? (l.target.symbol || l.target.id) : l.target,
    }));

    const filtered = minCorrelationThreshold <= 0 
      ? rawLinks 
      : rawLinks.filter((l: any) => Math.abs(l.weight || 0) >= minCorrelationThreshold);

    return {
      nodes: graphDataState.nodes,
      links: filtered
    };
  }, [graphDataState, minCorrelationThreshold, refreshTrigger]);

  // Persistent cache for ThreeJS objects to prevent violent recreations
  const nodeThreeObjsMap = useRef<Map<string, THREE.Group>>(new Map());

  const handleToggle3D = useCallback(() => {
    // Sanitize link object source/target references back to raw symbol strings
    // to prevent 2D/3D d3 simulation object reference collisions
    setGraphDataState(prev => ({
      nodes: prev.nodes,
      links: prev.links.map((l: any) => ({
        ...l,
        source: typeof l.source === "object" ? l.source.symbol || l.source.id : l.source,
        target: typeof l.target === "object" ? l.target.symbol || l.target.id : l.target,
      }))
    }));
    nodeThreeObjsMap.current.clear();
    setIs3D(prev => !prev);
  }, []);

  useEffect(() => {
    const update = () => {
      if (containerRef.current) {
        setDimensions({
          width: containerRef.current.clientWidth,
          height: Math.max(550, containerRef.current.clientHeight || 650),
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
              graphRef.current?.resumeAnimation?.();
              graphRef2D.current?.resumeAnimation?.();
            } else {
              graphRef.current?.pauseAnimation?.();
              graphRef2D.current?.pauseAnimation?.();
            }
          }
        },
        { threshold: 0.1 }
      );
      observer.observe(containerRef.current);
    }
    
    const handleVisibilityChange = () => {
      if (document.hidden) {
        graphRef.current?.pauseAnimation?.();
        graphRef2D.current?.pauseAnimation?.();
      } else {
        if (containerRef.current) {
          const rect = containerRef.current.getBoundingClientRect();
          const isVisible = (
            rect.top < (window.innerHeight || document.documentElement.clientHeight) &&
            rect.bottom > 0
          );
          if (isVisible) {
            graphRef.current?.resumeAnimation?.();
            graphRef2D.current?.resumeAnimation?.();
          }
        }
      }
    };
    document.addEventListener("visibilitychange", handleVisibilityChange);
    return () => {
      document.removeEventListener("visibilitychange", handleVisibilityChange);
      if (observer) observer.disconnect();
    };
  }, []);

  // Initialize the topology reference once when base liveData is ready
  useEffect(() => {
    if (liveData && !graphInitialized.current) {
      const nodes = liveData.nodes.map((n: any) => ({
        ...n,
        radius: getNodeRadius(n.market_cap_usd),
        color: getSignalColor(n.predicted_direction, palette),
      }));

      const nodeIds = new Set(nodes.map((n: any) => n.symbol));
      const links = liveData.edges
        .filter((e: any) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e: any) => ({
          source: e.source,
          target: e.target,
          weight: e.weight,
          edge_type: e.edge_type,
          motif_similarity: e.motif_similarity,
        }));

      setGraphDataState({ nodes, links });
      graphInitialized.current = true;
    }
  }, [liveData, palette]);

  // Smoothly update attributes in-place when slider changes to prevent graph reload/force reset
  useEffect(() => {
    if (graphDataState.nodes.length === 0) return;

    const stepLower = Math.min(4, Math.max(0, Math.floor(sliderVal)));
    const stepUpper = Math.min(4, Math.max(0, Math.ceil(sliderVal)));
    const t = sliderVal - stepLower;

    const list = [histData, hist30Data, liveData, proj15Data, proj30Data];
    const dataLower = list[stepLower] || liveData;
    const dataUpper = list[stepUpper] || liveData;

    if (!dataLower || !dataUpper) return;

    const nodeMapLower = new Map(dataLower.nodes.map((n: any) => [n.symbol, n]));
    const nodeMapUpper = new Map(dataUpper.nodes.map((n: any) => [n.symbol, n]));

    graphDataState.nodes.forEach((n: any) => {
      const nLower = nodeMapLower.get(n.symbol);
      const nUpper = nodeMapUpper.get(n.symbol);
      const targetDirLower = nLower?.predicted_direction || "neutral";
      const targetDirUpper = nUpper?.predicted_direction || "neutral";

      const colLower = getSignalColor(targetDirLower, palette);
      const colUpper = getSignalColor(targetDirUpper, palette);
      n.color = interpolateColor(colLower, colUpper, t);

      const radLower = getNodeRadius(nLower?.market_cap_usd || 1e9);
      const radUpper = getNodeRadius(nUpper?.market_cap_usd || 1e9);
      n.radius = Math.max(4, radLower * (1 - t) + radUpper * t);
      n.predicted_direction = t < 0.5 ? targetDirLower : targetDirUpper;

      // Update ThreeJS meshes in-place for instant, buttery smooth slider transitions
      const group = nodeThreeObjsMap.current.get(n.symbol);
      if (group) {
        const sphereMesh = group.children[0] as THREE.Mesh;
        if (sphereMesh && sphereMesh.material) {
          (sphereMesh.material as THREE.MeshBasicMaterial).color.set(n.color || palette.muted);
          sphereMesh.scale.setScalar(n.radius / 6);
        }
        const logoSprite = group.children[1] as THREE.Sprite;
        if (logoSprite) {
          logoSprite.scale.setScalar(14 * (n.radius / 6));
        }
        const textSprite = group.children[2] as THREE.Sprite;
        if (textSprite) {
          textSprite.scale.setScalar(18 * (n.radius / 6));
          textSprite.position.y = n.radius + 5;
        }
      }
    });

    const edgeMapLower = new Map(dataLower.edges.map((e: any) => [`${e.source}-${e.target}`, e]));
    const edgeMapUpper = new Map(dataUpper.edges.map((e: any) => [`${e.source}-${e.target}`, e]));

    graphDataState.links.forEach((l: any) => {
      const srcId = typeof l.source === "object" ? l.source.symbol || l.source.id : l.source;
      const tgtId = typeof l.target === "object" ? l.target.symbol || l.target.id : l.target;
      const key = `${srcId}-${tgtId}`;
      const revKey = `${tgtId}-${srcId}`;

      const eLower = edgeMapLower.get(key) || edgeMapLower.get(revKey);
      const eUpper = edgeMapUpper.get(key) || edgeMapUpper.get(revKey);

      const wLower = eLower ? eLower.weight : 0.0;
      const wUpper = eUpper ? eUpper.weight : 0.0;
      l.weight = wLower * (1 - t) + wUpper * t;

      // Interpolate edge_type: use the sign of the interpolated weight
      l.edge_type = l.weight >= 0 ? "positive_correlation" : "negative_correlation";

      const motifLower = eLower ? eLower.motif_similarity : 0.0;
      const motifUpper = eUpper ? eUpper.motif_similarity : 0.0;
      l.motif_similarity = motifLower * (1 - t) + motifUpper * t;
    });

    setRefreshTrigger(prev => prev + 1);
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [sliderVal, histData, hist30Data, liveData, proj15Data, proj30Data, palette]);

  const applyForces = useCallback((graphInstance: any) => {
    if (!graphInstance) return;
    try {
      const linkForce = graphInstance.d3Force?.('link');
      if (linkForce) {
        linkForce
          .strength((link: any) => (Math.abs(link.weight) || 0.5) * 0.9)
          .distance(450); // Generous link distance for un-cramped spacing
      }
      const chargeForce = graphInstance.d3Force?.('charge');
      if (chargeForce) {
        chargeForce.strength(-7000); // Strong repulsion spacing
      }
      const collideForce = graphInstance.d3Force?.('collision');
      if (collideForce) {
        collideForce.radius((node: any) => (node.radius || 6) * 3.5 + 32);
      } else if (d3.forceCollide) {
        graphInstance.d3Force?.('collision', d3.forceCollide().radius((node: any) => (node.radius || 6) * 3.5 + 32));
      }
      graphInstance.d3ReheatSimulation?.();
    } catch (err) {
      console.warn("Could not apply forces:", err);
    }
  }, []);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (is3D && graphRef.current) {
        applyForces(graphRef.current);
      } else if (!is3D && graphRef2D.current) {
        applyForces(graphRef2D.current);
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [is3D, isLoading, minCorrelationThreshold, applyForces]);

  // Handle perfect centering on initial load and 2D/3D toggle only — NOT on slider changes
  useEffect(() => {
    if (graphDataState.nodes.length > 0) {
      const timer = setTimeout(() => {
        graphRef.current?.zoomToFit?.(800, 120);
        graphRef2D.current?.zoomToFit?.(800, 120);
      }, 600);
      return () => clearTimeout(timer);
    }
    // eslint-disable-next-line react-hooks/exhaustive-deps
  }, [is3D, graphDataState.nodes.length]);

  // Adjust forces: massive repulsion and link spacing to spread out node connections cleanly
  useEffect(() => {
    if (is3D && graphRef.current) {
      applyForces(graphRef.current);
    } else if (!is3D && graphRef2D.current) {
      applyForces(graphRef2D.current);
    }
  }, [graphDataState, is3D, applyForces]);

  const nodeThreeObject = useCallback((node: any) => {
    const radius = node.radius || 4;

    // Use cached ThreeJS group representation if present to avoid violent rebuilds
    const cachedGroup = nodeThreeObjsMap.current.get(node.symbol);
    if (cachedGroup) {
      const sphereMesh = cachedGroup.children[0] as THREE.Mesh;
      if (sphereMesh && sphereMesh.material) {
        (sphereMesh.material as THREE.MeshBasicMaterial).color.set(node.color || palette.muted);
        sphereMesh.scale.setScalar(radius / 4);
      }
      const logoSprite = cachedGroup.children[1] as THREE.Sprite;
      if (logoSprite) {
        logoSprite.scale.setScalar(9 * (radius / 4));
      }
      const textSprite = cachedGroup.children[2] as THREE.Sprite;
      if (textSprite) {
        textSprite.scale.setScalar(12 * (radius / 4));
        textSprite.position.y = radius + 3;
      }
      return cachedGroup;
    }

    // 1. Transparent ambient sphere orb (depthWrite: false so logo sprite is never obscured)
    const sphereGeom = new THREE.SphereGeometry(4, 20, 20);
    const sphereMat = new THREE.MeshBasicMaterial({
      color: node.color || palette.muted,
      transparent: true,
      opacity: 0.22,
      depthWrite: false
    });
    const sphereMesh = new THREE.Mesh(sphereGeom, sphereMat);
    sphereMesh.scale.setScalar(radius / 4);

    const iconUrl = `https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530be6e374711a8554f31b17e4cb92c25fa5/svg/color/${node.symbol.toLowerCase()}.svg`;
    const isKnownFailed = failedIcons.current.has(node.symbol);

    // Create canvas texture immediately with fallback orb to avoid empty nodes
    const canvas = document.createElement("canvas");
    canvas.width = 64;
    canvas.height = 64;
    const ctx = canvas.getContext("2d");
    if (ctx) {
      ctx.clearRect(0, 0, 64, 64);
      ctx.beginPath();
      ctx.arc(32, 32, 26, 0, 2 * Math.PI);
      const grad = ctx.createRadialGradient(32, 32, 0, 32, 32, 26);
      grad.addColorStop(0, node.color || palette.muted);
      grad.addColorStop(1, 'rgba(15, 23, 42, 0.95)');
      ctx.fillStyle = grad;
      ctx.fill();
      ctx.strokeStyle = node.color || palette.muted;
      ctx.lineWidth = 2.0;
      ctx.stroke();
      ctx.font = 'bold 16px sans-serif';
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(node.symbol.length <= 4 ? node.symbol : node.symbol.slice(0, 3), 32, 32);
    }
    const logoTex = new THREE.CanvasTexture(canvas);

    if (!isKnownFailed) {
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.src = iconUrl;
      img.onload = () => {
        (logoTex as any).image = img;
        logoTex.needsUpdate = true;
        graphRef.current?.refresh?.();
      };
      img.onerror = () => {
        failedIcons.current.add(node.symbol);
      };
    }

    // depthTest: false and renderOrder: 999 guarantees coin icon is always rendered on top of sphere!
    const logoMat = new THREE.SpriteMaterial({ 
      map: logoTex, 
      transparent: true,
      depthTest: false,
      depthWrite: false
    });
    const logoSprite = new THREE.Sprite(logoMat);
    logoSprite.renderOrder = 999;
    logoSprite.scale.setScalar(9 * (radius / 4));

    const textCanvas = document.createElement('canvas');
    textCanvas.width = 128;
    textCanvas.height = 128;
    const tCtx = textCanvas.getContext('2d');
    if (tCtx) {
      tCtx.clearRect(0, 0, 128, 128);
      tCtx.fillStyle = 'rgba(15, 23, 42, 0.9)';
      tCtx.beginPath();
      tCtx.roundRect(10, 36, 108, 56, 8);
      tCtx.fill();
      tCtx.strokeStyle = 'rgba(255, 255, 255, 0.25)';
      tCtx.lineWidth = 2;
      tCtx.stroke();

      tCtx.font = 'bold 32px monospace';
      tCtx.fillStyle = '#ffffff';
      tCtx.textAlign = 'center';
      tCtx.textBaseline = 'middle';
      tCtx.fillText(node.symbol, 64, 64);
    }
    const textTex = new THREE.CanvasTexture(textCanvas);
    const spriteMat = new THREE.SpriteMaterial({ 
      map: textTex, 
      transparent: true,
      depthTest: false,
      depthWrite: false 
    });
    const textSprite = new THREE.Sprite(spriteMat);
    textSprite.renderOrder = 1000;
    textSprite.scale.setScalar(12 * (radius / 4));
    textSprite.position.y = radius + 3;

    const group = new THREE.Group();
    group.add(sphereMesh);
    group.add(logoSprite);
    group.add(textSprite);
    
    nodeThreeObjsMap.current.set(node.symbol, group);
    return group;
  }, [palette]);

  const linkColor = useCallback((link: any) => {
    const w = link.weight ?? 0;
    const absWeight = Math.abs(w);
    // Pure electric neon red (#ff0033) for negative, high-luminance neon green (#00ff66) for positive
    const color = w >= 0 ? "#00ff66" : "#ff0033";
    // Negative connections get ultra-high baseline opacity (0.90 - 1.0) so red connections pop violently
    const opacity = w < 0 ? Math.min(1.0, Math.max(0.90, absWeight * 3.0)) : Math.min(1.0, Math.max(0.60, absWeight * 2.0));
    return `rgba(${hexToRgb(color)}, ${opacity})`;
  }, []);

  const linkWidth = useCallback((link: any) => {
    const w = link.weight ?? 0;
    const absWeight = Math.abs(w);
    // Negative links get bold thick lines (1.8 + absWeight * 4.0) so red connections are ultra-prominent
    return w < 0 ? 1.8 + absWeight * 4.0 : 0.8 + absWeight * 2.2;
  }, []);

  if (!mounted) {
    return null;
  }

  if (error) {
    return (
      <div className="flex flex-col items-center justify-center h-full space-y-4">
        <div className="text-danger bg-danger/10 p-4 rounded-sm border border-danger/20">
          Failed to load graph data
        </div>
        <button onClick={() => mutate()} className="flex items-center gap-2 px-6 py-3 glass hover:bg-text/5 transition-colors rounded-sm text-text border border-text/10">
          <RefreshCcw size={16} /> Retry
        </button>
      </div>
    );
  }

  return (
    <div className="relative min-h-[calc(100vh-8rem)] flex flex-col gap-6 w-full max-w-[1600px] mx-auto p-4 md:p-6">
      
      {/* Header controls */}
      <div className="flex flex-col md:flex-row md:items-center justify-between gap-6 relative z-10 w-full">
        <div>
          <h1 className="text-4xl font-black text-transparent bg-clip-text bg-gradient-to-r from-text via-text/80 to-text-muted tracking-tight">Correlation Network</h1>
          <p className="text-text-muted font-light tracking-wide mt-2">Spatial-Temporal Graph — {graphDataState.nodes.length} assets, {graphDataState.links.length} connections</p>
        </div>

        <div className="flex flex-wrap items-center gap-4 bg-surface/30 p-2 rounded-lg border border-text/10 backdrop-blur-md">
          {/* Min correlation edge threshold filter */}
          <div className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono rounded border border-text/10 bg-text/5 text-text">
            <span className="text-text-muted font-bold">Min |r|:</span>
            <select
              value={minCorrelationThreshold}
              onChange={(e) => setMinCorrelationThreshold(parseFloat(e.target.value))}
              className="bg-transparent text-accent font-bold focus:outline-none cursor-pointer"
            >
              <option value={0.0} className="bg-background text-text">All Links (100)</option>
              <option value={0.25} className="bg-background text-text">≥ 0.25 (Filtered)</option>
              <option value={0.35} className="bg-background text-text">≥ 0.35 (Strong)</option>
              <option value={0.45} className="bg-background text-text">≥ 0.45 (Clusters)</option>
              <option value={0.60} className="bg-background text-text">≥ 0.60 (High Conviction)</option>
            </select>
          </div>

          {/* 2D/3D switcher */}
          <button 
            onClick={handleToggle3D} 
            className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-bold uppercase tracking-wider rounded border border-text/10 bg-text/5 hover:bg-text/15 text-text transition-all"
          >
            <Activity size={14} className="text-accent" />
            Switch to {is3D ? "2D Graph" : "3D Graph"}
          </button>
          
          <button onClick={() => {
            if (is3D) graphRef.current?.zoomToFit(400, 40);
            else graphRef2D.current?.zoomToFit(400, 40);
          }} className="flex items-center gap-2 px-4 py-2 text-xs font-mono font-bold uppercase tracking-wider rounded border border-text/10 bg-text/5 hover:bg-text/15 text-text transition-all">
            <ZoomIn size={14} /> Center Graph
          </button>
        </div>
      </div>

      <div ref={containerRef} className="flex-1 w-full relative glass-flat rounded-xl bg-background overflow-hidden min-h-[720px]">
        {isLoading || !liveData ? (
          <Skeleton className="w-full h-full" />
        ) : is3D ? (
          <ForceGraph3D
            key={resolvedTheme || 'dark'}
            ref={graphRef}
            width={dimensions.width}
            height={dimensions.height}
            graphData={displayGraphData}
            nodeId="symbol"
            nodeThreeObject={nodeThreeObject}
            linkColor={linkColor}
            linkWidth={linkWidth}
            linkResolution={6}
            linkDirectionalParticles={(link: any) => ((link.weight ?? 0) < 0 ? 6 : 4)}
            linkDirectionalParticleColor={(link: any) => {
              const w = link.weight ?? 0;
              return w < 0 ? "rgba(255, 0, 51, 1.0)" : "rgba(0, 255, 102, 1.0)";
            }}
            linkDirectionalParticleWidth={(link: any) => {
              const w = link.weight ?? 0;
              return w < 0 ? Math.max(1.2, linkWidth(link) * 0.45) : Math.max(0.4, linkWidth(link) * 0.25);
            }} // Dynamic size inside connection link
            linkDirectionalParticleSpeed={(link: any) => 0.012 + (Math.abs(link.motif_similarity || 0.1) * 0.03)}
            backgroundColor="rgba(0,0,0,0)"
            d3AlphaDecay={0.06}
            d3VelocityDecay={0.4}
            cooldownTime={4000}
            onEngineStop={() => {
              if (graphRef.current && !hasZoomed.current) {
                graphRef.current.zoomToFit(400, 40);
                hasZoomed.current = true;
              }
            }}
            onNodeClick={(node: any) => {
              setSelectedNode(node);
            }}
          />
        ) : (
          <ForceGraph2D
            ref={graphRef2D}
            width={dimensions.width}
            height={dimensions.height}
            graphData={displayGraphData}
            nodeId="symbol"
            nodeVal={(node: any) => node.radius || 7}
            nodeCanvasObject={(node: any, ctx: CanvasRenderingContext2D, globalScale: number) => {
              const radius = node.radius || 7;
              
              // 1. Outer transparent signal ring/glow
              ctx.beginPath();
              ctx.arc(node.x, node.y, radius, 0, 2 * Math.PI, false);
              ctx.fillStyle = node.color || palette.muted;
              ctx.globalAlpha = 0.25; // Transparent spheres match 3D
              ctx.fill();
              ctx.globalAlpha = 1.0;
              
              // 2. Render cryptocurrency coin logo clipped inside circle with fallbacks
              const imgId = `img-logo-${node.symbol}`;
              const isKnownFailed = failedIcons.current.has(node.symbol);
              let img = document.getElementById(imgId) as HTMLImageElement;
              if (!img && !isKnownFailed) {
                img = document.createElement("img");
                img.id = imgId;
                img.src = `https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530be6e374711a8554f31b17e4cb92c25fa5/svg/color/${node.symbol.toLowerCase()}.svg`;
                img.style.display = "none";
                img.onload = () => {
                  node.__imgLoaded = true;
                };
                img.onerror = () => {
                  node.__imgFailed = true;
                  failedIcons.current.add(node.symbol);
                };
                document.body.appendChild(img);
              }
              
              if (img && img.complete && img.naturalWidth !== 0 && !node.__imgFailed && !isKnownFailed) {
                ctx.save();
                ctx.beginPath();
                ctx.arc(node.x, node.y, radius * 0.8, 0, 2 * Math.PI, false);
                ctx.clip();
                ctx.drawImage(img, node.x - radius * 0.8, node.y - radius * 0.8, radius * 1.6, radius * 1.6);
                ctx.restore();
              } else {
                // High-quality canvas fallback with colored ring and symbol text
                ctx.save();
                ctx.beginPath();
                ctx.arc(node.x, node.y, radius * 0.8, 0, 2 * Math.PI, false);
                const grad = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, radius * 0.8);
                grad.addColorStop(0, node.color || palette.muted);
                grad.addColorStop(1, 'rgba(15, 23, 42, 0.9)');
                ctx.fillStyle = grad;
                ctx.fill();
                // Border ring
                ctx.strokeStyle = node.color || palette.muted;
                ctx.lineWidth = 1.5;
                ctx.stroke();
                ctx.font = `bold ${Math.max(radius * 0.55, 4)}px monospace`;
                ctx.fillStyle = '#ffffff';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(node.symbol.length <= 4 ? node.symbol : node.symbol.slice(0, 3), node.x, node.y);
                ctx.restore();
              }
              
              // 3. Float ticker text label below
              const fontSize = 11 / globalScale;
              ctx.font = `bold ${fontSize}px monospace`;
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillStyle = '#ffffff';
              ctx.fillText(node.symbol, node.x, node.y + radius + 9 / globalScale);
            }}
            linkColor={linkColor}
            linkWidth={linkWidth}
            linkDirectionalParticles={(link: any) => ((link.weight ?? 0) < 0 ? 6 : 4)}
            linkDirectionalParticleColor={(link: any) => {
              const w = link.weight ?? 0;
              return w < 0 ? "rgba(255, 0, 51, 1.0)" : "rgba(0, 255, 102, 1.0)";
            }}
            linkDirectionalParticleWidth={(link: any) => {
              const w = link.weight ?? 0;
              return w < 0 ? Math.max(1.2, linkWidth(link) * 0.45) : Math.max(0.4, linkWidth(link) * 0.25);
            }} // Dynamic size inside connection link
            linkDirectionalParticleSpeed={(link: any) => 0.012 + (Math.abs(link.motif_similarity || 0.1) * 0.03)}
            backgroundColor="rgba(0,0,0,0)"
            d3AlphaDecay={0.06}
            d3VelocityDecay={0.4}
            cooldownTime={4000}
            onEngineStop={() => {
              if (graphRef2D.current && !hasZoomed.current) {
                graphRef2D.current.zoomToFit(400, 40);
                hasZoomed.current = true;
              }
            }}
            onNodeClick={(node: any) => {
              setSelectedNode(node);
            }}
          />
        )}

        {/* Selected node panel */}
        {selectedNode && (
          <div className="absolute top-4 left-4 w-72 glass-3 rounded-xl p-6 border border-text/10 z-20 space-y-4 shadow-2xl backdrop-blur-2xl animate-in fade-in slide-in-from-left-4">
            <div className="flex justify-between items-start">
              <div className="font-sans text-3xl font-black text-text tracking-tight">{selectedNode.symbol}</div>
              <button onClick={() => setSelectedNode(null)} className="text-text-muted hover:text-text text-sm transition-colors w-6 h-6 flex items-center justify-center rounded-full hover:bg-text/5">✕</button>
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
                    <span className="text-xl font-mono font-black text-text">{(selectedNode.confidence).toFixed(1)}%</span>
                  </div>
                )}
            </div>
          </div>
        )}
      </div>

      {/* Smooth Timeline range control */}
      <div className="relative z-10 w-full glass-2 rounded-xl p-6 border border-text/10 shadow-lg mt-2">
        <div className="flex items-center justify-between mb-4 flex-wrap gap-2">
          <div className="flex items-center gap-3">
            <span className="w-2.5 h-2.5 rounded-full bg-accent animate-pulse" />
            <span className="text-xs font-mono font-black tracking-widest text-text uppercase">Swarm Timeline Controller</span>
          </div>
          <div className="text-xs font-mono font-bold text-accent bg-accent/10 px-3 py-1 rounded">
            {sliderVal < 0.5 ? "90D PAST HISTORY" :
             sliderVal < 1.5 ? "30D PAST HISTORY" :
             sliderVal < 2.5 ? "LIVE ENGINE STATE" :
             sliderVal < 3.5 ? "GNN PROJECTED +15D" : "GNN PROJECTED +30D"}
          </div>
        </div>

        <input 
          type="range"
          min="0"
          max="4"
          step="0.01"
          value={sliderVal}
          onChange={(e) => setSliderVal(parseFloat(e.target.value))}
          className="w-full h-2 bg-text/10 rounded-lg appearance-none cursor-pointer accent-accent focus:outline-none"
        />

        <div className="flex justify-between text-[10px] font-mono text-text-muted mt-3 uppercase tracking-wider font-bold">
          <span>90D Past</span>
          <span>30D Past</span>
          <span className="text-accent font-black">Live Engine</span>
          <span>Projected +15D</span>
          <span>Projected +30D</span>
        </div>
      </div>
    </div>
  );
}
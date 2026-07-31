"use client";
import useSWR from "swr";
import { fetcher, GraphResponse } from "@/lib/api";
import { Skeleton } from "@/components/ui/Skeleton";
import { RefreshCcw, ZoomIn, Activity, Sliders } from "lucide-react";
import dynamic from "next/dynamic";
import { useMemo, useRef, useState, useEffect, useCallback } from "react";
import { useChartPalette } from "@/lib/useChartPalette";
import { useTheme } from "next-themes";
import * as d3 from "d3-force";
import * as THREE from "three";
import { useRouter } from "next/navigation";

const ForceGraph2D = dynamic(() => import("react-force-graph-2d").then((mod) => mod.default || mod), {
  ssr: false,
  loading: () => <Skeleton className="w-full h-[600px] shape-squircle" />,
});

const ForceGraph3D = dynamic(() => import("react-force-graph-3d").then((mod) => mod.default || mod), {
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

// Ensure maximum fallback node visibility
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

export default function CorrelationNetworkGraph() {
  const palette = useChartPalette();
  const { resolvedTheme } = useTheme();
  const router = useRouter();
  
  const [sliderVal, setSliderVal] = useState<number>(2.0); // Smooth continuous float [0.0 - 4.0]
  const [is3D, setIs3D] = useState(false); // Default to lightweight 2D canvas (<35MB RAM)
  const [mounted, setMounted] = useState(false);
  const [refreshTrigger, setRefreshTrigger] = useState(0); // State trigger for 2D image-load repaints & timeline updates
  const failedIcons = useRef<Set<string>>(new Set()); // Cache icon 404s to prevent repeated loads

  useEffect(() => {
    setMounted(true);
  }, []);
  
  const activeMode = useMemo(() => {
    if (sliderVal < 0.8) return "historical";
    if (sliderVal < 1.8) return "historical_30";
    if (sliderVal < 2.5) return "live";
    if (sliderVal < 3.5) return "projected_15";
    return "projected";
  }, [sliderVal]);

  const { data: liveData, error, isLoading, mutate } = useSWR<GraphResponse>(
    `/api/v1/graph/latest?mode=${activeMode}`, 
    fetcher, 
    { revalidateOnFocus: false, dedupingInterval: 60000, refreshInterval: 10000 }
  );

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

    let filtered = minCorrelationThreshold <= 0 
      ? rawLinks 
      : rawLinks.filter((l: any) => Math.abs(l.weight || 0) >= minCorrelationThreshold);

    // Limit maximum edge count to 150 top weighted links to keep RAM < 100 MB and FPS high
    if (filtered.length > 150) {
      filtered = [...filtered].sort((a, b) => Math.abs(b.weight || 0) - Math.abs(a.weight || 0)).slice(0, 150);
    }

    return {
      nodes: graphDataState.nodes,
      links: filtered
    };
  }, [graphDataState, minCorrelationThreshold, refreshTrigger]);

  // Persistent cache for ThreeJS objects to prevent violent recreations
  const nodeThreeObjsMap = useRef<Map<string, THREE.Group>>(new Map());
  const iconImageMap = useRef<Map<string, HTMLImageElement>>(new Map());

  // Memory cleanup helper for ThreeJS groups
  const disposeThreeGroup = (group: THREE.Group) => {
    group.traverse((child: any) => {
      if (child.geometry) child.geometry.dispose();
      if (child.material) {
        if (Array.isArray(child.material)) {
          child.material.forEach((m: any) => {
            if (m.map) m.map.dispose();
            m.dispose();
          });
        } else {
          if (child.material.map) child.material.map.dispose();
          child.material.dispose();
        }
      }
    });
  };

  const handleToggle3D = useCallback(() => {
    setGraphDataState(prev => ({
      nodes: prev.nodes.map((n: any) => {
        const { fx, fy, fz, x, y, z, vx, vy, vz, ...rest } = n;
        return { ...rest };
      }),
      links: prev.links.map((l: any) => ({
        ...l,
        source: typeof l.source === "object" ? l.source.symbol || l.source.id : l.source,
        target: typeof l.target === "object" ? l.target.symbol || l.target.id : l.target,
      }))
    }));
    hasZoomed.current = false;
    nodeThreeObjsMap.current.forEach((group) => disposeThreeGroup(group));
    nodeThreeObjsMap.current.clear();
    setIs3D(prev => !prev);
  }, []);

  useEffect(() => {
    return () => {
      nodeThreeObjsMap.current.forEach((group) => disposeThreeGroup(group));
      nodeThreeObjsMap.current.clear();
      iconImageMap.current.clear();
    };
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

  // Update graph nodes & links when liveData changes for the active mode
  useEffect(() => {
    if (liveData && Array.isArray(liveData.nodes)) {
      const nodes = liveData.nodes.map((n: any) => ({
        ...n,
        radius: getNodeRadius(n.market_cap_usd),
        color: getSignalColor(n.predicted_direction, palette),
      }));

      const nodeIds = new Set(nodes.map((n: any) => n.symbol));
      const links = (liveData.edges || [])
        .filter((e: any) => nodeIds.has(e.source) && nodeIds.has(e.target))
        .map((e: any) => ({
          source: e.source,
          target: e.target,
          weight: e.weight,
          edge_type: e.edge_type,
          motif_similarity: e.motif_similarity,
        }));

      setGraphDataState({ nodes, links });
      setRefreshTrigger(prev => prev + 1);
    }
  }, [liveData, palette]);

  const [spreadMode, setSpreadMode] = useState<"compact" | "normal" | "expanded">("normal");
  const isLight = resolvedTheme === "light";

  const loadCoinIcon = useCallback((symbol: string, onLoaded: (img: HTMLImageElement) => void) => {
    if (failedIcons.current.has(symbol)) return;
    const existing = iconImageMap.current.get(symbol);
    if (existing && existing.complete && existing.naturalWidth !== 0) {
      onLoaded(existing);
      return;
    }

    const sym = symbol.toLowerCase();
    const urls = [
      `https://assets.coincap.io/assets/icons/${sym}@2x.png`,
      `https://raw.githubusercontent.com/spothq/cryptocurrency-icons/master/128/color/${sym}.png`,
      `https://cdn.jsdelivr.net/gh/atomiclabs/cryptocurrency-icons@1a63530be6e374711a8554f31b17e4cb92c25fa5/svg/color/${sym}.svg`
    ];

    let urlIdx = 0;
    const tryNext = () => {
      if (urlIdx >= urls.length) {
        failedIcons.current.add(symbol);
        setRefreshTrigger(prev => prev + 1);
        return;
      }
      const img = new Image();
      img.crossOrigin = "anonymous";
      img.src = urls[urlIdx++];
      img.onload = () => {
        iconImageMap.current.set(symbol, img);
        onLoaded(img);
        setRefreshTrigger(prev => prev + 1);
      };
      img.onerror = () => tryNext();
    };

    tryNext();
  }, []);

  const applyForces = useCallback((graphInstance: any) => {
    if (!graphInstance) return;
    try {
      const isAll = minCorrelationThreshold <= 0;
      let baseDistance = spreadMode === "compact" ? 120 : spreadMode === "expanded" ? 380 : 210;
      let baseCharge = spreadMode === "compact" ? -1100 : spreadMode === "expanded" ? -5500 : -2400;

      // When showing ALL links (100+), scale down distance & charge so 3D graph stays bounded and dense
      if (isAll) {
        baseDistance = Math.round(baseDistance * 0.58);
        baseCharge = Math.round(baseCharge * 0.45);
      }

      const linkForce = graphInstance.d3Force?.('link');
      if (linkForce) {
        linkForce
          .strength((link: any) => (Math.abs(link.weight) || 0.5) * 0.85)
          .distance(baseDistance);
      }
      const chargeForce = graphInstance.d3Force?.('charge');
      if (chargeForce) {
        chargeForce.strength(baseCharge);
      }
      const collideForce = graphInstance.d3Force?.('collision');
      if (collideForce) {
        collideForce.radius((node: any) => (node.radius || 6) * 2.5 + 16);
      } else if (d3.forceCollide) {
        graphInstance.d3Force?.('collision', d3.forceCollide().radius((node: any) => (node.radius || 6) * 2.5 + 16));
      }
      graphInstance.d3ReheatSimulation?.();
    } catch (err) {
      console.warn("Could not apply forces:", err);
    }
  }, [minCorrelationThreshold, spreadMode]);

  useEffect(() => {
    const timer = setTimeout(() => {
      if (is3D && graphRef.current) {
        applyForces(graphRef.current);
      } else if (!is3D && graphRef2D.current) {
        applyForces(graphRef2D.current);
      }
    }, 100);
    return () => clearTimeout(timer);
  }, [is3D, isLoading, minCorrelationThreshold, spreadMode, applyForces]);

  useEffect(() => {
    if (graphDataState.nodes.length > 0) {
      const timer = setTimeout(() => {
        graphRef.current?.zoomToFit?.(800, 120);
        graphRef2D.current?.zoomToFit?.(800, 120);
      }, 600);
      return () => clearTimeout(timer);
    }
  }, [is3D, graphDataState.nodes.length]);

  useEffect(() => {
    if (is3D && graphRef.current) {
      applyForces(graphRef.current);
    } else if (!is3D && graphRef2D.current) {
      applyForces(graphRef2D.current);
    }
  }, [graphDataState, is3D, applyForces]);

  const nodeThreeObject = useCallback((node: any) => {
    const radius = node.radius || 4;

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

    const sphereGeom = new THREE.SphereGeometry(4, 20, 20);
    const sphereMat = new THREE.MeshBasicMaterial({
      color: node.color || palette.muted,
      transparent: true,
      opacity: 0.28,
      depthWrite: false
    });
    const sphereMesh = new THREE.Mesh(sphereGeom, sphereMat);
    sphereMesh.scale.setScalar(radius / 4);

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
      ctx.lineWidth = 2.5;
      ctx.stroke();
      ctx.font = 'bold 16px sans-serif';
      ctx.fillStyle = '#ffffff';
      ctx.textAlign = 'center';
      ctx.textBaseline = 'middle';
      ctx.fillText(node.symbol.length <= 4 ? node.symbol : node.symbol.slice(0, 3), 32, 32);
    }
    const logoTex = new THREE.CanvasTexture(canvas);

    loadCoinIcon(node.symbol, (img) => {
      (logoTex as any).image = img;
      logoTex.needsUpdate = true;
      graphRef.current?.refresh?.();
    });

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
      tCtx.fillStyle = 'rgba(15, 23, 42, 0.92)';
      tCtx.beginPath();
      tCtx.roundRect(10, 36, 108, 56, 8);
      tCtx.fill();
      tCtx.strokeStyle = 'rgba(255, 255, 255, 0.35)';
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
  }, [palette, loadCoinIcon]);

  const linkColor = useCallback((link: any) => {
    const w = link.weight ?? 0;
    if (isLight) {
      // High contrast colors for Bright / Light Mode
      return w >= 0 ? "#047857" : "#dc2626"; // Dark Emerald (#047857) and Dark Crimson Red (#dc2626)
    } else {
      // Electric Neon colors for Dark Mode
      return w >= 0 ? "#00ff66" : "#ff0055"; // Electric Lime (#00ff66) and Electric Red (#ff0055)
    }
  }, [isLight]);

  const linkParticleColor = useCallback((link: any) => {
    const w = link.weight ?? 0;
    if (isLight) {
      return w >= 0 ? "rgba(4, 120, 87, 1.0)" : "rgba(220, 38, 38, 1.0)";
    }
    return w >= 0 ? "rgba(0, 255, 102, 1.0)" : "rgba(255, 0, 85, 1.0)";
  }, [isLight]);

  const linkWidth = useCallback((link: any) => {
    const w = link.weight ?? 0;
    const absWeight = Math.abs(w);
    return w < 0 ? 2.5 + absWeight * 4.5 : 1.5 + absWeight * 3.0;
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

        {/* Timeline Horizon Projection Slider */}
        <div className="flex flex-col gap-1.5 px-4 py-2 bg-surface/50 rounded-lg border border-accent/20 backdrop-blur-md min-w-[280px]">
          <div className="flex justify-between items-center text-[10px] font-mono font-bold uppercase tracking-widest text-text-muted">
            <span className={sliderVal < 1.5 ? "text-accent" : ""}>Past (-90D)</span>
            <span className="text-accent font-black bg-accent/10 px-2 py-0.5 rounded border border-accent/30">
              {sliderVal < 0.8 ? "Historical (-90D)" : sliderVal < 1.8 ? "Historical (-30D)" : sliderVal < 2.5 ? "Present (Live)" : sliderVal < 3.5 ? "Projected (+15D)" : "Projected (+30D)"}
            </span>
            <span className={sliderVal > 2.5 ? "text-accent" : ""}>Future (+30D)</span>
          </div>
          <input
            type="range"
            min="0"
            max="4"
            step="0.05"
            value={sliderVal}
            onChange={(e) => setSliderVal(parseFloat(e.target.value))}
            className="w-full h-1.5 accent-accent bg-text/10 rounded-lg appearance-none cursor-pointer"
          />
        </div>

        <div className="flex flex-wrap items-center gap-3 bg-surface/30 p-2 rounded-lg border border-text/10 backdrop-blur-md">
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

          {/* Spread Control Button */}
          <button 
            onClick={() => {
              setSpreadMode(prev => prev === "compact" ? "normal" : prev === "normal" ? "expanded" : "compact");
            }} 
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono font-bold uppercase tracking-wider rounded border border-text/10 bg-text/5 hover:bg-text/15 text-text transition-all"
            title="Toggle Graph Force Spread (Compact / Normal / Expanded)"
          >
            <Sliders size={14} className="text-accent" />
            Spread: <span className="text-accent capitalize font-black">{spreadMode}</span>
          </button>

          {/* 2D/3D switcher */}
          <button 
            onClick={handleToggle3D} 
            className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono font-bold uppercase tracking-wider rounded border border-text/10 bg-text/5 hover:bg-text/15 text-text transition-all"
          >
            <Activity size={14} className="text-accent" />
            {is3D ? "2D Graph" : "3D Graph"}
          </button>
          
          <button onClick={() => {
            if (is3D) graphRef.current?.zoomToFit(400, 40);
            else graphRef2D.current?.zoomToFit(400, 40);
          }} className="flex items-center gap-2 px-3 py-1.5 text-xs font-mono font-bold uppercase tracking-wider rounded border border-text/10 bg-text/5 hover:bg-text/15 text-text transition-all">
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
            linkDirectionalParticles={0}
            backgroundColor="rgba(0,0,0,0)"
            d3AlphaDecay={0.08}
            d3VelocityDecay={0.6}
            cooldownTime={1500}
            onEngineStop={() => {
              if (graphRef.current) {
                if (!hasZoomed.current) {
                  graphRef.current.zoomToFit(400, 40);
                  hasZoomed.current = true;
                }
                displayGraphData.nodes.forEach((n: any) => {
                  n.fx = n.x;
                  n.fy = n.y;
                  n.fz = n.z;
                });
              }
            }}
            onNodeDragEnd={(node: any) => {
              node.fx = node.x;
              node.fy = node.y;
              node.fz = node.z;
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
              
              ctx.save();
              ctx.beginPath();
              ctx.arc(node.x, node.y, radius * 1.4, 0, 2 * Math.PI, false);
              ctx.fillStyle = node.color || palette.muted;
              ctx.globalAlpha = 0.15;
              ctx.fill();
              ctx.restore();
              
              const isKnownFailed = failedIcons.current.has(node.symbol);
              let img = iconImageMap.current.get(node.symbol);
              if (!img && !isKnownFailed) {
                loadCoinIcon(node.symbol, () => {});
              }
              
              const logoRadius = radius * 1.0;
              if (img && img.complete && img.naturalWidth !== 0 && !isKnownFailed) {
                ctx.save();
                ctx.beginPath();
                ctx.arc(node.x, node.y, logoRadius, 0, 2 * Math.PI, false);
                ctx.clip();
                ctx.drawImage(img, node.x - logoRadius, node.y - logoRadius, logoRadius * 2, logoRadius * 2);
                ctx.restore();
                
                ctx.save();
                ctx.beginPath();
                ctx.arc(node.x, node.y, logoRadius, 0, 2 * Math.PI, false);
                ctx.strokeStyle = node.color || palette.muted;
                ctx.lineWidth = 1.5;
                ctx.stroke();
                ctx.restore();
              } else {
                ctx.save();
                ctx.beginPath();
                ctx.arc(node.x, node.y, logoRadius, 0, 2 * Math.PI, false);
                const grad = ctx.createRadialGradient(node.x, node.y, 0, node.x, node.y, logoRadius);
                grad.addColorStop(0, node.color || palette.muted);
                grad.addColorStop(1, 'rgba(15, 23, 42, 0.95)');
                ctx.fillStyle = grad;
                ctx.fill();
                ctx.strokeStyle = node.color || palette.muted;
                ctx.lineWidth = 1.5;
                ctx.stroke();
                ctx.font = `bold ${Math.max(logoRadius * 0.7, 5)}px monospace`;
                ctx.fillStyle = '#ffffff';
                ctx.textAlign = 'center';
                ctx.textBaseline = 'middle';
                ctx.fillText(node.symbol.length <= 4 ? node.symbol : node.symbol.slice(0, 3), node.x, node.y);
                ctx.restore();
              }
              
              const fontSize = 8.5 / globalScale;
              const textY = node.y + radius * 1.4 + 9 / globalScale;
              const textWidth = (node.symbol.length * 5.5 + 8) / globalScale;
              const textHeight = 12 / globalScale;
              const pillRadius = 3 / globalScale;
              
              ctx.save();
              ctx.fillStyle = 'rgba(15, 23, 42, 0.9)';
              ctx.strokeStyle = 'rgba(255, 255, 255, 0.15)';
              ctx.lineWidth = 1 / globalScale;
              ctx.beginPath();
              if (ctx.roundRect) {
                ctx.roundRect(node.x - textWidth / 2, textY - textHeight / 2, textWidth, textHeight, pillRadius);
              } else {
                ctx.rect(node.x - textWidth / 2, textY - textHeight / 2, textWidth, textHeight);
              }
              ctx.fill();
              ctx.stroke();

              ctx.font = `bold ${fontSize}px monospace`;
              ctx.fillStyle = '#ffffff';
              ctx.textAlign = 'center';
              ctx.textBaseline = 'middle';
              ctx.fillText(node.symbol, node.x, textY);
              ctx.restore();
            }}
            linkColor={linkColor}
            linkWidth={linkWidth}
            linkDirectionalParticles={0}
            backgroundColor="rgba(0,0,0,0)"
            d3AlphaDecay={0.08}
            d3VelocityDecay={0.6}
            cooldownTime={1500}
            onEngineStop={() => {
              if (graphRef2D.current) {
                if (!hasZoomed.current) {
                  graphRef2D.current.zoomToFit(400, 40);
                  hasZoomed.current = true;
                }
                displayGraphData.nodes.forEach((n: any) => {
                  n.fx = n.x;
                  n.fy = n.y;
                });
              }
            }}
            onNodeDragEnd={(node: any) => {
              node.fx = node.x;
              node.fy = node.y;
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
    </div>
  );
}

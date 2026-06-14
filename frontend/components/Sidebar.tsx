"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Search, Activity, BarChart2, Shield, TrendingUp, Target, Grid3x3, SlidersHorizontal, Network, Brain, Settings, Wallet, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { StatusIndicator } from "@/components/StatusIndicator";
import { LivePulse } from "@/components/LivePulse";

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const pathname = usePathname();

  const handleSync = async () => {
    setSyncing(true);
    try {
      await fetch("http://localhost:8000/api/stream/broadcast", { method: "POST" });
    } catch (e) {
      console.error(e);
    }
    setTimeout(() => setSyncing(false), 2000);
  };

  const navGroups = [
    {
      title: "Discover",
      items: [
        { name: "Search Asset", icon: <Search size={14} />, onClick: () => window.dispatchEvent(new Event("open-global-search")) },
      ]
    },
    {
      title: "Markets",
      items: [
        { name: "Market Data", href: "/market", icon: <BarChart2 size={14} /> },
        { name: "Screener", href: "/screener", icon: <SlidersHorizontal size={14} /> },
      ]
    },
    {
      title: "Analysis",
      items: [
        { name: "Network Graph", href: "/graph", icon: <Network size={14} /> },
        { name: "Correlations", href: "/correlations", icon: <Grid3x3 size={14} /> },
        { name: "Sentiment", href: "/sentiment", icon: <Activity size={14} /> },
        { name: "Risk Dashboard", href: "/risk", icon: <Shield size={14} /> },
      ]
    },
    {
      title: "AI & Models",
      items: [
        { name: "Explain AI", href: "/explain", icon: <Brain size={14} /> },
        { name: "Predictions", href: "/predictions", icon: <TrendingUp size={14} /> },
        { name: "Performance", href: "/performance", icon: <Target size={14} /> },
        { name: "Portfolio", href: "/portfolio", icon: <Wallet size={14} /> },
      ]
    },
    {
      title: "System",
      items: [
        { name: "Settings", href: "/settings", icon: <Settings size={14} /> },
      ]
    }
  ];

  return (
    <aside className={`relative border-r border-white/5 bg-[#050505]/60 backdrop-blur-3xl flex flex-col transition-all duration-500 z-50 ${collapsed ? "w-16" : "w-60"}`}>
      
      {/* Collapse Toggle */}
      <button 
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-2.5 top-8 bg-indigo-500 hover:bg-indigo-400 text-white p-0.5 rounded-full shadow-[0_0_15px_rgba(99,102,241,0.5)] z-50 transition-colors"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>

      <div className={`p-5 border-b border-white/5 flex flex-col ${collapsed ? 'items-center' : ''}`}>
        {!collapsed ? (
            <div className="flex justify-between items-center mb-4">
                <div className="flex flex-col">
                    <h1 className="text-xl font-black text-transparent bg-clip-text bg-gradient-to-br from-white to-slate-500 tracking-tight leading-none">ST-GCN</h1>
                    <span className="text-[9px] text-indigo-400 tracking-[0.2em] font-medium uppercase mt-1">Intelligence</span>
                </div>
                <LivePulse />
            </div>
        ) : (
            <div className="w-8 h-8 rounded-full bg-gradient-to-tr from-indigo-500 to-cyan-500 flex items-center justify-center text-white font-bold mb-4 shadow-lg shadow-indigo-500/20">
                ST
            </div>
        )}
        
        {/* Sleek Sync Button */}
        <button 
            onClick={handleSync}
            disabled={syncing}
            className={`flex items-center justify-center gap-1.5 w-full py-1.5 px-2 bg-indigo-500/10 hover:bg-indigo-500/20 border border-indigo-500/20 rounded-md text-[10px] font-mono text-indigo-300 transition-all shadow-[0_0_10px_rgba(99,102,241,0.05)] ${syncing ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
            <RefreshCw size={12} className={syncing ? 'animate-spin text-cyan-400' : ''} />
            {!collapsed && <span className="uppercase tracking-widest">{syncing ? 'Syncing...' : 'Live Sync'}</span>}
        </button>
      </div>

      <nav className="flex-1 py-2 space-y-4 overflow-y-auto overflow-x-hidden" style={{ msOverflowStyle: 'none', scrollbarWidth: 'none' }}>
        {navGroups.map((group, idx) => (
          <div key={idx} className={collapsed ? "px-2" : "px-3"}>
            {!collapsed && (
              <h2 className="text-[9px] font-bold text-slate-600 uppercase tracking-widest px-2 mb-2">{group.title}</h2>
            )}
            <div className="space-y-0.5">
              {group.items.map((item: any, iIdx) => {
                const isActive = item.href ? pathname === item.href : false;
                const commonClasses = `flex items-center gap-3 px-2 py-1.5 rounded-md transition-all duration-300 ${
                  isActive 
                    ? "bg-white/10 text-white shadow-[inset_0_1px_0_rgba(255,255,255,0.1)]" 
                    : "text-slate-400 hover:text-slate-200 hover:bg-white/5 cursor-pointer"
                } ${collapsed ? "justify-center" : "w-full text-left"}`;
                
                const content = (
                  <>
                    <div className={`${isActive ? 'text-indigo-400 drop-shadow-[0_0_8px_rgba(99,102,241,0.5)]' : ''}`}>
                        {item.icon}
                    </div>
                    {!collapsed && <span className="text-sm tracking-wide font-light">{item.name}</span>}
                  </>
                );

                if (item.href) {
                  return (
                    <Link key={iIdx} href={item.href} className={commonClasses} title={collapsed ? item.name : undefined}>
                      {content}
                    </Link>
                  );
                } else {
                  return (
                    <button key={iIdx} onClick={item.onClick} className={commonClasses} title={collapsed ? item.name : undefined}>
                      {content}
                    </button>
                  );
                }
              })}
            </div>
          </div>
        ))}
      </nav>
      
      {!collapsed ? (
        <div className="p-4 border-t border-white/5">
            <StatusIndicator />
        </div>
      ) : (
        <div className="p-4 border-t border-white/5 flex justify-center">
            <div className="w-2 h-2 rounded-full bg-emerald-500 shadow-[0_0_10px_rgba(16,185,129,0.8)]" title="System Online"></div>
        </div>
      )}
    </aside>
  );
}

"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Search, Activity, BarChart2, Shield, TrendingUp, Target, Grid3x3, SlidersHorizontal, Network, Brain, Settings, Wallet, ChevronLeft, ChevronRight, RefreshCw } from "lucide-react";
import { StatusIndicator } from "@/components/StatusIndicator";
import { LivePulse } from "@/components/LivePulse";
import { ThemeToggle } from "@/components/ThemeToggle";

export function Sidebar() {
  const [collapsed, setCollapsed] = useState(false);
  const [syncing, setSyncing] = useState(false);
  const pathname = usePathname();

  const handleSync = async () => {
    setSyncing(true);
    try {
      await fetch(`${process.env.NEXT_PUBLIC_API_URL || "http://localhost:8000"}/api/status/refresh-all`, { method: "POST" });
    } catch (e) {
      console.error(e);
    }
    setTimeout(() => setSyncing(false), 2000);
  };

  const navGroups = [
    {
      title: "Discover",
      items: [
        { name: "Search Asset", icon: <Search size={16} />, onClick: () => window.dispatchEvent(new Event("open-global-search")) },
      ]
    },
    {
      title: "Markets",
      items: [
        { name: "Market Data", href: "/market", icon: <BarChart2 size={16} /> },
        { name: "Screener", href: "/screener", icon: <SlidersHorizontal size={16} /> },
      ]
    },
    {
      title: "Analysis",
      items: [
        { name: "Network Graph", href: "/graph", icon: <Network size={16} /> },
        { name: "Correlations", href: "/correlations", icon: <Grid3x3 size={16} /> },
        { name: "Sentiment", href: "/sentiment", icon: <Activity size={16} /> },
        { name: "Risk Dashboard", href: "/risk", icon: <Shield size={16} /> },
      ]
    },
    {
      title: "AI & Models",
      items: [
        { name: "Explain AI", href: "/explain", icon: <Brain size={16} /> },
        { name: "Predictions", href: "/predictions", icon: <TrendingUp size={16} /> },
        { name: "Performance", href: "/performance", icon: <Target size={16} /> },
        { name: "Portfolio", href: "/portfolio", icon: <Wallet size={16} /> },
      ]
    },
    {
      title: "System",
      items: [
        { name: "Settings", href: "/settings", icon: <Settings size={16} /> },
      ]
    }
  ];

  return (
    <aside className={`absolute md:relative glass-panel flex flex-col transition-all duration-500 z-50 rounded-tl-[40px] rounded-br-[40px] rounded-tr-[10px] rounded-bl-[10px] my-2 shrink-0 ${collapsed ? "w-20 -translate-x-[120%] md:translate-x-0" : "w-64 translate-x-0"} h-[calc(100vh-1rem)] md:h-auto`}>
      
      {/* Collapse Toggle */}
      <button 
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3 top-10 bg-accent hover:scale-110 text-white p-1 rounded-crypto-sm shadow-[0_0_15px_rgba(var(--accent),0.5)] z-50 transition-all duration-300"
      >
        {collapsed ? <ChevronRight size={14} /> : <ChevronLeft size={14} />}
      </button>

      <div className={`p-6 border-b border-white/5 flex flex-col ${collapsed ? 'items-center' : ''}`}>
        {!collapsed ? (
            <div className="flex justify-between items-center mb-6">
                <div className="flex flex-col">
                    <h1 className="text-2xl font-black text-transparent bg-clip-text bg-gradient-to-br from-text to-text-muted tracking-tight leading-none">ST-GCN</h1>
                    <span className="text-[10px] text-accent tracking-[0.3em] font-bold uppercase mt-1">Intelligence</span>
                </div>
                <LivePulse />
            </div>
        ) : (
            <div className="w-10 h-10 rounded-crypto-sm bg-gradient-to-tr from-accent to-orange-500 flex items-center justify-center text-white font-bold mb-6 shadow-lg shadow-accent/20">
                ST
            </div>
        )}
        
        {/* Scheduler Button */}
        <button 
            onClick={handleSync}
            disabled={syncing}
            className={`flex items-center justify-center gap-2 w-full py-2 px-3 bg-accent/10 hover:bg-accent/20 border border-accent/20 rounded-crypto-sm text-xs font-mono text-accent transition-all shadow-[0_0_10px_rgba(var(--accent),0.05)] ${syncing ? 'opacity-50 cursor-not-allowed' : ''}`}
        >
            <RefreshCw size={14} className={syncing ? 'animate-spin text-orange-400' : ''} />
            {!collapsed && <span className="uppercase tracking-widest">{syncing ? 'Running...' : 'Run Scheduler'}</span>}
        </button>
      </div>

      <nav className="flex-1 py-4 space-y-6 overflow-y-auto overflow-x-hidden" style={{ msOverflowStyle: 'none', scrollbarWidth: 'none' }}>
        {navGroups.map((group, idx) => (
          <div key={idx} className={collapsed ? "px-2" : "px-4"}>
            {!collapsed && (
              <h2 className="text-[10px] font-bold text-text-muted/60 uppercase tracking-widest px-3 mb-3">{group.title}</h2>
            )}
            <div className="space-y-1">
              {group.items.map((item: any, iIdx) => {
                const isActive = item.href ? pathname === item.href : false;
                const commonClasses = `flex items-center gap-4 px-3 py-2.5 transition-all duration-300 group ${
                  isActive 
                    ? "bg-accent/10 text-text border border-accent/30 shadow-[0_0_15px_rgba(var(--accent),0.1)] rounded-crypto" 
                    : "text-text-muted hover:text-text hover:bg-white/5 hover:translate-x-1 rounded-crypto-sm cursor-pointer"
                } ${collapsed ? "justify-center" : "w-full text-left"}`;
                
                const content = (
                  <>
                    <div className={`transition-all duration-300 ${isActive ? 'text-accent drop-shadow-[0_0_8px_rgba(var(--accent),0.5)] scale-110' : 'group-hover:text-accent group-hover:scale-110'}`}>
                        {item.icon}
                    </div>
                    {!collapsed && <span className="text-sm tracking-wide font-medium">{item.name}</span>}
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
      
      <div className={`p-4 border-t border-white/5 flex items-center ${collapsed ? 'flex-col gap-4 justify-center' : 'justify-between'}`}>
        {!collapsed && <StatusIndicator />}
        {collapsed && (
          <div className="w-2 h-2 rounded-full bg-success shadow-[0_0_10px_rgba(34,197,94,0.8)]" title="System Online"></div>
        )}
        <ThemeToggle />
      </div>
    </aside>
  );
}

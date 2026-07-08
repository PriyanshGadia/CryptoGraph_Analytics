"use client";

import Link from "next/link";
import { usePathname } from "next/navigation";
import { useState } from "react";
import { Menu, BarChart2, Network, TrendingUp, Shield, Wallet } from "lucide-react";
import { StatusIndicator } from "@/components/StatusIndicator";
import { ThemeToggle } from "@/components/ThemeToggle";
import { Directory, type DirectorySection } from "@/components/Directory";

export const NAV_GROUPS: DirectorySection[] = [
  { title: "Discover", items: [{ name: "Search Asset", action: () => window.dispatchEvent(new Event("open-global-search")) }] },
  { title: "Markets", items: [{ name: "Market Data", href: "/market" }, { name: "Screener", href: "/screener" }] },
  { title: "Analysis", items: [
      { name: "Network Graph", href: "/graph" },
      { name: "Correlations", href: "/correlations" },
      { name: "Sentiment", href: "/sentiment" },
      { name: "Risk Dashboard", href: "/risk" },
  ]},
  { title: "AI & Models", items: [
      { name: "Explain AI", href: "/explain" },
      { name: "Predictions", href: "/predictions" },
      { name: "Performance", href: "/performance" },
      { name: "Portfolio", href: "/portfolio" },
  ]},
  { title: "System", items: [{ name: "Settings", href: "/settings" }] },
];

const QUICK_ITEMS = [
  { name: "Market Data", href: "/market", icon: <BarChart2 size={18} /> },
  { name: "Network Graph", href: "/graph", icon: <Network size={18} /> },
  { name: "Predictions", href: "/predictions", icon: <TrendingUp size={18} /> },
  { name: "Risk Dashboard", href: "/risk", icon: <Shield size={18} /> },
  { name: "Portfolio", href: "/portfolio", icon: <Wallet size={18} /> },
];

export function Console() {
  const [directoryOpen, setDirectoryOpen] = useState(false);
  const pathname = usePathname();

  return (
    <>
      <nav
        className="fixed z-40 glass-2 depth-bevel flex
                   bottom-3 left-3 right-3 h-16 flex-row items-center justify-between px-4 shape-facet
                   md:bottom-auto md:right-auto md:top-3 md:left-3 md:h-[calc(100vh-1.5rem)] md:w-16
                   md:flex-col md:justify-between md:px-0 md:py-4 md:shape-squircle"
      >
        <div className="flex md:flex-col items-center gap-1 md:gap-3">
          <button
            onClick={() => setDirectoryOpen(true)}
            className="w-10 h-10 shape-facet-sm flex items-center justify-center text-text-muted hover:text-accent-2 transition-colors duration-[var(--dur-hover)]"
            aria-label="Open navigation"
          >
            <Menu size={18} />
          </button>
          {QUICK_ITEMS.map((item) => {
            const isActive = pathname === item.href;
            return (
              <Link
                key={item.href}
                href={item.href}
                title={item.name}
                className={`relative w-10 h-10 shape-facet-sm flex items-center justify-center transition-all duration-[var(--dur-hover)] ease-glide ${
                  isActive ? "text-accent shadow-[0_0_15px_rgba(var(--accent),0.2)]" : "text-text-muted hover:text-text hover:scale-110"
                }`}
              >
                {item.icon}
              </Link>
            );
          })}
        </div>
        <div className="flex md:flex-col items-center gap-3">
          <StatusIndicator compact />
          <ThemeToggle />
        </div>
      </nav>
      <Directory open={directoryOpen} onClose={() => setDirectoryOpen(false)} sections={NAV_GROUPS} />
    </>
  );
}

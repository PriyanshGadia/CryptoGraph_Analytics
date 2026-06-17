"use client";

import { useState, useEffect, useRef } from "react";
import { createPortal } from "react-dom";
import useSWR from "swr";
import { fetcher } from "@/lib/api";
import Link from "next/link";
import { Search, ChevronRight } from "lucide-react";
import { useRouter } from "next/navigation";

export function GlobalSearch() {
  const [isOpen, setIsOpen] = useState(false);
  const [query, setQuery] = useState("");
  const [selectedIndex, setSelectedIndex] = useState(0);
  const inputRef = useRef<HTMLInputElement>(null);
  const router = useRouter();

  const { data: assets } = useSWR("/api/assets", fetcher, {
    revalidateOnFocus: false,
    revalidateOnReconnect: false
  });

  useEffect(() => {
    const handleKeyDown = (e: KeyboardEvent) => {
      if ((e.metaKey || e.ctrlKey) && e.key === "k") {
        e.preventDefault();
        setIsOpen((prev) => !prev);
      }
      if (e.key === "Escape") {
        setIsOpen(false);
      }
    };
    
    const handleOpenSearch = () => setIsOpen(true);
    
    window.addEventListener("keydown", handleKeyDown);
    window.addEventListener("open-global-search", handleOpenSearch);
    
    return () => {
      window.removeEventListener("keydown", handleKeyDown);
      window.removeEventListener("open-global-search", handleOpenSearch);
    };
  }, []);

  useEffect(() => {
    if (isOpen) {
      setTimeout(() => inputRef.current?.focus(), 10);
      setQuery("");
      setSelectedIndex(0);
    }
  }, [isOpen]);

  const filteredAssets = (assets || []).filter((a: any) => 
    a.symbol.toLowerCase().includes(query.toLowerCase()) || 
    (a.name && a.name.toLowerCase().includes(query.toLowerCase())) ||
    (a.sector && a.sector.toLowerCase().includes(query.toLowerCase()))
  ).slice(0, 8);

  const handleKeyDown = (e: React.KeyboardEvent) => {
    if (e.key === "ArrowDown") {
      e.preventDefault();
      setSelectedIndex(prev => Math.min(prev + 1, filteredAssets.length - 1));
    } else if (e.key === "ArrowUp") {
      e.preventDefault();
      setSelectedIndex(prev => Math.max(prev - 1, 0));
    } else if (e.key === "Enter") {
      e.preventDefault();
      if (filteredAssets.length > 0 && filteredAssets[selectedIndex]) {
        router.push(`/coin/${filteredAssets[selectedIndex].symbol}`);
        setIsOpen(false);
      }
    }
  };

  if (!isOpen) return null;

  return createPortal(
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-32 bg-background/60 backdrop-blur-xl transition-all duration-500" onClick={() => setIsOpen(false)}>
      <div 
        className="w-full max-w-2xl flex flex-col gap-4 px-4"
        onClick={(e) => e.stopPropagation()}
      >
        {/* Search Input Pill */}
        <div className="glass-panel rounded-crypto-lg p-2 shadow-[0_10px_40px_rgba(0,0,0,0.5)] transform animate-in fade-in slide-in-from-top-4 duration-500">
          <div className="flex items-center px-4 py-2 bg-surface/40 rounded-crypto border border-white/5 focus-within:border-accent/50 focus-within:shadow-[0_0_20px_rgba(var(--accent),0.2)] transition-all duration-300">
            <Search className="text-accent mr-3" size={24} />
            <input
              ref={inputRef}
              className="flex-1 bg-transparent border-none outline-none text-text text-xl placeholder-text-muted font-sans"
              placeholder="Decrypt assets, sectors..."
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              onKeyDown={handleKeyDown}
            />
            <div className="text-[10px] text-text-muted/60 font-mono tracking-widest border border-white/10 px-2 py-1 rounded-md bg-white/5 uppercase">ESC</div>
          </div>
        </div>
        
        {/* Results */}
        {filteredAssets.length > 0 ? (
          <div className="py-2 max-h-[60vh] overflow-y-auto space-y-2" style={{ msOverflowStyle: 'none', scrollbarWidth: 'none' }}>
            {filteredAssets.map((asset: any, idx: number) => (
              <Link
                key={asset.id}
                href={`/coin/${asset.symbol}`}
                className={`flex items-center justify-between px-6 py-4 rounded-crypto glass transition-all duration-300 transform block animate-in fade-in slide-in-from-bottom-4 ${
                  idx === selectedIndex 
                    ? "bg-accent/10 border-accent/40 shadow-[0_0_20px_rgba(var(--accent),0.15)] scale-[1.02]" 
                    : "bg-surface/30 border-white/5 hover:bg-white/10 hover:border-white/20 hover:scale-[1.01]"
                }`}
                style={{ animationFillMode: 'both', animationDelay: `${idx * 50}ms` }}
                onClick={() => setIsOpen(false)}
                onMouseEnter={() => setSelectedIndex(idx)}
              >
                <div className="flex items-center gap-4">
                  <span className="font-bold font-mono text-text text-xl tracking-wide">{asset.symbol}</span>
                  <span className="text-sm text-text-muted font-light">{asset.name}</span>
                  <span className="text-[10px] uppercase bg-white/5 text-text-muted px-2 py-1 rounded-sm border border-white/10 tracking-widest">{asset.sector}</span>
                </div>
                <div className="flex items-center gap-4">
                  {asset.predicted_direction && (
                    <span className={`text-[10px] uppercase px-2 py-1 rounded-sm border font-bold tracking-widest ${
                      ['up', 'strong_up'].includes(asset.predicted_direction) 
                      ? "bg-success/10 text-success border-success/30 shadow-[0_0_10px_rgba(34,197,94,0.2)]" 
                      : ['down', 'strong_down'].includes(asset.predicted_direction)
                      ? "bg-danger/10 text-danger border-danger/30 shadow-[0_0_10px_rgba(239,68,68,0.2)]"
                      : "bg-white/5 text-text-muted border-white/10"
                    }`}>
                      {asset.predicted_direction.replace('_', ' ')}
                    </span>
                  )}
                  <ChevronRight size={18} className={`transition-all duration-300 ${idx === selectedIndex ? "text-accent translate-x-1" : "text-text-muted/40"}`} />
                </div>
              </Link>
            ))}
          </div>
        ) : query ? (
          <div className="glass-panel rounded-crypto p-12 text-center text-text-muted font-light text-lg animate-in fade-in">
            No decryptions found matching <span className="font-mono text-text">&quot;{query}&quot;</span>
          </div>
        ) : null}
      </div>
    </div>,
    document.body
  );
}

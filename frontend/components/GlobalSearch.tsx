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
    <div className="fixed inset-0 z-[100] flex items-start justify-center pt-32 bg-black/60 backdrop-blur-md transition-all duration-[var(--dur-enter)] ease-glide" onClick={() => setIsOpen(false)}>
      <div 
        className="w-full max-w-2xl px-4"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="glass-3 rounded-2xl p-4 border border-text/10 shadow-[0_20px_50px_rgba(0,0,0,0.5)] backdrop-blur-xl bg-surface/30 flex flex-col gap-4 transform animate-in fade-in slide-in-from-top-4 duration-[var(--dur-enter)] ease-glide">
          {/* Search Input Pill */}
          <div className="flex items-center px-4 py-3 bg-surface-2/40 rounded-xl border border-text/10 focus-within:border-accent/50 focus-within:shadow-[0_0_20px_rgba(var(--accent),0.15)] transition-all duration-[var(--dur-hover)] ease-glide">
            <Search className="text-accent mr-3" size={24} />
            <input
              ref={inputRef}
              className="flex-1 bg-transparent border-none outline-none text-text text-xl placeholder-text-muted/60 font-sans"
              placeholder="Decrypt assets, sectors..."
              value={query}
              onChange={(e) => {
                setQuery(e.target.value);
                setSelectedIndex(0);
              }}
              onKeyDown={handleKeyDown}
            />
            <div className="text-[10px] text-text-muted/60 font-mono tracking-widest border border-text/10 px-2 py-1 rounded-md bg-text/5 uppercase">ESC</div>
          </div>
          
          {/* Results */}
          {filteredAssets.length > 0 ? (
            <div className="py-2 max-h-[60vh] overflow-y-auto space-y-2" style={{ msOverflowStyle: 'none', scrollbarWidth: 'none' }}>
              {filteredAssets.map((asset: any, idx: number) => (
                <Link
                  key={asset.id}
                  href={`/coin/${asset.symbol}`}
                  className={`flex items-center justify-between px-6 py-4 rounded-xl transition-all duration-[var(--dur-hover)] ease-glide transform block ${
                    idx === selectedIndex 
                      ? "bg-accent/15 border-accent/40 shadow-[0_0_15px_rgba(var(--accent),0.15)] scale-[1.01]" 
                      : "bg-surface/10 backdrop-blur-sm border-border/5 hover:bg-surface/20 hover:border-border/20"
                  } border`}
                  style={{ animationFillMode: 'both', animationDelay: `${Math.min(idx, 5) * 50}ms` }}
                  onClick={() => setIsOpen(false)}
                  onMouseEnter={() => setSelectedIndex(idx)}
                >
                  <div className="flex items-center gap-4">
                    <span className="font-bold font-mono text-text text-lg tracking-wide">{asset.symbol}</span>
                    <span className="text-sm text-text-muted font-light">{asset.name}</span>
                    <span className="text-[10px] uppercase bg-text/5 text-text-muted px-2 py-0.5 rounded-sm border border-text/10 tracking-widest">{asset.sector}</span>
                  </div>
                  <div className="flex items-center gap-4">
                    {asset.predicted_direction && (
                      <span className={`text-[10px] uppercase px-2 py-0.5 rounded-sm border font-bold tracking-widest ${
                        ['up', 'strong_up'].includes(asset.predicted_direction) 
                        ? "bg-success/15 text-success border-success/30 shadow-[0_0_10px_rgba(var(--success),0.15)]" 
                        : ['down', 'strong_down'].includes(asset.predicted_direction)
                        ? "bg-danger/15 text-danger border-danger/30 shadow-[0_0_10px_rgba(var(--danger),0.15)]"
                        : "bg-text/5 text-text-muted border-text/10"
                      }`}>
                        {asset.predicted_direction.replace('_', ' ')}
                      </span>
                    )}
                    <ChevronRight size={16} className={`transition-all duration-300 ${idx === selectedIndex ? "text-accent translate-x-1" : "text-text-muted/40"}`} />
                  </div>
                </Link>
              ))}
            </div>
          ) : query ? (
            <div className="rounded-xl p-8 text-center text-text-muted font-light text-md bg-surface-2/15 border border-border/5">
              No decryptions found matching <span className="font-mono text-text">&quot;{query}&quot;</span>
            </div>
          ) : null}
        </div>
      </div>
    </div>,
    document.body
  );
}


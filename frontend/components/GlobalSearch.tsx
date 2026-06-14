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
    <div className="fixed inset-0 z-50 flex items-start justify-center pt-32 bg-black/50 backdrop-blur-sm" onClick={() => setIsOpen(false)}>
      <div 
        className="w-full max-w-2xl bg-[#1a1a1a] rounded-xl border border-[#2a2a2a] shadow-2xl overflow-hidden"
        onClick={(e) => e.stopPropagation()}
      >
        <div className="flex items-center px-4 py-3 border-b border-[#2a2a2a]">
          <Search className="text-[#94a3b8] mr-3" size={20} />
          <input
            ref={inputRef}
            className="flex-1 bg-transparent border-none outline-none text-white text-lg placeholder-[#4a4a4a]"
            placeholder="Search assets, sectors..."
            value={query}
            onChange={(e) => {
              setQuery(e.target.value);
              setSelectedIndex(0);
            }}
            onKeyDown={handleKeyDown}
          />
          <div className="text-xs text-[#4a4a4a] border border-[#2a2a2a] px-2 py-1 rounded bg-[#0f0f0f]">ESC</div>
        </div>
        
        {filteredAssets.length > 0 ? (
          <div className="py-2 max-h-96 overflow-y-auto">
            {filteredAssets.map((asset: any, idx: number) => (
              <Link
                key={asset.id}
                href={`/coin/${asset.symbol}`}
                className={`flex items-center justify-between px-4 py-3 mx-2 rounded-lg cursor-pointer transition-colors ${
                  idx === selectedIndex ? "bg-indigo-600/20 text-white" : "text-[#94a3b8] hover:bg-[#2a2a2a] hover:text-white"
                }`}
                onClick={() => setIsOpen(false)}
                onMouseEnter={() => setSelectedIndex(idx)}
              >
                <div className="flex items-center gap-3">
                  <span className="font-bold font-mono text-white text-lg">{asset.symbol}</span>
                  <span className="text-xs">{asset.name}</span>
                  <span className="text-[10px] uppercase bg-[#2a2a2a] text-[#cbd5e1] px-1.5 py-0.5 rounded border border-[#3a3a3a]">{asset.sector}</span>
                </div>
                <div className="flex items-center gap-4">
                  {asset.predicted_direction && (
                    <span className={`text-[10px] uppercase px-1.5 py-0.5 rounded border font-bold ${
                      ['up', 'strong_up'].includes(asset.predicted_direction) 
                      ? "bg-green-900/30 text-green-400 border-green-800" 
                      : ['down', 'strong_down'].includes(asset.predicted_direction)
                      ? "bg-red-900/30 text-red-400 border-red-800"
                      : "bg-[#2a2a2a] text-[#94a3b8] border-[#3a3a3a]"
                    }`}>
                      {asset.predicted_direction.replace('_', ' ')}
                    </span>
                  )}
                  <ChevronRight size={16} className={idx === selectedIndex ? "text-indigo-400" : "text-[#4a4a4a]"} />
                </div>
              </Link>
            ))}
          </div>
        ) : (
          <div className="py-12 text-center text-[#4a4a4a]">
            No assets found matching "{query}"
          </div>
        )}
      </div>
    </div>,
    document.body
  );
}

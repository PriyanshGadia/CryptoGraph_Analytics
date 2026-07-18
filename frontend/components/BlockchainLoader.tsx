import React, { useEffect, useState } from "react";

export function BlockchainLoader({ onComplete, duration = 1150 }: { onComplete?: () => void; duration?: number }) {
  const [progress, setProgress] = useState(0);
  const [fade, setFade] = useState(false);

  useEffect(() => {
    const start = Date.now();

    const interval = setInterval(() => {
      const elapsed = Date.now() - start;
      const pct = Math.min(100, Math.floor((elapsed / duration) * 100));
      setProgress(pct);

      if (pct >= 100) {
        clearInterval(interval);
        setTimeout(() => {
          setFade(true);
          if (onComplete) {
            onComplete();
          }
        }, 180);
      }
    }, 16);

    return () => clearInterval(interval);
  }, [onComplete]);

  if (fade) return null;

  return (
    <div className="fixed inset-0 z-[9999] flex flex-col items-center justify-center bg-background text-text overflow-hidden select-none">
      {/* Day: wood-bark texture. Night: circuit/dot-grid texture. */}
      <div
        className="absolute inset-0 opacity-10 pointer-events-none dark:hidden"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='160' height='160'%3E%3Cpath d='M10,0 Q18,55 10,120 M34,0 Q26,60 34,120 M60,0 Q50,65 60,120 M86,0 Q96,60 86,120 M112,0 Q102,65 112,120 M140,0 Q150,60 140,120' stroke='rgba(var(--accent),0.4)' stroke-width='1.2' fill='none'/%3E%3C/svg%3E")`,
          backgroundSize: '160px 160px',
        }}
      />
      <div
        className="absolute inset-0 opacity-[0.14] pointer-events-none hidden dark:block"
        style={{
          backgroundImage: `url("data:image/svg+xml,%3Csvg xmlns='http://www.w3.org/2000/svg' width='120' height='120'%3E%3Cpath d='M0,30 H120 M0,90 H120 M30,0 V120 M90,0 V120' stroke='%2300e5ff' stroke-width='0.4' fill='none' opacity='0.5'/%3E%3Ccircle cx='30' cy='30' r='1.6' fill='%2300e5ff' opacity='0.6'/%3E%3Ccircle cx='90' cy='90' r='1.6' fill='%23b05cff' opacity='0.6'/%3E%3C/svg%3E")`,
          backgroundSize: '120px 120px',
        }}
      />

      {/* Expanding ripple wave from center */}
      <div
        className="absolute w-[250vw] h-[250vw] rounded-full border border-accent/20 transition-all duration-[1150ms] ease-out pointer-events-none"
        style={{
          transform: `scale(${progress / 100})`,
          opacity: (100 - progress) / 100,
          background: `radial-gradient(circle, transparent 10%, rgba(var(--accent),0.10) 40%, rgba(var(--accent-2),0.06) 70%, transparent 100%)`,
        }}
      />

      <div className="relative flex items-center justify-center w-64 h-64 z-10">
        {/* Orbital rings — shared by both motifs */}
        <div className="absolute inset-0 rounded-full border border-dashed border-accent/30 animate-[spin_12s_linear_infinite]" />
        <div className="absolute inset-6 rounded-full border border-dashed border-accent/20 animate-[spin_8s_linear_infinite_reverse]" />

        {/* Radial progress ring */}
        <svg className="absolute w-44 h-44 z-20 pointer-events-none" viewBox="0 0 100 100">
          <circle cx="50" cy="50" r="42" stroke="currentColor" strokeWidth="2" fill="none" className="opacity-10 text-text" />
          <circle
            cx="50"
            cy="50"
            r="42"
            stroke="currentColor"
            strokeWidth="3.5"
            fill="none"
            strokeDasharray="263.89"
            strokeDashoffset={263.89 - (263.89 * progress) / 100}
            strokeLinecap="round"
            className="transition-all duration-150 ease-out text-accent dark:text-accent-2"
            transform="rotate(-90 50 50)"
          />
        </svg>

        {/* Day core: a wax-seal medallion, pressing down as progress advances */}
        <div className="absolute w-16 h-16 shape-seal bg-surface border-2 border-accent shadow-[0_0_40px_rgba(var(--accent),0.4)] flex items-center justify-center z-30 animate-seal-press dark:hidden">
          <span className="font-mono text-xs font-black tracking-widest text-accent">{progress}%</span>
        </div>

        {/* Night core: a pulsing neural node */}
        <div className="absolute w-14 h-14 rounded-full bg-surface border-2 border-accent-2 shadow-[0_0_40px_rgba(0,229,255,0.35)] hidden dark:flex items-center justify-center z-30 animate-[pulse_1.4s_ease-in-out_infinite]">
          <span className="font-mono text-xs font-black tracking-widest text-accent-2">{progress}%</span>
        </div>

        {/* Night-only scanline sweep across the core */}
        <div className="absolute inset-6 rounded-full overflow-hidden hidden dark:block pointer-events-none">
          <div className="absolute left-0 right-0 h-6 bg-gradient-to-b from-transparent via-accent-2/25 to-transparent animate-scanline" />
        </div>

        {/* Nodes spreading outward — day: brass ledger marks. Night: converging network nodes. */}
        {[0, 45, 90, 135, 180, 225, 270, 315].map((angle, idx) => {
          const distance = 40 + (progress / 100) * 110;
          const rad = (angle * Math.PI) / 180;
          const x = Math.cos(rad) * distance;
          const y = Math.sin(rad) * distance;

          return (
            <div key={idx} className="absolute transition-all duration-75 ease-out z-10" style={{ transform: `translate(${x}px, ${y}px)` }}>
              <div
                className="absolute bg-accent/20 dark:bg-accent-2/25 origin-left"
                style={{
                  width: `${distance}px`,
                  height: '1px',
                  transform: `rotate(${angle + 180}deg)`,
                  left: 0,
                  top: 0,
                }}
              />
              <div className="w-3 h-3 rounded-full bg-accent dark:bg-accent-2 border border-background shadow-[0_0_12px_rgba(var(--accent),0.8)] dark:shadow-[0_0_12px_rgba(0,229,255,0.8)] shrink-0" />
            </div>
          );
        })}
      </div>

      <div className="mt-8 text-center space-y-2 z-10">
        <h2 className="text-sm font-black tracking-[0.3em] uppercase text-accent dark:text-accent-2 drop-shadow">
          <span className="dark:hidden">Sealing The Ledger</span>
          <span className="hidden dark:inline">Synchronizing Neural Swarm</span>
        </h2>
        <p className="text-[10px] font-mono tracking-widest text-text-muted uppercase">
          <span className="dark:hidden">Binding Heritage Portfolio State...</span>
          <span className="hidden dark:inline">Establishing Encrypted Network Link...</span>
        </p>
      </div>
    </div>
  );
}

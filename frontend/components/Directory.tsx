"use client";

import Link from "next/link";

export interface DirectoryItem { name: string; href?: string; action?: () => void }
export interface DirectorySection { title: string; items: DirectoryItem[] }

export function Directory({
  open,
  onClose,
  sections,
}: {
  open: boolean;
  onClose: () => void;
  sections: DirectorySection[];
}) {
  return (
    <div
      className={`fixed inset-0 z-50 glass-3 transition-opacity duration-[var(--dur-enter)] ${
        open ? "opacity-100 pointer-events-auto" : "opacity-0 pointer-events-none"
      }`}
    >
      <button onClick={onClose} className="absolute top-6 right-6 font-mono text-text-muted hover:text-text">
        (close)
      </button>
      <nav className="h-full overflow-y-auto flex flex-col items-start justify-center gap-10 px-10 md:px-20 py-20">
        {sections.map((group) => (
          <div key={group.title}>
            <h2 className="text-[11px] uppercase tracking-[0.3em] text-text-muted font-mono mb-3">{group.title}</h2>
            <div className="flex flex-col gap-2">
              {group.items.map((item) =>
                item.href ? (
                  <Link
                    key={item.name}
                    href={item.href}
                    onClick={onClose}
                    className="font-display text-3xl hover:text-accent-2 transition-colors duration-[var(--dur-hover)]"
                  >
                    {item.name}
                  </Link>
                ) : (
                  <button
                    key={item.name}
                    onClick={() => { onClose(); item.action?.(); }}
                    className="font-display text-3xl text-left hover:text-accent-2 transition-colors duration-[var(--dur-hover)]"
                  >
                    {item.name}
                  </button>
                )
              )}
            </div>
          </div>
        ))}
      </nav>
    </div>
  );
}

"use client";

import { usePathname } from "next/navigation";
import { useEffect, useRef, useState } from "react";

// A slim, non-blocking themed progress cue for in-app navigation — the full
// BlockchainLoader splash only ever plays once, on cold boot (see AppLoaderWrapper).
export function RouteProgressBar() {
  const pathname = usePathname();
  const [visible, setVisible] = useState(false);
  const [width, setWidth] = useState(0);
  const isFirstRender = useRef(true);

  useEffect(() => {
    if (isFirstRender.current) {
      isFirstRender.current = false;
      return;
    }
    setVisible(true);
    setWidth(0);
    const growTimer = setTimeout(() => setWidth(82), 20);
    const finishTimer = setTimeout(() => setWidth(100), 260);
    const hideTimer = setTimeout(() => setVisible(false), 420);
    return () => {
      clearTimeout(growTimer);
      clearTimeout(finishTimer);
      clearTimeout(hideTimer);
    };
  }, [pathname]);

  return (
    <div
      className="fixed top-0 left-0 h-[3px] z-[9998] pointer-events-none bg-gradient-to-r from-accent via-accent-2 to-accent ease-out"
      style={{
        width: `${width}%`,
        opacity: visible ? 1 : 0,
        transitionProperty: "width, opacity",
        transitionDuration: visible ? "250ms" : "150ms",
        boxShadow: "0 0 8px rgba(var(--accent-2), 0.6)",
      }}
    />
  );
}

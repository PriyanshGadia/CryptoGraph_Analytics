"use client";

import { useState, useEffect } from "react";
import { ChevronUp } from "lucide-react";

export function ScrollToTop() {
  const [isVisible, setIsVisible] = useState(false);

  useEffect(() => {
    const toggleVisibility = () => {
      if (window.scrollY > 400) {
        setIsVisible(true);
      } else {
        setIsVisible(false);
      }
    };

    window.addEventListener("scroll", toggleVisibility);
    return () => window.removeEventListener("scroll", toggleVisibility);
  }, []);

  const scrollToTop = () => {
    window.scrollTo({
      top: 0,
      behavior: "smooth"
    });
  };

  return (
    <button
      onClick={scrollToTop}
      className={`fixed bottom-8 right-8 p-3 shape-facet-sm depth-bevel glass-1 hover:text-text border border-white/10 hover:border-accent shadow-xl transition-all duration-[var(--dur-enter)] ease-glide z-40 group ${isVisible ? 'opacity-100 translate-y-0' : 'opacity-0 translate-y-8 pointer-events-none'}`}
      aria-label="Scroll to top"
    >
      <ChevronUp size={24} className="group-hover:-translate-y-1 transition-transform duration-[var(--dur-hover)] ease-glide" />
    </button>
  );
}

"use client";

import { useEffect, useState } from "react";
import { Brain, Network, Layers, ShieldCheck, HelpCircle, X, ChevronRight, ChevronLeft, Sparkles } from "lucide-react";
import { usePathname } from "next/navigation";

interface Step {
  title: string;
  icon: React.ReactNode;
  content: string;
  targetPath: string;
  targetSelector?: string;
  colorClass: string;
}

export function OnboardingTour() {
  const pathname = usePathname();
  const [isOpen, setIsOpen] = useState(false);
  const [currentStep, setCurrentStep] = useState(0);

  useEffect(() => {
    // Automatically trigger if not completed
    const completed = localStorage.getItem("cryptograph-onboarding-completed");
    if (!completed) {
      setIsOpen(true);
    }

    // Listen to custom trigger event to re-run
    const handleReRun = () => {
      setCurrentStep(0);
      setIsOpen(true);
    };
    window.addEventListener("trigger-onboarding-tour", handleReRun);
    return () => window.removeEventListener("trigger-onboarding-tour", handleReRun);
  }, []);

  const steps: Step[] = [
    {
      title: "Interactive Neural Market Graph",
      icon: <Network className="text-accent w-10 h-10 drop-shadow-[0_0_10px_rgba(var(--accent),0.5)]" />,
      content: "Explore asset relationships visually. Nodes represent major cryptocurrencies; connecting edges show topological correlation calculated in real-time by our backend spatial-temporal engines.",
      targetPath: "/market",
      colorClass: "from-accent to-accent-2",
    },
    {
      title: "Predictive Analytics & AI Forecast",
      icon: <Brain className="text-warning w-10 h-10 drop-shadow-[0_0_10px_rgba(245,158,11,0.5)]" />,
      content: "Deep-dive into multi-factor predictions. Using spatial-temporal GCNs combined with local LSTMs, the platform calculates ensembled price paths, probability cones, and consensus targets.",
      targetPath: "/predictions",
      colorClass: "from-warning to-orange-500",
    },
    {
      title: "Neural Technical Screener",
      icon: <Layers className="text-info w-10 h-10 drop-shadow-[0_0_10px_rgba(6,182,212,0.5)]" />,
      content: "Filter and analyze technical indicators globally. Check live prices, cross-asset correlations, historical volatility regimes, and execute custom filter rules instantly.",
      targetPath: "/screener",
      colorClass: "from-info to-blue-500",
    },
    {
      title: "Simulated Swarm Portfolio & Ledger",
      icon: <ShieldCheck className="text-success w-10 h-10 drop-shadow-[0_0_10px_rgba(34,197,94,0.5)]" />,
      content: "Optimize assets using AI execution logic. Our simulated portfolio allocates weightings based on neural signals, tracks historic balances, and stamps cryptographic checksum logs for each transaction.",
      targetPath: "/portfolio",
      colorClass: "from-success to-emerald-500",
    },
  ];

  const handleNext = () => {
    if (currentStep < steps.length - 1) {
      setCurrentStep((prev) => prev + 1);
    } else {
      handleComplete();
    }
  };

  const handlePrev = () => {
    if (currentStep > 0) {
      setCurrentStep((prev) => prev - 1);
    }
  };

  const handleComplete = () => {
    localStorage.setItem("cryptograph-onboarding-completed", "true");
    setIsOpen(false);
  };

  if (!isOpen) return null;

  const activeStep = steps[currentStep];

  return (
    <div className="fixed inset-0 z-50 flex items-center justify-center p-4">
      {/* Backdrop */}
      <div 
        className="absolute inset-0 bg-black/70 backdrop-blur-md transition-opacity duration-300"
        onClick={handleComplete}
      />

      {/* Modal Dialog */}
      <div className="glass-3 rounded-2xl border border-text/10 max-w-lg w-full overflow-hidden relative z-10 shadow-2xl flex flex-col animate-in fade-in zoom-in-95 duration-200">
        
        {/* Glow Header */}
        <div className={`h-1.5 w-full bg-gradient-to-r ${activeStep.colorClass}`} />

        {/* Close Button */}
        <button 
          onClick={handleComplete}
          className="absolute top-4 right-4 text-text-muted hover:text-text transition-colors bg-text/5 hover:bg-text/10 p-1.5 rounded-full"
        >
          <X size={16} />
        </button>

        {/* Slide Content */}
        <div className="p-8 flex flex-col items-center text-center space-y-6">
          
          {/* Icon Circle */}
          <div className="p-4 rounded-full bg-white/5 border border-white/10 shadow-inner flex items-center justify-center relative">
            <div className="absolute inset-0 rounded-full bg-white/2 blur-md" />
            {activeStep.icon}
          </div>

          {/* Text Summary */}
          <div className="space-y-2">
            <span className="text-[9px] font-mono font-black tracking-[0.2em] text-accent uppercase flex items-center justify-center gap-1">
              <Sparkles size={10} className="animate-pulse" /> Platform Tour • Step {currentStep + 1} of {steps.length}
            </span>
            <h2 className="text-2xl font-black text-text tracking-tight font-sans">
              {activeStep.title}
            </h2>
          </div>

          <p className="text-text/80 text-sm font-light leading-relaxed tracking-wide max-w-sm">
            {activeStep.content}
          </p>

          {/* Navigation Prompt */}
          {pathname !== activeStep.targetPath && (
            <div className="text-[10px] font-mono text-text-muted bg-surface/50 border border-text/10 px-3 py-1.5 rounded-sm uppercase tracking-widest flex items-center gap-1.5 shadow-inner">
              <HelpCircle size={12} className="text-accent animate-bounce" /> Recommended View: <span className="text-text font-bold">{activeStep.targetPath}</span>
            </div>
          )}
        </div>

        {/* Footer controls */}
        <div className="border-t border-text/5 bg-surface/40 p-5 flex items-center justify-between">
          
          {/* Progress dots */}
          <div className="flex gap-2">
            {steps.map((_, i) => (
              <div 
                key={i}
                onClick={() => setCurrentStep(i)}
                className={`h-1.5 rounded-full transition-all duration-300 cursor-pointer ${
                  i === currentStep 
                    ? "w-6 bg-accent" 
                    : "w-1.5 bg-text-muted/30 hover:bg-text-muted/50"
                }`}
              />
            ))}
          </div>

          <div className="flex items-center gap-3">
            <button 
              onClick={handleComplete}
              className="text-[10px] uppercase font-bold text-text-muted hover:text-text tracking-widest px-3 py-1.5"
            >
              Skip
            </button>

            {currentStep > 0 && (
              <button 
                onClick={handlePrev}
                className="flex items-center gap-1 glass border-text/10 text-[10px] uppercase font-bold text-text hover:bg-text/5 tracking-widest px-3.5 py-2 rounded-sm transition-all"
              >
                <ChevronLeft size={12} /> Prev
              </button>
            )}

            <button 
              onClick={handleNext}
              className="flex items-center gap-1 bg-accent hover:bg-accent/90 text-white text-[10px] uppercase font-black tracking-widest px-4 py-2 rounded-sm shadow-[0_0_15px_rgba(var(--accent),0.3)] transition-all hover:scale-105"
            >
              {currentStep === steps.length - 1 ? "Get Started" : "Next"} <ChevronRight size={12} />
            </button>
          </div>

        </div>

      </div>
    </div>
  );
}

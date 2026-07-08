import { create } from "zustand";
import axios from "axios";

export type Currency = "USD" | "EUR" | "GBP" | "JPY" | "AUD" | "CAD" | "CHF" | "CNY" | "INR";
export type PerformanceMode = "full" | "lite";

export const CURRENCY_SYMBOLS: Record<Currency, string> = {
  USD: "$", EUR: "€", GBP: "£", JPY: "¥", AUD: "A$", CAD: "C$", CHF: "CHF", CNY: "¥", INR: "₹"
};

interface AppState {
  // Currency Settings
  currency: Currency;
  exchangeRate: number;
  ratesCache: Record<string, number>;
  setCurrency: (currency: Currency) => void;
  fetchRates: () => Promise<void>;

  // Performance Settings
  performanceMode: PerformanceMode;
  setPerformanceMode: (mode: PerformanceMode) => void;
  initializeSettings: () => void;

  // WebSocket connection statuses
  wsStatuses: Record<string, "connecting" | "connected" | "disconnected">;
  updateWsStatus: (endpoint: string, status: "connecting" | "connected" | "disconnected") => void;
}

export const useAppStore = create<AppState>((set, get) => ({
  currency: "USD",
  exchangeRate: 1.0,
  ratesCache: { USD: 1.0 },
  performanceMode: "full",
  wsStatuses: {},

  setCurrency: (c: Currency) => {
    localStorage.setItem("preferredCurrency", c);
    const rate = get().ratesCache[c] || 1.0;
    set({ currency: c, exchangeRate: rate });
  },

  fetchRates: async () => {
    try {
      const res = await axios.get("https://open.er-api.com/v6/latest/USD");
      if (res.data && res.data.rates) {
        const rates = res.data.rates;
        const currentCurrency = get().currency;
        set({
          ratesCache: rates,
          exchangeRate: rates[currentCurrency] || 1.0,
        });
      }
    } catch (err) {
      console.error("Failed to fetch exchange rates", err);
    }
  },

  setPerformanceMode: (mode: PerformanceMode) => {
    localStorage.setItem("performance-mode", mode);
    if (typeof document !== "undefined") {
      document.documentElement.setAttribute("data-performance", mode);
    }
    set({ performanceMode: mode });
  },

  initializeSettings: () => {
    if (typeof window === "undefined") return;

    // Load Currency Preference
    const savedCurrency = localStorage.getItem("preferredCurrency") as Currency;
    if (savedCurrency && CURRENCY_SYMBOLS[savedCurrency]) {
      set({ currency: savedCurrency });
    }

    // Load Performance Preference
    const savedPerf = localStorage.getItem("performance-mode") as PerformanceMode | null;
    if (savedPerf === "full" || savedPerf === "lite") {
      set({ performanceMode: savedPerf });
      document.documentElement.setAttribute("data-performance", savedPerf);
    } else {
      const prefersReduced = window.matchMedia("(prefers-reduced-motion: reduce)").matches;
      const initialMode = prefersReduced ? "lite" : "full";
      set({ performanceMode: initialMode });
      document.documentElement.setAttribute("data-performance", initialMode);
    }

    // Initial rates fetch
    get().fetchRates();
  },

  updateWsStatus: (endpoint: string, status: "connecting" | "connected" | "disconnected") => {
    set((state) => ({
      wsStatuses: {
        ...state.wsStatuses,
        [endpoint]: status,
      },
    }));
  },
}));

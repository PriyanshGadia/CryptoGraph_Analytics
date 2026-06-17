"use client";

import React, { createContext, useContext, useState, useEffect } from "react";
import axios from "axios";

// Default to USD
export type Currency = "USD" | "EUR" | "GBP" | "JPY" | "AUD" | "CAD" | "CHF" | "CNY" | "INR";

interface CurrencyContextType {
  currency: Currency;
  setCurrency: (c: Currency) => void;
  exchangeRate: number; // Multiplier from USD
  formatPrice: (priceInUsd: number, decimals?: number) => string;
}

const CurrencyContext = createContext<CurrencyContextType | undefined>(undefined);

export const CURRENCY_SYMBOLS: Record<Currency, string> = {
  USD: "$", EUR: "€", GBP: "£", JPY: "¥", AUD: "A$", CAD: "C$", CHF: "CHF", CNY: "¥", INR: "₹"
};

export const CurrencyProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [currency, setCurrency] = useState<Currency>("USD");
  const [exchangeRate, setExchangeRate] = useState<number>(1.0);
  const [ratesCache, setRatesCache] = useState<Record<string, number>>({ USD: 1.0 });

  // Load saved currency preference from local storage on mount
  useEffect(() => {
    const saved = localStorage.getItem("preferredCurrency") as Currency;
    if (saved && CURRENCY_SYMBOLS[saved]) {
      setCurrency(saved);
    }

    // Fetch live rates from a free API
    const fetchRates = async () => {
      try {
        const res = await axios.get("https://open.er-api.com/v6/latest/USD");
        if (res.data && res.data.rates) {
          setRatesCache(res.data.rates);
          if (saved && res.data.rates[saved]) {
            setExchangeRate(res.data.rates[saved]);
          }
        }
      } catch (err) {
        console.error("Failed to fetch exchange rates", err);
      }
    };
    fetchRates();
  }, []);

  // Update exchange rate when currency changes
  const handleSetCurrency = (c: Currency) => {
    setCurrency(c);
    localStorage.setItem("preferredCurrency", c);
    if (ratesCache[c]) {
      setExchangeRate(ratesCache[c]);
    }
  };

  const formatPrice = (priceInUsd: number, decimals?: number) => {
    if (priceInUsd === null || priceInUsd === undefined) return `${CURRENCY_SYMBOLS[currency]}0.00`;
    
    let finalDecimals = decimals !== undefined ? decimals : 2;
    const converted = priceInUsd * exchangeRate;
    
    if (decimals === undefined) { 
      if (converted < 0.01) finalDecimals = 6;
      else if (converted < 1) finalDecimals = 4;
    }

    return `${CURRENCY_SYMBOLS[currency]}${converted.toLocaleString(undefined, {
      minimumFractionDigits: finalDecimals,
      maximumFractionDigits: finalDecimals
    })}`;
  };

  return (
    <CurrencyContext.Provider value={{ currency, setCurrency: handleSetCurrency, exchangeRate, formatPrice }}>
      {children}
    </CurrencyContext.Provider>
  );
};

export const useCurrency = () => {
  const context = useContext(CurrencyContext);
  if (!context) {
    throw new Error("useCurrency must be used within a CurrencyProvider");
  }
  return context;
};

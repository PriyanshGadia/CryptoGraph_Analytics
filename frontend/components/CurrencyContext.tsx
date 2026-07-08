"use client";

import React, { createContext, useContext, useEffect } from "react";
import { useAppStore, Currency, CURRENCY_SYMBOLS } from "@/lib/store";

export type { Currency };
export { CURRENCY_SYMBOLS };

interface CurrencyContextType {
  currency: Currency;
  setCurrency: (c: Currency) => void;
  exchangeRate: number; // Multiplier from USD
  formatPrice: (priceInUsd: number, decimals?: number) => string;
}

const CurrencyContext = createContext<CurrencyContextType | undefined>(undefined);

export const CurrencyProvider: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const currency = useAppStore((state) => state.currency);
  const setCurrency = useAppStore((state) => state.setCurrency);
  const exchangeRate = useAppStore((state) => state.exchangeRate);
  const initializeSettings = useAppStore((state) => state.initializeSettings);

  useEffect(() => {
    initializeSettings();
  }, [initializeSettings]);

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
    <CurrencyContext.Provider value={{ currency, setCurrency, exchangeRate, formatPrice }}>
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

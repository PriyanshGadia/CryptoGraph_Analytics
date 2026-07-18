"use client";

import React, { useState, useEffect } from 'react';
import { BlockchainLoader } from './BlockchainLoader';

export const AppLoaderWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [loading, setLoading] = useState(true);

  useEffect(() => {
    const hasLoaded = sessionStorage.getItem("app_loaded");
    if (hasLoaded) {
      setLoading(false);
    }
  }, []);

  const handleComplete = () => {
    sessionStorage.setItem("app_loaded", "true");
    setLoading(false);
  };

  if (loading) {
    return <BlockchainLoader onComplete={handleComplete} />;
  }

  return <>{children}</>;
};

'use client';

import React, { useState, useEffect } from 'react';
import { usePathname } from 'next/navigation';
import { BlockchainLoader } from './BlockchainLoader';

export const AppLoaderWrapper: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const [loading, setLoading] = useState(true);
  const [isFirstLoad, setIsFirstLoad] = useState(true);
  const pathname = usePathname();

  useEffect(() => {
    if (!isFirstLoad) {
      setLoading(true);
    } else {
      setIsFirstLoad(false);
    }
  }, [pathname]);

  return (
    <>
      {children}
      {loading && (
        <BlockchainLoader 
          duration={isFirstLoad ? 1150 : 600} 
          onComplete={() => setLoading(false)} 
        />
      )}
    </>
  );
};

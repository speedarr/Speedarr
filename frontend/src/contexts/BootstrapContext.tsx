import React, { createContext, useContext, useEffect, useState, ReactNode } from 'react';
import { apiClient } from '@/api/client';
import type { BootstrapResponse } from '@/types';

interface BootstrapContextType {
  data: BootstrapResponse | null;
  isLoading: boolean;
  isError: boolean;
}

const BootstrapContext = createContext<BootstrapContextType | undefined>(undefined);

export const BootstrapProvider: React.FC<{ children: ReactNode }> = ({ children }) => {
  const [data, setData] = useState<BootstrapResponse | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isError, setIsError] = useState(false);

  useEffect(() => {
    let cancelled = false;
    apiClient
      .getBootstrap()
      .then((res) => {
        if (!cancelled) {
          setData(res);
          setIsError(false);
        }
      })
      .catch(() => {
        if (!cancelled) {
          setData(null);
          setIsError(true);
        }
      })
      .finally(() => {
        if (!cancelled) setIsLoading(false);
      });
    return () => {
      cancelled = true;
    };
  }, []);

  return (
    <BootstrapContext.Provider value={{ data, isLoading, isError }}>
      {children}
    </BootstrapContext.Provider>
  );
};

export const useBootstrap = () => {
  const context = useContext(BootstrapContext);
  if (context === undefined) {
    throw new Error('useBootstrap must be used within a BootstrapProvider');
  }
  return context;
};

import { useState, useCallback } from 'react';

/**
 * Hook to track unsaved changes by comparing original and current config.
 * Uses deep comparison via JSON.stringify.
 */
export function useUnsavedChanges<T>(initialOriginal: T | null = null) {
  const [originalConfig, setOriginalConfig] = useState<T | null>(initialOriginal);

  const hasUnsavedChanges = useCallback(
    (currentConfig: T | null): boolean => {
      if (originalConfig === null || currentConfig === null) {
        return false;
      }
      return JSON.stringify(originalConfig) !== JSON.stringify(currentConfig);
    },
    [originalConfig]
  );

  const resetOriginal = useCallback((config: T) => {
    setOriginalConfig(JSON.parse(JSON.stringify(config)));
  }, []);

  const discardChanges = useCallback((): T | null => {
    return originalConfig ? JSON.parse(JSON.stringify(originalConfig)) : null;
  }, [originalConfig]);

  return {
    originalConfig,
    hasUnsavedChanges,
    resetOriginal,
    discardChanges,
  };
}

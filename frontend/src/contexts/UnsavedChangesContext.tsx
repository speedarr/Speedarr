import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode, RefObject, useRef } from 'react';

interface TabState {
  isDirty: boolean;
  saveButtonRef: RefObject<HTMLButtonElement> | null;
  onSave: (() => Promise<void>) | null;
  onDiscard: (() => void) | null;
}

interface UnsavedChangesContextType {
  registerTab: (
    tabId: string,
    isDirty: boolean,
    saveButtonRef: RefObject<HTMLButtonElement> | null,
    onSave: (() => Promise<void>) | null,
    onDiscard: (() => void) | null
  ) => void;
  unregisterTab: (tabId: string) => void;
  hasDirtyTabs: boolean;
  getDirtyTabs: () => string[];
  currentDirtyTab: string | null;
  triggerWarning: () => void;
  dismissWarning: () => void;
  isWarningVisible: boolean;
  handleSaveAndProceed: () => Promise<void>;
  handleDiscardAndProceed: () => void;
  pendingTabChange: string | null;
  setPendingTabChange: (tab: string | null) => void;
  pendingNavigation: string | null;
  setPendingNavigation: (path: string | null) => void;
  setNavigateCallback: (cb: ((path: string) => void) | null) => void;
}

const UnsavedChangesContext = createContext<UnsavedChangesContextType | null>(null);

export const useUnsavedChangesContext = () => {
  const context = useContext(UnsavedChangesContext);
  if (!context) {
    throw new Error('useUnsavedChangesContext must be used within an UnsavedChangesProvider');
  }
  return context;
};

interface UnsavedChangesProviderProps {
  children: ReactNode;
}

export const UnsavedChangesProvider: React.FC<UnsavedChangesProviderProps> = ({ children }) => {
  const [tabStates, setTabStates] = useState<Record<string, TabState>>({});
  const [isWarningVisible, setIsWarningVisible] = useState(false);
  const [pendingTabChange, setPendingTabChange] = useState<string | null>(null);
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);
  const navigateCallbackRef = useRef<((path: string) => void) | null>(null);

  const setNavigateCallback = useCallback((cb: ((path: string) => void) | null) => {
    navigateCallbackRef.current = cb;
  }, []);

  const registerTab = useCallback(
    (
      tabId: string,
      isDirty: boolean,
      saveButtonRef: RefObject<HTMLButtonElement> | null,
      onSave: (() => Promise<void>) | null,
      onDiscard: (() => void) | null
    ) => {
      setTabStates((prev) => ({
        ...prev,
        [tabId]: { isDirty, saveButtonRef, onSave, onDiscard },
      }));
    },
    []
  );

  const unregisterTab = useCallback((tabId: string) => {
    setTabStates((prev) => {
      const newState = { ...prev };
      delete newState[tabId];
      return newState;
    });
  }, []);

  const getDirtyTabs = useCallback(() => {
    return Object.entries(tabStates)
      .filter(([_, state]) => state.isDirty)
      .map(([tabId]) => tabId);
  }, [tabStates]);

  const hasDirtyTabs = Object.values(tabStates).some((state) => state.isDirty);

  const currentDirtyTab = Object.entries(tabStates).find(([_, state]) => state.isDirty)?.[0] || null;

  const triggerWarning = useCallback(() => {
    const dirtyTab = Object.entries(tabStates).find(([_, state]) => state.isDirty);
    if (dirtyTab) {
      const [_, state] = dirtyTab;
      if (state.saveButtonRef?.current) {
        state.saveButtonRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
      }
    }
    setIsWarningVisible(true);
  }, [tabStates]);

  const dismissWarning = useCallback(() => {
    setIsWarningVisible(false);
    setPendingTabChange(null);
    setPendingNavigation(null);
  }, []);

  const handleSaveAndProceed = useCallback(async () => {
    const dirtyTab = Object.entries(tabStates).find(([_, state]) => state.isDirty);
    if (dirtyTab) {
      const [_, state] = dirtyTab;
      if (state.onSave) {
        await state.onSave();
      }
    }
    setIsWarningVisible(false);

    // Wait for React to flush state updates, then trigger navigation
    requestAnimationFrame(() => {
      if (pendingNavigation && navigateCallbackRef.current) {
        navigateCallbackRef.current(pendingNavigation);
        setPendingNavigation(null);
      }
    });
  }, [tabStates, pendingNavigation]);

  const handleDiscardAndProceed = useCallback(() => {
    const dirtyTab = Object.entries(tabStates).find(([_, state]) => state.isDirty);
    if (dirtyTab) {
      const [_, state] = dirtyTab;
      if (state.onDiscard) {
        state.onDiscard();
      }
    }
    setIsWarningVisible(false);
  }, [tabStates]);

  // Browser beforeunload handler
  useEffect(() => {
    const handleBeforeUnload = (e: BeforeUnloadEvent) => {
      if (hasDirtyTabs) {
        e.preventDefault();
        e.returnValue = '';
        return '';
      }
    };

    window.addEventListener('beforeunload', handleBeforeUnload);
    return () => window.removeEventListener('beforeunload', handleBeforeUnload);
  }, [hasDirtyTabs]);

  return (
    <UnsavedChangesContext.Provider
      value={{
        registerTab,
        unregisterTab,
        hasDirtyTabs,
        getDirtyTabs,
        currentDirtyTab,
        triggerWarning,
        dismissWarning,
        isWarningVisible,
        handleSaveAndProceed,
        handleDiscardAndProceed,
        pendingTabChange,
        setPendingTabChange,
        pendingNavigation,
        setPendingNavigation,
        setNavigateCallback,
      }}
    >
      {children}
    </UnsavedChangesContext.Provider>
  );
};

import React, { createContext, useContext, useState, useCallback, useEffect, ReactNode, RefObject } from 'react';

interface TabState {
  isDirty: boolean;
  saveButtonRef: RefObject<HTMLButtonElement> | null;
  onSave: (() => Promise<boolean>) | null;
  onDiscard: (() => void) | null;
}

interface UnsavedChangesContextType {
  registerTab: (
    tabId: string,
    isDirty: boolean,
    saveButtonRef: RefObject<HTMLButtonElement> | null,
    onSave: (() => Promise<boolean>) | null,
    onDiscard: (() => void) | null
  ) => void;
  unregisterTab: (tabId: string) => void;
  hasDirtyTabs: boolean;
  getDirtyTabs: () => string[];
  currentDirtyTab: string | null;
  triggerWarning: () => void;
  dismissWarning: () => void;
  isWarningVisible: boolean;
  isSaving: boolean;
  handleSaveAndProceed: () => Promise<void>;
  handleDiscardAndProceed: () => void;
  pendingTabChange: string | null;
  setPendingTabChange: (tab: string | null) => void;
  pendingNavigation: string | null;
  setPendingNavigation: (path: string | null) => void;
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

// Brings a panel's Save button, and the error alert beside it, into view.
const scrollToSave = (state: TabState) => {
  state.saveButtonRef?.current?.scrollIntoView({ behavior: 'smooth', block: 'center' });
};

export const UnsavedChangesProvider: React.FC<UnsavedChangesProviderProps> = ({ children }) => {
  const [tabStates, setTabStates] = useState<Record<string, TabState>>({});
  const [isWarningVisible, setIsWarningVisible] = useState(false);
  const [isSaving, setIsSaving] = useState(false);
  const [pendingTabChange, setPendingTabChange] = useState<string | null>(null);
  const [pendingNavigation, setPendingNavigation] = useState<string | null>(null);

  const registerTab = useCallback(
    (
      tabId: string,
      isDirty: boolean,
      saveButtonRef: RefObject<HTMLButtonElement> | null,
      onSave: (() => Promise<boolean>) | null,
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
    const dirtyTab = Object.values(tabStates).find((state) => state.isDirty);
    if (dirtyTab) scrollToSave(dirtyTab);
    setIsWarningVisible(true);
  }, [tabStates]);

  const dismissWarning = useCallback(() => {
    setIsWarningVisible(false);
    setPendingTabChange(null);
    setPendingNavigation(null);
  }, []);

  // Save Now. Runs every dirty panel's save in registration order and proceeds only when all of
  // them report success (audit T5-3). Otherwise the banner stays, the pending destination stays
  // armed and the first failing panel's Save button, with its error alert, is brought into view
  // (audit T5-2). Every dirty panel is attempted even after a failure, so a retry has less left
  // to save. The navigation itself happens in the Dashboard and Settings effects once nothing is
  // dirty and the banner is hidden.
  const handleSaveAndProceed = useCallback(async () => {
    const dirtyTabs = Object.values(tabStates).filter((state) => state.isDirty);
    setIsSaving(true);
    let firstFailed: TabState | null = null;
    try {
      for (const state of dirtyTabs) {
        let saved = false;
        try {
          saved = state.onSave ? await state.onSave() : false;
        } catch {
          saved = false;
        }
        if (!saved && !firstFailed) firstFailed = state;
      }
    } finally {
      setIsSaving(false);
    }
    if (firstFailed) {
      scrollToSave(firstFailed);
      return;
    }
    setIsWarningVisible(false);
  }, [tabStates]);

  const handleDiscardAndProceed = useCallback(() => {
    for (const state of Object.values(tabStates)) {
      if (state.isDirty && state.onDiscard) state.onDiscard();
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
        isSaving,
        handleSaveAndProceed,
        handleDiscardAndProceed,
        pendingTabChange,
        setPendingTabChange,
        pendingNavigation,
        setPendingNavigation,
      }}
    >
      {children}
    </UnsavedChangesContext.Provider>
  );
};

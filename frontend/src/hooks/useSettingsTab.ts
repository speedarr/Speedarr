import { useEffect, useLayoutEffect, useRef, type RefObject } from 'react';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

/**
 * Registers a settings panel with the unsaved-changes banner.
 *
 * The banner keeps the callbacks it is handed until the dirty flag flips, so a callback that
 * closes over one render's state would save the form as it was at the first edit and drop every
 * later one (audit T5-1). The latest onSave/onDiscard live in a ref refreshed after every commit,
 * and the banner gets stable wrappers that call through it, so Save Now always runs the current
 * render's save. The registration itself still changes only when the dirty flag does.
 */
export function useSettingsTab(
  tabId: string,
  isDirty: boolean,
  saveButtonRef: RefObject<HTMLButtonElement>,
  onSave: () => Promise<void>,
  onDiscard: () => void,
): void {
  const { registerTab, unregisterTab } = useUnsavedChangesContext();
  const latest = useRef({ onSave, onDiscard });

  useLayoutEffect(() => {
    latest.current = { onSave, onDiscard };
  });

  useEffect(() => {
    registerTab(
      tabId,
      isDirty,
      saveButtonRef,
      () => latest.current.onSave(),
      () => latest.current.onDiscard(),
    );
    return () => unregisterTab(tabId);
  }, [tabId, isDirty, saveButtonRef, registerTab, unregisterTab]);
}

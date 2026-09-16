import { useCallback, useState } from 'react';
import {
  DEFAULT_LAYOUT,
  LAYOUT_STORAGE_KEY,
  isDefaultLayout,
  movePanel,
  parseLayout,
  serializeLayout,
  togglePanel,
  type DashboardLayout,
  type MoveDirection,
  type PanelId,
} from '@/lib/dashboardLayout';

export interface UseDashboardLayout {
  layout: DashboardLayout;
  /** Move `id` one visible step; `visible` is the list of panels the viewer can currently see. */
  move: (id: PanelId, direction: MoveDirection, visible: readonly PanelId[]) => void;
  toggle: (id: PanelId) => void;
  reset: () => void;
  isDefault: boolean;
}

const readLayout = (): DashboardLayout => {
  try {
    return parseLayout(localStorage.getItem(LAYOUT_STORAGE_KEY));
  } catch (e) {
    console.error('Failed to load dashboard layout:', e);
    return DEFAULT_LAYOUT;
  }
};

const writeLayout = (layout: DashboardLayout): void => {
  try {
    localStorage.setItem(LAYOUT_STORAGE_KEY, serializeLayout(layout));
  } catch (e) {
    console.error('Failed to save dashboard layout:', e);
  }
};

/**
 * Dashboard panel order and collapsed state, persisted per browser (issue #86).
 * Writes happen in the action handlers, not in an effect, so mounting writes nothing and a
 * no-op move (same object back from movePanel) writes nothing either.
 */
export function useDashboardLayout(): UseDashboardLayout {
  const [layout, setLayout] = useState<DashboardLayout>(readLayout);

  const apply = useCallback(
    (next: DashboardLayout) => {
      if (next === layout) return;
      writeLayout(next);
      setLayout(next);
    },
    [layout],
  );

  const move = useCallback(
    (id: PanelId, direction: MoveDirection, visible: readonly PanelId[]) =>
      apply(movePanel(layout, id, direction, visible)),
    [layout, apply],
  );
  const toggle = useCallback((id: PanelId) => apply(togglePanel(layout, id)), [layout, apply]);
  const reset = useCallback(() => apply(DEFAULT_LAYOUT), [apply]);

  return { layout, move, toggle, reset, isDefault: isDefaultLayout(layout) };
}

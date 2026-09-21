/**
 * Dashboard panel layout state (issue #86): pure data in, pure data out.
 * Persistence lives in hooks/useDashboardLayout.ts; rendering in pages/Home.tsx.
 */

export type PanelId = 'overview' | 'temporary-limits' | 'bandwidth-chart' | 'stream-count' | 'active-streams';

/** Default order, top to bottom. Also the set of valid ids. */
export const PANEL_IDS: readonly PanelId[] = [
  'overview',
  'temporary-limits',
  'bandwidth-chart',
  'stream-count',
  'active-streams',
];

export interface DashboardLayout {
  order: PanelId[];
  collapsed: PanelId[];
}

export const DEFAULT_LAYOUT: DashboardLayout = { order: [...PANEL_IDS], collapsed: [] };

export const LAYOUT_STORAGE_KEY = 'speedarr_dashboard_layout';

export type MoveDirection = 'up' | 'down';

const isPanelId = (value: unknown): value is PanelId =>
  typeof value === 'string' && (PANEL_IDS as readonly string[]).includes(value);

/**
 * Move `id` one visible step up or down. `visible` lists the panels the viewer can see;
 * hidden panels between `id` and its visible neighbour are skipped and keep their relative
 * order (a plain adjacent swap with a hidden panel would look like a dead click).
 * Returns the same object when nothing can move.
 */
export function movePanel(
  layout: DashboardLayout,
  id: PanelId,
  direction: MoveDirection,
  visible: readonly PanelId[] = layout.order,
): DashboardLayout {
  const from = layout.order.indexOf(id);
  if (from === -1) return layout;
  const step = direction === 'up' ? -1 : 1;
  let to = from + step;
  while (to >= 0 && to < layout.order.length && !visible.includes(layout.order[to])) {
    to += step;
  }
  if (to < 0 || to >= layout.order.length) return layout;
  const order = [...layout.order];
  order.splice(from, 1);
  order.splice(to, 0, id);
  return { ...layout, order };
}

export function togglePanel(layout: DashboardLayout, id: PanelId): DashboardLayout {
  const collapsed = layout.collapsed.includes(id)
    ? layout.collapsed.filter((c) => c !== id)
    : [...layout.collapsed, id];
  return { ...layout, collapsed };
}

export function isDefaultLayout(layout: DashboardLayout): boolean {
  return (
    layout.collapsed.length === 0 &&
    layout.order.length === PANEL_IDS.length &&
    layout.order.every((id, i) => id === PANEL_IDS[i])
  );
}

export function serializeLayout(layout: DashboardLayout): string {
  return JSON.stringify({ v: 1, order: layout.order, collapsed: layout.collapsed });
}

/** Valid ids only, first occurrence wins; anything that is not an array gives []. */
const uniqueIds = (value: unknown): PanelId[] => {
  if (!Array.isArray(value)) return [];
  const out: PanelId[] = [];
  for (const v of value) {
    if (isPanelId(v) && !out.includes(v)) out.push(v);
  }
  return out;
};

/**
 * Tolerant parser for the stored payload. Never throws. Unknown ids are dropped, missing ids
 * are appended in default order, so a panel added in a future version needs no migration.
 */
export function parseLayout(raw: string | null): DashboardLayout {
  if (raw === null) return DEFAULT_LAYOUT;
  let parsed: unknown;
  try {
    parsed = JSON.parse(raw);
  } catch {
    return DEFAULT_LAYOUT;
  }
  if (typeof parsed !== 'object' || parsed === null || Array.isArray(parsed)) return DEFAULT_LAYOUT;
  const obj = parsed as { v?: unknown; order?: unknown; collapsed?: unknown };
  if (obj.v !== 1) return DEFAULT_LAYOUT;
  const order = uniqueIds(obj.order);
  for (const id of PANEL_IDS) {
    if (!order.includes(id)) order.push(id);
  }
  return { order, collapsed: uniqueIds(obj.collapsed) };
}

// Pure helpers for building per-client-id chart series descriptors and
// resolving collision-free colors. No React, no I/O — kept pure for review
// (the project has no JS unit-test runner; verified via tsc + integration).

export interface ChartSeriesDescriptor {
  id: string;
  type: string;
  name: string;
  color: string;
  supportsUpload: boolean;
}

// Fallback palette for resolving color collisions among same-type clients and
// for historical/removed series with no configured color.
export const SERIES_PALETTE = [
  '#3b82f6', '#f59e0b', '#10b981', '#ec4899', '#06b6d4',
  '#84cc16', '#a855f7', '#ef4444', '#14b8a6', '#f97316',
];

// Per-type defaults for historical (type-keyed) or unknown series.
const TYPE_DEFAULTS: Record<string, { name: string; color: string }> = {
  qbittorrent: { name: 'qBittorrent', color: '#3b82f6' },
  sabnzbd: { name: 'SABnzbd', color: '#facc15' },
  nzbget: { name: 'NZBGet', color: '#22c55e' },
  transmission: { name: 'Transmission', color: '#ef4444' },
  deluge: { name: 'Deluge', color: '#8b5cf6' },
};

/**
 * Merge current clients (from /status, keyed by id) with historical-only series
 * ids from chart-data. Current clients keep their given order and metadata;
 * historical-only ids (removed clients or legacy type-merged ids) are appended
 * and resolved against per-type defaults, falling back to the bare id/grey.
 */
export function buildChartSeries(
  currentClients: ChartSeriesDescriptor[],
  historicalSeries: { id: string; type: string }[],
): ChartSeriesDescriptor[] {
  const byId = new Map<string, ChartSeriesDescriptor>();
  for (const c of currentClients) {
    byId.set(c.id, c);
  }
  for (const h of historicalSeries) {
    if (byId.has(h.id)) continue;
    const def = TYPE_DEFAULTS[h.type];
    byId.set(h.id, {
      id: h.id,
      type: h.type,
      name: def ? def.name : h.id,
      color: def ? def.color : '#888888',
      supportsUpload: false,
    });
  }
  return Array.from(byId.values());
}

// Raw point-field suffixes that exist per series id (and, for pre-fix rows, per type).
const FOLD_SUFFIXES = ['_speed', '_upload_speed', '_download_limit', '_upload_limit'];

/**
 * Map each client TYPE to the first current client id of that type (by order).
 * Used to fold pre-fix, type-keyed history into the matching current client so
 * a single-instance client renders as one continuous series across the storage
 * cutover instead of a duplicate legacy series.
 */
export function computeLegacyFoldMap(
  currentClients: { id: string; type: string }[],
): Record<string, string> {
  const map: Record<string, string> = {};
  for (const c of currentClients) {
    if (!(c.type in map)) map[c.type] = c.id;
  }
  return map;
}

/**
 * Fold legacy type-keyed point fields (`<type>_speed`, …) into the matching
 * current client's id-keyed fields (`<id>_speed`, …) per foldMap, then drop the
 * legacy keys. New rows (which only carry id-keyed fields) pass through
 * unchanged; only rows that actually contain a legacy key are copied. The
 * id-keyed value wins when both are present, so new data is never overwritten.
 */
export function foldLegacyPoints<T extends Record<string, unknown>>(
  points: T[],
  foldMap: Record<string, string>,
): T[] {
  const types = Object.keys(foldMap);
  if (types.length === 0) return points;
  return points.map((p) => {
    let copy: Record<string, unknown> | null = null;
    for (const type of types) {
      const targetId = foldMap[type];
      if (targetId === type) continue;
      for (const suffix of FOLD_SUFFIXES) {
        const legacyKey = type + suffix;
        if (legacyKey in p) {
          if (copy === null) copy = { ...p };
          const targetKey = targetId + suffix;
          if (copy[targetKey] === undefined || copy[targetKey] === null) {
            copy[targetKey] = (p as Record<string, unknown>)[legacyKey];
          }
          delete copy[legacyKey];
        }
      }
    }
    return (copy ?? p) as T;
  });
}

/**
 * Drop historical series entries that fold into a current client: a bare
 * type-keyed legacy id (id === type) whose type has a current client. Removed
 * individual clients (id !== type) and fully-removed types (no current client)
 * are kept so their history still shows.
 */
export function dropFoldedHistoricalSeries(
  historicalSeries: { id: string; type: string }[],
  foldMap: Record<string, string>,
): { id: string; type: string }[] {
  return historicalSeries.filter((h) => !(h.id === h.type && foldMap[h.type]));
}

/**
 * Resolve display colors so no two series share a color. Each descriptor keeps
 * its configured color when still unused; collisions are reassigned to the next
 * unused palette color, deterministically by input order. Returns an id->color map.
 */
export function resolveSeriesColors(
  descriptors: ChartSeriesDescriptor[],
): Record<string, string> {
  const used = new Set<string>();
  const result: Record<string, string> = {};
  for (const d of descriptors) {
    let color = d.color;
    if (used.has(color.toLowerCase())) {
      color = SERIES_PALETTE.find((p) => !used.has(p.toLowerCase())) ?? color;
    }
    used.add(color.toLowerCase());
    result[d.id] = color;
  }
  return result;
}

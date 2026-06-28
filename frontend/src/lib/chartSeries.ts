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

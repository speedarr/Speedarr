import { describe, it, expect } from 'vitest';
import {
  DEFAULT_LAYOUT,
  PANEL_IDS,
  isDefaultLayout,
  movePanel,
  parseLayout,
  serializeLayout,
  togglePanel,
  type DashboardLayout,
} from './dashboardLayout';

const layout = (order: DashboardLayout['order'], collapsed: DashboardLayout['collapsed'] = []): DashboardLayout =>
  ({ order, collapsed });

describe('DEFAULT_LAYOUT', () => {
  it("is today's dashboard order with nothing collapsed", () => {
    expect(DEFAULT_LAYOUT.order).toEqual([
      'overview', 'temporary-limits', 'bandwidth-chart', 'stream-count', 'active-streams',
    ]);
    expect(DEFAULT_LAYOUT.collapsed).toEqual([]);
    expect(isDefaultLayout(DEFAULT_LAYOUT)).toBe(true);
  });
});

describe('movePanel', () => {
  it('moves a panel up past its neighbour', () => {
    const next = movePanel(DEFAULT_LAYOUT, 'bandwidth-chart', 'up');
    expect(next.order).toEqual(['overview', 'bandwidth-chart', 'temporary-limits', 'stream-count', 'active-streams']);
    expect(next.collapsed).toEqual([]);
  });

  it('moves a panel down past its neighbour', () => {
    const next = movePanel(DEFAULT_LAYOUT, 'bandwidth-chart', 'down');
    expect(next.order).toEqual(['overview', 'temporary-limits', 'stream-count', 'bandwidth-chart', 'active-streams']);
  });

  it('returns the same layout object at the top, at the bottom, and for an unknown id', () => {
    expect(movePanel(DEFAULT_LAYOUT, 'overview', 'up')).toBe(DEFAULT_LAYOUT);
    expect(movePanel(DEFAULT_LAYOUT, 'active-streams', 'down')).toBe(DEFAULT_LAYOUT);
    const partial = layout(['overview', 'bandwidth-chart']);
    expect(movePanel(partial, 'stream-count', 'up')).toBe(partial);
  });

  it('does not mutate its input', () => {
    const before = layout([...PANEL_IDS]);
    movePanel(before, 'stream-count', 'up');
    expect(before.order).toEqual(PANEL_IDS);
  });

  it('skips hidden panels so the move is visible to the viewer', () => {
    // temporary-limits is hidden (not in `visible`): moving the chart up must land above overview,
    // and the hidden panel keeps its relative order.
    const visible = ['overview', 'bandwidth-chart'] as const;
    const next = movePanel(layout(['overview', 'temporary-limits', 'bandwidth-chart']), 'bandwidth-chart', 'up', visible);
    expect(next.order).toEqual(['bandwidth-chart', 'overview', 'temporary-limits']);
  });

  it('returns the same layout when the only panels in that direction are hidden', () => {
    const start = layout(['overview', 'temporary-limits']);
    expect(movePanel(start, 'overview', 'down', ['overview'])).toBe(start);
  });
});

describe('togglePanel', () => {
  it('adds a panel to collapsed, then removes it', () => {
    const once = togglePanel(DEFAULT_LAYOUT, 'stream-count');
    expect(once.collapsed).toEqual(['stream-count']);
    expect(once.order).toEqual(DEFAULT_LAYOUT.order);
    const twice = togglePanel(once, 'stream-count');
    expect(twice.collapsed).toEqual([]);
  });
});

describe('isDefaultLayout', () => {
  it('is false when the order differs or anything is collapsed', () => {
    expect(isDefaultLayout(movePanel(DEFAULT_LAYOUT, 'stream-count', 'up'))).toBe(false);
    expect(isDefaultLayout(togglePanel(DEFAULT_LAYOUT, 'overview'))).toBe(false);
  });
});

describe('serializeLayout / parseLayout', () => {
  it('serialises with a version field', () => {
    expect(JSON.parse(serializeLayout(DEFAULT_LAYOUT))).toEqual({ v: 1, order: PANEL_IDS, collapsed: [] });
  });

  it('round-trips a customised layout', () => {
    const custom = togglePanel(movePanel(DEFAULT_LAYOUT, 'active-streams', 'up'), 'bandwidth-chart');
    expect(parseLayout(serializeLayout(custom))).toEqual(custom);
  });

  it('returns the default for null, non-JSON, non-object and wrong-version input', () => {
    expect(parseLayout(null)).toEqual(DEFAULT_LAYOUT);
    expect(parseLayout('{nope')).toEqual(DEFAULT_LAYOUT);
    expect(parseLayout('"a string"')).toEqual(DEFAULT_LAYOUT);
    expect(parseLayout('[1,2]')).toEqual(DEFAULT_LAYOUT);
    expect(parseLayout(JSON.stringify({ v: 2, order: ['overview'], collapsed: [] }))).toEqual(DEFAULT_LAYOUT);
  });

  it('drops unknown ids and duplicates, and appends missing ids in default order', () => {
    const raw = JSON.stringify({
      v: 1,
      order: ['stream-count', 'bogus', 'overview', 'stream-count', 42],
      collapsed: ['bogus', 'overview', 'overview'],
    });
    expect(parseLayout(raw)).toEqual({
      order: ['stream-count', 'overview', 'temporary-limits', 'bandwidth-chart', 'active-streams'],
      collapsed: ['overview'],
    });
  });

  it('treats a missing or non-array collapsed as empty', () => {
    expect(parseLayout(JSON.stringify({ v: 1, order: [] })).collapsed).toEqual([]);
    expect(parseLayout(JSON.stringify({ v: 1, order: [], collapsed: 'x' })).collapsed).toEqual([]);
    expect(parseLayout(JSON.stringify({ v: 1 })).order).toEqual(PANEL_IDS);
  });
});

import { describe, it, expect, beforeEach } from 'vitest';
import { renderHook, act } from '@testing-library/react';
import { useDashboardLayout } from './useDashboardLayout';
import { LAYOUT_STORAGE_KEY, PANEL_IDS } from '@/lib/dashboardLayout';

const stored = () => {
  const raw = localStorage.getItem(LAYOUT_STORAGE_KEY);
  return raw === null ? null : JSON.parse(raw);
};

beforeEach(() => {
  localStorage.clear();
});

describe('useDashboardLayout', () => {
  it('starts from the default layout and writes nothing on mount', () => {
    const { result } = renderHook(() => useDashboardLayout());
    expect(result.current.layout.order).toEqual(PANEL_IDS);
    expect(result.current.layout.collapsed).toEqual([]);
    expect(result.current.isDefault).toBe(true);
    expect(stored()).toBeNull();
  });

  it('restores a valid stored layout', () => {
    const order = [...PANEL_IDS].reverse();
    localStorage.setItem(LAYOUT_STORAGE_KEY, JSON.stringify({ v: 1, order, collapsed: ['stream-count'] }));
    const { result } = renderHook(() => useDashboardLayout());
    expect(result.current.layout).toEqual({ order, collapsed: ['stream-count'] });
    expect(result.current.isDefault).toBe(false);
  });

  it('falls back to the default on garbage', () => {
    localStorage.setItem(LAYOUT_STORAGE_KEY, '{nope');
    const { result } = renderHook(() => useDashboardLayout());
    expect(result.current.layout.order).toEqual(PANEL_IDS);
  });

  it('move updates the order and writes it', () => {
    const { result } = renderHook(() => useDashboardLayout());
    act(() => result.current.move('bandwidth-chart', 'up', result.current.layout.order));
    expect(result.current.layout.order[1]).toBe('bandwidth-chart');
    expect(result.current.isDefault).toBe(false);
    expect(stored()).toEqual({ v: 1, order: result.current.layout.order, collapsed: [] });
  });

  it('a no-op move writes nothing', () => {
    const { result } = renderHook(() => useDashboardLayout());
    act(() => result.current.move('overview', 'up', result.current.layout.order));
    expect(stored()).toBeNull();
  });

  it('toggle collapses, writes, and toggles back', () => {
    const { result } = renderHook(() => useDashboardLayout());
    act(() => result.current.toggle('stream-count'));
    expect(result.current.layout.collapsed).toEqual(['stream-count']);
    expect(stored().collapsed).toEqual(['stream-count']);
    act(() => result.current.toggle('stream-count'));
    expect(result.current.layout.collapsed).toEqual([]);
    expect(stored().collapsed).toEqual([]);
  });

  it('reset restores and writes the default', () => {
    const { result } = renderHook(() => useDashboardLayout());
    act(() => result.current.move('active-streams', 'up', result.current.layout.order));
    act(() => result.current.toggle('overview'));
    act(() => result.current.reset());
    expect(result.current.isDefault).toBe(true);
    expect(stored()).toEqual({ v: 1, order: PANEL_IDS, collapsed: [] });
  });
});

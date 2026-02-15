import { useState, useCallback, useEffect, useRef } from 'react';
import type { ChartDataPoint } from '@/types';

export interface ZoomRange {
  start: number; // epoch ms
  end: number;   // epoch ms
}

interface ChartZoomState {
  isSelecting: boolean;
  selectionStart: number | null;  // epoch ms (from chart coordinate)
  selectionEnd: number | null;
  zoomRange: ZoomRange | null;
}

interface UseChartZoomReturn {
  isSelecting: boolean;
  selectionStart: number | null;
  selectionEnd: number | null;
  zoomRange: ZoomRange | null;
  isZoomed: boolean;
  handleMouseDown: (e: { activeLabel?: string; chartX?: number }) => void;
  handleMouseMove: (e: { activeLabel?: string; chartX?: number }) => void;
  handleMouseUp: () => void;
  handleDoubleClick: () => void;
  resetZoom: () => void;
  filterDataByZoom: (data: ChartDataPoint[]) => ChartDataPoint[];
}

/** Standalone filter for components that receive zoomRange as a prop */
export function filterDataByZoomRange<T extends { timestamp: string }>(data: T[], zoomRange: ZoomRange | null): T[] {
  if (!zoomRange) return data;
  const { start, end } = zoomRange;
  return data.filter(point => {
    const ts = point.timestamp.endsWith('Z') ? point.timestamp : point.timestamp + 'Z';
    const t = new Date(ts).getTime();
    return t >= start && t <= end;
  });
}

const MIN_DRAG_PX = 10;
const MIN_SELECTION_MS = 30 * 1000; // 30 seconds

export function useChartZoom(): UseChartZoomReturn {
  const [state, setState] = useState<ChartZoomState>({
    isSelecting: false,
    selectionStart: null,
    selectionEnd: null,
    zoomRange: null,
  });

  const dragStartX = useRef<number | null>(null);
  const dragActivated = useRef(false);
  const startLabel = useRef<number | null>(null);

  const parseTimestamp = (label?: string): number | null => {
    if (!label) return null;
    const ts = label.endsWith('Z') ? label : label + 'Z';
    const val = new Date(ts).getTime();
    return isNaN(val) ? null : val;
  };

  const handleMouseDown = useCallback((e: { activeLabel?: string; chartX?: number }) => {
    // Don't start selection if no valid label
    const ts = parseTimestamp(e.activeLabel);
    if (ts === null) return;

    dragStartX.current = e.chartX ?? null;
    dragActivated.current = false;
    startLabel.current = ts;

    // Don't set isSelecting yet — wait until drag threshold is met
  }, []);

  const handleMouseMove = useCallback((e: { activeLabel?: string; chartX?: number }) => {
    if (startLabel.current === null || dragStartX.current === null) return;

    const currentX = e.chartX ?? 0;
    const dx = Math.abs(currentX - dragStartX.current);

    // Activate drag once threshold is met
    if (!dragActivated.current) {
      if (dx < MIN_DRAG_PX) return;
      dragActivated.current = true;
      setState(prev => ({
        ...prev,
        isSelecting: true,
        selectionStart: startLabel.current,
        selectionEnd: startLabel.current,
      }));
    }

    const ts = parseTimestamp(e.activeLabel);
    if (ts === null) return;

    setState(prev => ({
      ...prev,
      selectionEnd: ts,
    }));
  }, []);

  const handleMouseUp = useCallback(() => {
    if (!dragActivated.current || startLabel.current === null) {
      // Was a click, not a drag — just reset
      dragStartX.current = null;
      dragActivated.current = false;
      startLabel.current = null;
      setState(prev => ({
        ...prev,
        isSelecting: false,
        selectionStart: null,
        selectionEnd: null,
      }));
      return;
    }

    setState(prev => {
      const start = prev.selectionStart;
      const end = prev.selectionEnd;

      if (start === null || end === null) {
        return {
          ...prev,
          isSelecting: false,
          selectionStart: null,
          selectionEnd: null,
        };
      }

      // Normalize direction
      const rangeStart = Math.min(start, end);
      const rangeEnd = Math.max(start, end);

      // Reject tiny selections
      if (rangeEnd - rangeStart < MIN_SELECTION_MS) {
        return {
          ...prev,
          isSelecting: false,
          selectionStart: null,
          selectionEnd: null,
        };
      }

      return {
        isSelecting: false,
        selectionStart: null,
        selectionEnd: null,
        zoomRange: { start: rangeStart, end: rangeEnd },
      };
    });

    dragStartX.current = null;
    dragActivated.current = false;
    startLabel.current = null;
  }, []);

  const handleDoubleClick = useCallback(() => {
    setState({
      isSelecting: false,
      selectionStart: null,
      selectionEnd: null,
      zoomRange: null,
    });
    dragStartX.current = null;
    dragActivated.current = false;
    startLabel.current = null;
  }, []);

  const resetZoom = useCallback(() => {
    setState({
      isSelecting: false,
      selectionStart: null,
      selectionEnd: null,
      zoomRange: null,
    });
    dragStartX.current = null;
    dragActivated.current = false;
    startLabel.current = null;
  }, []);

  const filterDataByZoom = useCallback((data: ChartDataPoint[]): ChartDataPoint[] => {
    if (!state.zoomRange) return data;
    const { start, end } = state.zoomRange;
    return data.filter(point => {
      const ts = point.timestamp.endsWith('Z') ? point.timestamp : point.timestamp + 'Z';
      const t = new Date(ts).getTime();
      return t >= start && t <= end;
    });
  }, [state.zoomRange]);

  // Catch mouseup/touchend outside the chart
  useEffect(() => {
    const handleGlobalUp = () => {
      if (dragActivated.current || startLabel.current !== null) {
        handleMouseUp();
      }
    };
    window.addEventListener('mouseup', handleGlobalUp);
    window.addEventListener('touchend', handleGlobalUp);
    return () => {
      window.removeEventListener('mouseup', handleGlobalUp);
      window.removeEventListener('touchend', handleGlobalUp);
    };
  }, [handleMouseUp]);

  return {
    isSelecting: state.isSelecting,
    selectionStart: state.selectionStart,
    selectionEnd: state.selectionEnd,
    zoomRange: state.zoomRange,
    isZoomed: state.zoomRange !== null,
    handleMouseDown,
    handleMouseMove,
    handleMouseUp,
    handleDoubleClick,
    resetZoom,
    filterDataByZoom,
  };
}

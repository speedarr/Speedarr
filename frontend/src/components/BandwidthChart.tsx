import React, { useState, useEffect, useMemo, useCallback } from 'react';
import {
  ComposedChart,
  Area,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
  ReferenceLine,
  ReferenceArea,
  Line,
  LineChart,
} from 'recharts';
import { formatInTimeZone } from 'date-fns-tz';
import { apiClient } from '@/api/client';
import type { ChartDataPoint } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { Loader2, AlertCircle, Layers, BarChart3, ArrowUpDown, ZoomOut, Server } from 'lucide-react';
import { useChartZoom, type ZoomRange } from '@/hooks/useChartZoom';
import { buildChartSeries, resolveSeriesColors, computeLegacyFoldMap, foldLegacyPoints, dropFoldedHistoricalSeries, type ChartSeriesDescriptor } from '@/lib/chartSeries';

// Dynamic SVG gradient ids for a series (id is safe for SVG: letters/digits/underscore).
const dlGradientId = (id: string) => `grad_dl_${id}`;
const ulGradientId = (id: string) => `grad_ul_${id}`;

// Color palette for per-server stream breakdown lines
const PER_SERVER_COLORS = ['#6366f1', '#f59e0b', '#10b981', '#ec4899', '#06b6d4', '#84cc16'];

interface LegendItem {
  value: string;
  type: string;
  color: string;
  dataKey: string;
}

interface CustomLegendProps {
  payload?: LegendItem[];
  visibleSeries: Record<string, boolean>;
  onToggle: (dataKey: string) => void;
}

const CustomLegend: React.FC<CustomLegendProps> = ({ payload, visibleSeries, onToggle }) => {
  if (!payload) return null;

  // Downloads sort before uploads. A key is a download if it carries a download
  // suffix or is the SNMP download line; everything else (uploads, streams) sorts after.
  const isDownloadKey = (key: string) =>
    key === 'snmp_download' || key.endsWith('_download') || key.endsWith('_download_limit_line');

  // Sort payload: downloads first (alphabetically by name), then uploads (alphabetically by name)
  const sortedPayload = [...payload].sort((a, b) => {
    const aIsDownload = isDownloadKey(a.dataKey);
    const bIsDownload = isDownloadKey(b.dataKey);

    // Downloads come before uploads
    if (aIsDownload && !bIsDownload) return -1;
    if (!aIsDownload && bIsDownload) return 1;

    // Within same category, keep WAN before LAN, then alphabetically
    const streamOrder: Record<string, number> = { wan_streams: 0, lan_streams: 1 };
    const aStream = streamOrder[a.dataKey];
    const bStream = streamOrder[b.dataKey];
    if (aStream !== undefined && bStream !== undefined) return aStream - bStream;
    if (aStream !== undefined) return -1;
    if (bStream !== undefined) return 1;
    return a.value.localeCompare(b.value);
  });

  return (
    <div className="flex flex-wrap justify-center gap-4 pt-2">
      {sortedPayload.map((entry, index) => {
        const isVisible = visibleSeries[entry.dataKey];
        return (
          <button
            key={`legend-${index}`}
            onClick={() => onToggle(entry.dataKey)}
            className="flex items-center gap-2 cursor-pointer hover:opacity-80 transition-opacity"
            aria-label={`${isVisible ? 'Hide' : 'Show'} ${entry.value}`}
            aria-pressed={isVisible}
          >
            <div
              className="w-4 h-4 rounded"
              style={{
                backgroundColor: isVisible ? entry.color : 'transparent',
                border: `2px solid ${entry.color}`,
              }}
            />
            <span
              className={`text-sm ${isVisible ? '' : 'line-through opacity-50'}`}
              style={{ color: isVisible ? '#888' : '#666' }}
            >
              {entry.value}
            </span>
          </button>
        );
      })}
    </div>
  );
};

export interface TimeRange {
  label: string;
  hours: number;
}

export type DataInterval = 'raw' | 0.25 | 0.5 | 1 | 5 | 10 | 15 | 30 | 60;

interface BandwidthChartProps {
  timeRange: TimeRange;
  setTimeRange: (range: TimeRange) => void;
  dataInterval: DataInterval;
  setDataInterval: (interval: DataInterval) => void;
  timeRanges: TimeRange[];
  onZoomChange?: (zoomRange: ZoomRange | null) => void;
  configuredServerCount: number;
}

// Default visibility for the non-per-client (fixed-key) series only. Per-client
// series visibility (`<id>_download`, `<id>_upload`, and the `_limit_line`
// variants) is seeded per id when the series load — see the effect in the
// component body — so no client-type keys belong here.
const defaultVisibleSeries: Record<string, boolean> = {
  wan_streams: true,
  lan_streams: false,
  snmp_download: false,
  snmp_upload: false,
};

// Load saved visible series from localStorage
const loadVisibleSeries = (): Record<string, boolean> => {
  try {
    const saved = localStorage.getItem('speedarr_chart_visible_series');
    if (saved) {
      const parsed = JSON.parse(saved);
      // Merge with defaults to handle new series that may have been added
      return { ...defaultVisibleSeries, ...parsed };
    }
  } catch (e) {
    console.error('Failed to load chart preferences:', e);
  }
  return defaultVisibleSeries;
};

export const BandwidthChart: React.FC<BandwidthChartProps> = ({
  timeRange,
  setTimeRange,
  dataInterval,
  setDataInterval,
  timeRanges,
  onZoomChange,
  configuredServerCount,
}) => {
  const [rawData, setRawData] = useState<ChartDataPoint[]>([]);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [error, setError] = useState('');
  const [visibleSeries, setVisibleSeries] = useState<Record<string, boolean>>(loadVisibleSeries);
  const [descriptors, setDescriptors] = useState<ChartSeriesDescriptor[]>([]);
  const [historicalSeries, setHistoricalSeries] = useState<Array<{ id: string; type: string }>>([]);
  const [snmpEnabled, setSnmpEnabled] = useState<boolean>(false);
  const [mediaServerNames, setMediaServerNames] = useState<Record<string, string>>({});
  const [stackChart, setStackChart] = useState<boolean>(() => {
    const saved = localStorage.getItem('speedarr_chart_stacked');
    return saved !== null ? JSON.parse(saved) : true;
  });
  const [flipped, setFlipped] = useState<boolean>(() => {
    const saved = localStorage.getItem('speedarr_chart_flipped');
    return saved !== null ? JSON.parse(saved) : true;
  });
  const [clientOrder, setClientOrder] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('speedarr_chart_client_order');
      if (saved) return JSON.parse(saved);
    } catch {}
    return [];
  });

  // Per-server stream breakdown (from per_server_series / per_server_points in chart-data response)
  const [perServerSeries, setPerServerSeries] = useState<string[]>([]);
  const [perServerPoints, setPerServerPoints] = useState<Array<Record<string, number | string>>>([]);
  const [showPerServer, setShowPerServer] = useState<boolean>(false);

  // Chart zoom state
  const {
    isSelecting,
    selectionStart,
    selectionEnd,
    zoomRange,
    isZoomed,
    handleMouseDown: zoomMouseDown,
    handleMouseMove: zoomMouseMove,
    handleMouseUp: zoomMouseUp,
    handleDoubleClick: zoomDoubleClick,
    resetZoom,
    filterDataByZoom,
  } = useChartZoom();

  // Notify parent of zoom range changes
  useEffect(() => {
    onZoomChange?.(zoomRange);
  }, [zoomRange, onZoomChange]);

  // Save stacking preferences to localStorage
  useEffect(() => {
    localStorage.setItem('speedarr_chart_stacked', JSON.stringify(stackChart));
  }, [stackChart]);
  useEffect(() => {
    localStorage.setItem('speedarr_chart_flipped', JSON.stringify(flipped));
  }, [flipped]);
  useEffect(() => {
    if (clientOrder.length > 0) {
      localStorage.setItem('speedarr_chart_client_order', JSON.stringify(clientOrder));
    }
  }, [clientOrder]);

  // Load client metadata and SNMP status from public status endpoint
  useEffect(() => {
    const loadClientInfo = async () => {
      try {
        const status = await apiClient.getSystemStatus();

        // Build per-client-id descriptors from status (clients are keyed by id).
        const clientMap = new Map<string, ChartSeriesDescriptor>();
        const dlClients = status.bandwidth?.download?.clients || [];
        const ulClients = status.bandwidth?.upload?.clients || [];

        if (dlClients.length === 0 && ulClients.length === 0) {
          console.warn('[BandwidthChart] Status response returned 0 clients. Response status:', status.status);
        }

        for (const c of dlClients) {
          clientMap.set(c.id, {
            id: c.id, type: c.type, name: c.name,
            color: c.color, supportsUpload: false,
          });
        }
        for (const c of ulClients) {
          const existing = clientMap.get(c.id);
          if (existing) {
            existing.supportsUpload = true;
          } else {
            clientMap.set(c.id, {
              id: c.id, type: c.type, name: c.name,
              color: c.color, supportsUpload: true,
            });
          }
        }
        const clients = Array.from(clientMap.values());
        setDescriptors(clients);

        // Compute client order immediately (same batch), keyed by id.
        const enabledIds = clients.map(c => c.id);
        setClientOrder(prev => {
          const kept = prev.filter(id => enabledIds.includes(id));
          const newClients = enabledIds.filter(id => !kept.includes(id));
          return kept.length > 0 ? [...kept, ...newClients] : enabledIds;
        });

        setSnmpEnabled(status.snmp_enabled ?? false);

        // Capture media server display names for per-server chart labels
        if (status.media_server_statuses) {
          const names: Record<string, string> = {};
          for (const [id, info] of Object.entries(status.media_server_statuses)) {
            names[id] = info.name;
          }
          setMediaServerNames(names);
        }
      } catch (err) {
        console.error('Failed to load client info:', err);
      }
    };
    loadClientInfo();
  }, []);

  // Fold pre-fix, type-keyed history into the matching current client so a
  // single-instance client renders as one continuous series across the storage
  // cutover (no duplicate legacy entry). foldMap: type -> first current client id.
  const foldMap = useMemo(() => computeLegacyFoldMap(descriptors), [descriptors]);

  // Merge current clients with the historical-only series ids that DON'T fold
  // (removed clients / fully-removed types), then resolve collision-free colors.
  // `series` is the single source of truth for every per-client chart element.
  const series = useMemo(
    () => buildChartSeries(descriptors, dropFoldedHistoricalSeries(historicalSeries, foldMap)),
    [descriptors, historicalSeries, foldMap],
  );
  const seriesColors = useMemo(() => resolveSeriesColors(series), [series]);
  const seriesById = useMemo(() => {
    const map = new Map<string, ChartSeriesDescriptor>();
    for (const s of series) map.set(s.id, s);
    return map;
  }, [series]);

  // Lookup by series id, with display color from the collision-resolved map.
  const getSeriesInfo = useMemo(() => {
    return (id: string) => {
      const s = seriesById.get(id);
      return {
        name: s?.name ?? id,
        color: seriesColors[id] ?? '#888888',
        supportsUpload: s?.supportsUpload ?? false,
      };
    };
  }, [seriesById, seriesColors]);

  const seriesSupportsUpload = useMemo(() => {
    return (id: string) => seriesById.get(id)?.supportsUpload ?? false;
  }, [seriesById]);

  // Reconcile clientOrder with the actual series ids.
  useEffect(() => {
    if (series.length === 0) return;
    const ids = series.map(s => s.id);
    setClientOrder(prev => {
      const kept = prev.filter(id => ids.includes(id));
      const newClients = ids.filter(id => !kept.includes(id));
      const merged = [...kept, ...newClients];
      if (merged.length === prev.length && merged.every((id, i) => id === prev[i])) return prev;
      return merged;
    });
  }, [series]);

  // Ensure default visibility keys exist for every series (download+upload on,
  // limit lines off) without clobbering user toggles persisted in localStorage.
  useEffect(() => {
    if (series.length === 0) return;
    setVisibleSeries(prev => {
      const next = { ...prev };
      let changed = false;
      for (const s of series) {
        for (const [key, def] of [
          [`${s.id}_download`, true],
          [`${s.id}_upload`, true],
          [`${s.id}_download_limit_line`, false],
          [`${s.id}_upload_limit_line`, false],
        ] as Array<[string, boolean]>) {
          if (!(key in next)) { next[key] = def; changed = true; }
        }
      }
      return changed ? next : prev;
    });
  }, [series]);

  // Check if all data series are hidden (drives the "all hidden" hint).
  const allMetricsHidden = useMemo(() => {
    const activeKeys: string[] = [];
    for (const s of series) {
      activeKeys.push(`${s.id}_download`);
      if (s.supportsUpload) activeKeys.push(`${s.id}_upload`);
    }
    activeKeys.push('wan_streams', 'lan_streams');
    if (snmpEnabled) activeKeys.push('snmp_download', 'snmp_upload');
    if (activeKeys.length === 0) return false;
    return activeKeys.every(key => !visibleSeries[key]);
  }, [visibleSeries, series, snmpEnabled]);

  // Save visible series to localStorage when it changes
  useEffect(() => {
    try {
      localStorage.setItem('speedarr_chart_visible_series', JSON.stringify(visibleSeries));
    } catch (e) {
      console.error('Failed to save chart preferences:', e);
    }
  }, [visibleSeries]);

  // Apply zoom filter before aggregation
  // Fold legacy type-keyed point fields into current-client id fields before any
  // aggregation/zoom, so old history flows into the matching per-id series.
  const foldedRawData = useMemo(() => foldLegacyPoints(rawData, foldMap), [rawData, foldMap]);
  const zoomedRawData = useMemo(() => filterDataByZoom(foldedRawData), [foldedRawData, filterDataByZoom]);

  // Memoize aggregation - only recomputes when zoomedRawData or dataInterval changes
  const aggregatedData = useMemo(() => {
    if (zoomedRawData.length === 0) return [];
    if (dataInterval === 'raw') return zoomedRawData;

    const intervalMinutes = dataInterval as number;
    const intervalMs = intervalMinutes * 60 * 1000;
    const buckets: Map<number, ChartDataPoint[]> = new Map();

    // Group data points into time buckets
    zoomedRawData.forEach((point) => {
      const timestamp = new Date(point.timestamp).getTime();
      const bucketKey = Math.floor(timestamp / intervalMs) * intervalMs;

      if (!buckets.has(bucketKey)) {
        buckets.set(bucketKey, []);
      }
      buckets.get(bucketKey)!.push(point);
    });

    // Average each bucket, including limits
    const aggregated = Array.from(buckets.entries()).map(([bucketTime, points]) => {
      const avg: Record<string, number | string> = {
        timestamp: new Date(bucketTime).toISOString(),
        download_speed: points.reduce((sum, p) => sum + (p.download_speed || 0), 0) / points.length,
        upload_speed: points.reduce((sum, p) => sum + (p.upload_speed || 0), 0) / points.length,
        stream_bandwidth: points.reduce((sum, p) => sum + (p.stream_bandwidth || 0), 0) / points.length,
        // Backward compat: old data has null WAN/LAN — fall back to combined fields
        wan_stream_bandwidth: points.reduce((sum, p) => sum + (p.wan_stream_bandwidth != null ? p.wan_stream_bandwidth : (p.stream_bandwidth || 0)), 0) / points.length,
        lan_stream_bandwidth: points.reduce((sum, p) => sum + (p.lan_stream_bandwidth || 0), 0) / points.length,
        wan_streams_count: points.reduce((sum, p) => sum + (p.wan_streams_count != null ? p.wan_streams_count : (p.active_streams_count || 0)), 0) / points.length,
        lan_streams_count: points.reduce((sum, p) => sum + (p.lan_streams_count || 0), 0) / points.length,
        active_streams_count: points.reduce((sum, p) => sum + (p.active_streams_count || 0), 0) / points.length,
        // Average SNMP data
        snmp_download_speed: points.reduce((sum, p) => sum + (p.snmp_download_speed || 0), 0) / points.length,
        snmp_upload_speed: points.reduce((sum, p) => sum + (p.snmp_upload_speed || 0), 0) / points.length,
      };
      // Per-client-id averages (speeds + limits), keyed by series id.
      for (const s of series) {
        avg[`${s.id}_speed`] = points.reduce((sum, p) => sum + ((p[`${s.id}_speed`] as number) || 0), 0) / points.length;
        avg[`${s.id}_upload_speed`] = points.reduce((sum, p) => sum + ((p[`${s.id}_upload_speed`] as number) || 0), 0) / points.length;
        avg[`${s.id}_download_limit`] = points.reduce((sum, p) => sum + ((p[`${s.id}_download_limit`] as number) || 0), 0) / points.length;
        avg[`${s.id}_upload_limit`] = points.reduce((sum, p) => sum + ((p[`${s.id}_upload_limit`] as number) || 0), 0) / points.length;
      }
      return avg;
    });

    return aggregated.sort((a, b) => new Date(a.timestamp as string).getTime() - new Date(b.timestamp as string).getTime());
  }, [zoomedRawData, dataInterval, series]);

  const fetchData = useCallback(async () => {
    setError('');
    try {
      // Fetch chart data with per-datapoint limits
      const chartResponse = await apiClient.getBandwidthChartData({
        hours: timeRange.hours,
        interval_minutes: 1,
      });

      setRawData(chartResponse.data);
      // Capture per-server breakdown if present
      setPerServerSeries(chartResponse.per_server_series ?? []);
      setPerServerPoints(chartResponse.per_server_points ?? []);
      // Capture per-client-id series ids present in this window (for historical/removed clients)
      setHistoricalSeries(chartResponse.client_series ?? []);
    } catch (err) {
      setError('Failed to load bandwidth data');
      console.error('Error fetching bandwidth chart data:', err);
    } finally {
      setIsInitialLoad(false);
    }
  }, [timeRange.hours]);

  // Memoize transformed chart data - depends on aggregated data and visibleSeries for scaling
  const transformedData = useMemo(() => {
    if (aggregatedData.length === 0) return { data: [], positiveRatio: 1, negativeRatio: 1, yDomain: ['auto', 'auto'] as [string, string] };

    // Find max values for scaling - only include visible series
    // When flipped, uploads are positive (on top) and downloads are negated (below zero)
    let maxPositive = 0;
    let maxToNegate = 0;

    aggregatedData.forEach((point) => {
      // Compute download totals from visible per-id series
      let totalDownload = 0;
      let maxDownloadLimit = 0;
      let totalUpload = 0;
      let maxUploadLimit = 0;
      for (const s of series) {
        if (visibleSeries[`${s.id}_download`]) totalDownload += (point[`${s.id}_speed`] as number) || 0;
        if (s.supportsUpload && visibleSeries[`${s.id}_upload`]) totalUpload += (point[`${s.id}_upload_speed`] as number) || 0;
        if (visibleSeries[`${s.id}_download_limit_line`]) maxDownloadLimit = Math.max(maxDownloadLimit, (point[`${s.id}_download_limit`] as number) || 0);
        if (s.supportsUpload && visibleSeries[`${s.id}_upload_limit_line`]) maxUploadLimit = Math.max(maxUploadLimit, (point[`${s.id}_upload_limit`] as number) || 0);
      }

      const snmpDownloadVal = visibleSeries.snmp_download ? ((point.snmp_download_speed as number) || 0) : 0;

      // WAN streams: use wan_stream_bandwidth if available, fall back to combined stream_bandwidth for old data
      if (visibleSeries.wan_streams) totalUpload += ((point.wan_stream_bandwidth as number | null) != null ? (point.wan_stream_bandwidth as number) : ((point.stream_bandwidth as number) || 0));

      // LAN streams render as an independent Line (not stacked), so track separately
      const lanBandwidth = visibleSeries.lan_streams ? ((point.lan_stream_bandwidth as number) || 0) : 0;

      const snmpUploadVal = visibleSeries.snmp_upload ? ((point.snmp_upload_speed as number) || 0) : 0;

      if (flipped) {
        // Uploads on top (positive), downloads negated
        maxPositive = Math.max(maxPositive, totalUpload, lanBandwidth, snmpUploadVal, maxUploadLimit);
        maxToNegate = Math.max(maxToNegate, totalDownload, snmpDownloadVal, maxDownloadLimit);
      } else {
        // Downloads on top (positive), uploads negated
        maxPositive = Math.max(maxPositive, totalDownload, snmpDownloadVal, maxDownloadLimit);
        maxToNegate = Math.max(maxToNegate, totalUpload, lanBandwidth, snmpUploadVal, maxUploadLimit);
      }
    });

    // Use overallMax so the domain is the same regardless of flip direction.
    const overallMax = Math.max(maxPositive, maxToNegate);

    // Calculate scaling ratios — each side scales its data to fill the overallMax domain
    const positiveRatio = (maxPositive > 0 && maxToNegate > 0) ? overallMax / maxPositive : 1;
    const negativeRatio = (maxPositive > 0 && maxToNegate > 0) ? overallMax / maxToNegate : 1;

    // Calculate Y-axis domain: symmetric when both sides have data,
    // full-height when only one side has data.
    const domainPadding = 1.05;
    let yDomain: [number | string, number | string];
    if (maxPositive > 0 && maxToNegate > 0) {
      // Both sides have data — symmetric domain using overall max
      const extent = overallMax * domainPadding;
      yDomain = [-extent, extent];
    } else if (maxPositive > 0) {
      // Only positive side has data — fill entire chart
      yDomain = [0, maxPositive * domainPadding];
    } else if (maxToNegate > 0) {
      // Only negative side has data — fill entire chart
      yDomain = [-maxToNegate * domainPadding, 0];
    } else {
      yDomain = ['auto', 'auto'];
    }

    // Transform data and include limits as line data
    // When flipped, uploads stay positive and downloads get negated+scaled (and vice versa)
    const chartData = aggregatedData.map((point) => ({
      ...point,
      // Upload series — WAN/LAN stream split (backward compat: wan falls back to combined stream_bandwidth)
      wan_streams: (() => { const v = point.wan_stream_bandwidth != null ? point.wan_stream_bandwidth : (point.stream_bandwidth || 0); return flipped ? Math.abs(v as number) * positiveRatio : -Math.abs(v as number) * negativeRatio; })(),
      lan_streams: (() => { const v = point.lan_stream_bandwidth || 0; return flipped ? Math.abs(v as number) * positiveRatio : -Math.abs(v as number) * negativeRatio; })(),
      // Per-client-id download/upload areas + limit lines (keyed by series id)
      ...Object.fromEntries(series.flatMap((s) => {
        const dlSpeed = (point[`${s.id}_speed`] as number) || 0;
        const ulSpeed = (point[`${s.id}_upload_speed`] as number) || 0;
        const dlLimit = (point[`${s.id}_download_limit`] as number) || 0;
        const ulLimit = (point[`${s.id}_upload_limit`] as number) || 0;
        return [
          [`${s.id}_download`, flipped ? -Math.abs(dlSpeed) * negativeRatio : dlSpeed * positiveRatio],
          [`${s.id}_upload`, flipped ? Math.abs(ulSpeed) * positiveRatio : -Math.abs(ulSpeed) * negativeRatio],
          [`${s.id}_download_limit_line`, flipped ? (dlLimit ? -Math.abs(dlLimit) * negativeRatio : null) : (dlLimit ? Math.abs(dlLimit) * positiveRatio : null)],
          [`${s.id}_upload_limit_line`, flipped ? (ulLimit ? Math.abs(ulLimit) * positiveRatio : null) : (ulLimit ? -Math.abs(ulLimit) * negativeRatio : null)],
        ];
      })),
      // SNMP bandwidth
      snmp_download: flipped ? ((point.snmp_download_speed as number | null) != null ? -Math.abs(point.snmp_download_speed as number) * negativeRatio : null) : ((point.snmp_download_speed as number | null) != null ? Math.abs(point.snmp_download_speed as number) * positiveRatio : null),
      snmp_upload: flipped ? ((point.snmp_upload_speed as number | null) != null ? Math.abs(point.snmp_upload_speed as number) * positiveRatio : null) : ((point.snmp_upload_speed as number | null) != null ? -Math.abs(point.snmp_upload_speed as number) * negativeRatio : null),
    }));

    return { data: chartData, positiveRatio, negativeRatio, yDomain };
  }, [aggregatedData, visibleSeries, stackChart, flipped, series]);

  const data = transformedData.data;
  const positiveScalingRatio = transformedData.positiveRatio;
  const negativeScalingRatio = transformedData.negativeRatio;
  const yDomain = transformedData.yDomain;

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [fetchData]);


  // Reset zoom when time range dropdown changes
  useEffect(() => {
    resetZoom();
  }, [timeRange, resetZoom]);

  // Calculate zoomed duration for XAxis formatting
  const zoomedDurationHours = useMemo(() => {
    if (!isZoomed || zoomedRawData.length < 2) return null;
    const first = new Date((zoomedRawData[0].timestamp.endsWith('Z') ? zoomedRawData[0].timestamp : zoomedRawData[0].timestamp + 'Z')).getTime();
    const last = new Date((zoomedRawData[zoomedRawData.length - 1].timestamp.endsWith('Z') ? zoomedRawData[zoomedRawData.length - 1].timestamp : zoomedRawData[zoomedRawData.length - 1].timestamp + 'Z')).getTime();
    return (last - first) / (1000 * 60 * 60);
  }, [isZoomed, zoomedRawData]);

  const formatXAxis = (timestamp: string) => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // Ensure timestamp is parsed as UTC (API returns UTC without 'Z' suffix)
    const utcTimestamp = timestamp.endsWith('Z') ? timestamp : timestamp + 'Z';
    const effectiveHours = zoomedDurationHours ?? timeRange.hours;
    if (effectiveHours <= 1) {
      return formatInTimeZone(new Date(utcTimestamp), tz, 'HH:mm:ss');
    } else if (effectiveHours <= 24) {
      return formatInTimeZone(new Date(utcTimestamp), tz, 'HH:mm');
    } else {
      return formatInTimeZone(new Date(utcTimestamp), tz, 'MM/dd HH:mm');
    }
  };

  const formatTooltip = (value: number, name: string) => {
    // Show absolute value — unscale using the appropriate ratio
    let absValue = Math.abs(value);

    if (value < 0 && negativeScalingRatio !== 1) {
      absValue = absValue / negativeScalingRatio;
    } else if (value > 0 && positiveScalingRatio !== 1) {
      absValue = absValue / positiveScalingRatio;
    }

    return [`${absValue.toFixed(2)} Mbps`, name];
  };

  const formatYAxis = (value: number) => {
    // Unscale each side using its own ratio for display
    if (value < 0 && negativeScalingRatio !== 1) {
      return (Math.abs(value) / negativeScalingRatio).toFixed(0);
    }
    if (value > 0 && positiveScalingRatio !== 1) {
      return (Math.abs(value) / positiveScalingRatio).toFixed(0);
    }
    return Math.abs(value).toFixed(0);
  };

  // Show per-server UI when 2+ media servers are configured, or when the chart
  // data itself spans more than one server (e.g. a since-removed server's history).
  const hasMultipleServers = configuredServerCount >= 2 || perServerSeries.length > 1;

  return (
    <Card>
      <CardHeader>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <CardTitle>Bandwidth Usage</CardTitle>
          <div className="flex flex-wrap gap-2">
            {stackChart && clientOrder.length > 1 && (
              <>
                <Select
                  value={clientOrder[0]}
                  onValueChange={(value) => {
                    setClientOrder(prev => [value, ...prev.filter(c => c !== value)]);
                  }}
                >
                  <SelectTrigger className="w-[230px]" aria-label="Select stack order">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {clientOrder.map((id) => (
                      <SelectItem key={id} value={id}>
                        {getSeriesInfo(id).name} first (bottom)
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>

                <div className="border-l border-border h-6 self-center" />
              </>
            )}

            <Select
              value={timeRange.label}
              onValueChange={(value) => {
                const selected = timeRanges.find((r) => r.label === value);
                if (selected) setTimeRange(selected);
              }}
            >
              <SelectTrigger className="w-[160px]" aria-label="Select time range for chart data">
                <SelectValue placeholder="Time Range" />
              </SelectTrigger>
              <SelectContent>
                {timeRanges.map((range) => (
                  <SelectItem key={range.label} value={range.label}>
                    {range.label}
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>

            <Select
              value={dataInterval.toString()}
              onValueChange={(value) => {
                setDataInterval(value === 'raw' ? 'raw' : parseFloat(value) as DataInterval);
              }}
            >
              <SelectTrigger className="w-[140px]" aria-label="Select data aggregation interval">
                <SelectValue placeholder="Interval" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="raw">Raw Data</SelectItem>
                <SelectItem value="0.25">15 sec</SelectItem>
                <SelectItem value="0.5">30 sec</SelectItem>
                <SelectItem value="1">1 min</SelectItem>
                <SelectItem value="5">5 min</SelectItem>
                <SelectItem value="10">10 min</SelectItem>
                <SelectItem value="15">15 min</SelectItem>
                <SelectItem value="30">30 min</SelectItem>
                <SelectItem value="60">1 hour</SelectItem>
              </SelectContent>
            </Select>

            <Button
              variant="outline"
              size="sm"
              onClick={() => setStackChart(!stackChart)}
              className="gap-2"
              title={stackChart ? 'Switch to overlapping view' : 'Switch to stacked view'}
              aria-label={stackChart ? 'Currently showing stacked view, click to switch to overlapping' : 'Currently showing overlapping view, click to switch to stacked'}
              aria-pressed={stackChart}
            >
              {stackChart ? <Layers className="h-4 w-4" aria-hidden="true" /> : <BarChart3 className="h-4 w-4" aria-hidden="true" />}
              {stackChart ? 'Stacked' : 'Overlapping'}
            </Button>
            <Button
              variant="outline"
              size="sm"
              onClick={() => setFlipped(!flipped)}
              className="gap-2"
              title={flipped ? 'Uploads on top — click to put downloads on top' : 'Downloads on top — click to put uploads on top'}
              aria-label={flipped ? 'Currently showing uploads on top, click to flip' : 'Currently showing downloads on top, click to flip'}
              aria-pressed={flipped}
            >
              <ArrowUpDown className="h-4 w-4" aria-hidden="true" />
              {flipped ? 'UL on Top' : 'DL on Top'}
            </Button>
            {hasMultipleServers && (
              <Button
                variant={showPerServer ? 'default' : 'outline'}
                size="sm"
                onClick={() => setShowPerServer(!showPerServer)}
                className="gap-2"
                title={showPerServer ? 'Hide per-server stream breakdown' : 'Show per-server stream breakdown'}
                aria-label={showPerServer ? 'Hide per-server stream breakdown' : 'Show per-server stream breakdown'}
                aria-pressed={showPerServer}
              >
                <Server className="h-4 w-4" aria-hidden="true" />
                Per Server
              </Button>
            )}
            {isZoomed && (
              <Button
                variant="outline"
                size="sm"
                onClick={resetZoom}
                className="gap-2"
                title="Reset zoom to full time range"
                aria-label="Reset zoom"
              >
                <ZoomOut className="h-4 w-4" aria-hidden="true" />
                Reset Zoom
              </Button>
            )}
          </div>
        </div>
      </CardHeader>

      <CardContent>
        {error && (
          <Alert variant="destructive" className="mb-4">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {isInitialLoad ? (
          <div className="flex justify-center items-center p-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </div>
        ) : data.length === 0 ? (
          <Alert>
            <AlertDescription>No bandwidth data available for the selected time range.</AlertDescription>
          </Alert>
        ) : (
          <>
          {allMetricsHidden && (
            <Alert className="mb-4">
              <AlertDescription>All metrics are hidden. Click on a legend item below to show data.</AlertDescription>
            </Alert>
          )}
          <div style={{ touchAction: isSelecting ? 'none' : 'pan-y', userSelect: 'none', WebkitUserSelect: 'none' }}>
          <ResponsiveContainer width="100%" height={700}>
              <ComposedChart
                key={`chart-${flipped}`}
                data={data}
                margin={{ top: 10, right: 10, left: 10, bottom: 20 }}
                onMouseDown={zoomMouseDown}
                onMouseMove={zoomMouseMove}
                onMouseUp={zoomMouseUp}
                onDoubleClick={zoomDoubleClick}
                style={{ cursor: isSelecting ? 'col-resize' : 'crosshair' }}
              >
                <defs key={`chart-defs-${flipped}`}>
                  {/* Per-client-id download gradients */}
                  {series.map((s) => {
                    const color = getSeriesInfo(s.id).color;
                    return (
                      <linearGradient key={dlGradientId(s.id)} id={dlGradientId(s.id)} x1="0" y1={flipped ? "1" : "0"} x2="0" y2={flipped ? "0" : "1"}>
                        <stop offset="5%" stopColor={color} stopOpacity={0.8}/>
                        <stop offset="95%" stopColor={color} stopOpacity={0.3}/>
                      </linearGradient>
                    );
                  })}
                  {/* Per-client-id upload gradients (only upload-capable series) */}
                  {series.filter((s) => s.supportsUpload).map((s) => {
                    const color = getSeriesInfo(s.id).color;
                    return (
                      <linearGradient key={ulGradientId(s.id)} id={ulGradientId(s.id)} x1="0" y1={flipped ? "0" : "1"} x2="0" y2={flipped ? "1" : "0"}>
                        <stop offset="5%" stopColor={color} stopOpacity={0.8}/>
                        <stop offset="95%" stopColor={color} stopOpacity={0.3}/>
                      </linearGradient>
                    );
                  })}
                  {/* WAN streams gradient - always shown */}
                  <linearGradient id="wanStreams" x1="0" y1={flipped ? "0" : "1"} x2="0" y2={flipped ? "1" : "0"}>
                    <stop offset="5%" stopColor="#ff7300" stopOpacity={0.8}/>
                    <stop offset="95%" stopColor="#ff7300" stopOpacity={0.3}/>
                  </linearGradient>
                  {/* LAN streams gradient - always shown */}
                  <linearGradient id="lanStreams" x1="0" y1={flipped ? "0" : "1"} x2="0" y2={flipped ? "1" : "0"}>
                    <stop offset="5%" stopColor="#10b981" stopOpacity={0.8}/>
                    <stop offset="95%" stopColor="#10b981" stopOpacity={0.3}/>
                  </linearGradient>
                </defs>
                <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                <XAxis
                  dataKey="timestamp"
                  tickFormatter={formatXAxis}
                  angle={-45}
                  textAnchor="end"
                  height={60}
                  stroke="#888"
                />
                <YAxis
                  yAxisId="left"
                  label={{
                    value: 'Speed (Mbps)',
                    angle: -90,
                    position: 'insideLeft',
                    style: { fill: '#888', textAnchor: 'middle' }
                  }}
                  tickFormatter={formatYAxis}
                  stroke="#888"
                  domain={yDomain}
                  allowDataOverflow={yDomain[0] !== 'auto'}
                />
                <Tooltip
                  active={isSelecting ? false : undefined}
                  formatter={formatTooltip}
                  labelFormatter={(label) => {
                    const utcLabel = String(label).endsWith('Z') ? label : label + 'Z';
                    return formatInTimeZone(new Date(utcLabel), Intl.DateTimeFormat().resolvedOptions().timeZone, 'PPpp');
                  }}
                  contentStyle={{
                    backgroundColor: 'rgba(0, 0, 0, 0.9)',
                    border: '1px solid #666',
                    borderRadius: '4px'
                  }}
                />
                <Legend
                  content={<CustomLegend visibleSeries={visibleSeries} onToggle={(dataKey) => {
                    setVisibleSeries(prev => ({
                      ...prev,
                      [dataKey]: !prev[dataKey]
                    }));
                  }} />}
                />
                <ReferenceLine
                  yAxisId="left"
                  y={0}
                  stroke="#999"
                  strokeWidth={2}
                />
                {isSelecting && selectionStart !== null && selectionEnd !== null && (
                  <ReferenceArea
                    yAxisId="left"
                    x1={new Date(Math.min(selectionStart, selectionEnd)).toISOString().replace('Z', '')}
                    x2={new Date(Math.max(selectionStart, selectionEnd)).toISOString().replace('Z', '')}
                    fill="#3b82f6"
                    fillOpacity={0.15}
                    stroke="#3b82f6"
                    strokeOpacity={0.4}
                  />
                )}
                {/* Per-client-id download limit lines */}
                {series.map((s) => {
                  const info = getSeriesInfo(s.id);
                  return (
                    <Line
                      key={`${s.id}_download_limit_line`}
                      yAxisId="left"
                      type="monotone"
                      dataKey={`${s.id}_download_limit_line`}
                      stroke={info.color}
                      strokeDasharray="5 5"
                      strokeWidth={2}
                      dot={false}
                      name={`${info.name} DL Limit`}
                      isAnimationActive={true}
                      animationDuration={300}
                      animationEasing="ease-in-out"
                      connectNulls={true}
                      hide={!visibleSeries[`${s.id}_download_limit_line`]}
                    />
                  );
                })}
                {/* Per-client-id upload limit lines (upload-capable series only) */}
                {series.filter((s) => s.supportsUpload).map((s) => {
                  const info = getSeriesInfo(s.id);
                  return (
                    <Line
                      key={`${s.id}_upload_limit_line`}
                      yAxisId="left"
                      type="monotone"
                      dataKey={`${s.id}_upload_limit_line`}
                      stroke={info.color}
                      strokeDasharray="5 5"
                      strokeWidth={2}
                      dot={false}
                      name={`${info.name} UL Limit`}
                      isAnimationActive={true}
                      animationDuration={300}
                      animationEasing="ease-in-out"
                      connectNulls={true}
                      hide={!visibleSeries[`${s.id}_upload_limit_line`]}
                    />
                  );
                })}
                {/* SNMP Actual Bandwidth Lines - only shown when SNMP is enabled */}
                {snmpEnabled && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="snmp_download"
                    stroke="#8b5cf6"
                    strokeDasharray="5 5"
                    strokeWidth={3}
                    dot={false}
                    name="WAN Download (SNMP)"
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.snmp_download}
                  />
                )}
                {snmpEnabled && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="snmp_upload"
                    stroke="#8b5cf6"
                    strokeDasharray="5 5"
                    strokeWidth={3}
                    dot={false}
                    name="WAN Upload (SNMP)"
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.snmp_upload}
                  />
                )}
                {/* Download Areas (stacked positive) - order controlled by clientOrder */}
                {clientOrder.map((id) => {
                  const info = getSeriesInfo(id);
                  return (
                    <Area
                      key={`${id}_download`}
                      yAxisId="left"
                      type="monotone"
                      dataKey={`${id}_download`}
                      stackId={stackChart ? "download" : undefined}
                      stroke={info.color}
                      fill={`url(#${dlGradientId(id)})`}
                      name={`${info.name} Download`}
                      isAnimationActive={true}
                      animationDuration={300}
                      animationEasing="ease-in-out"
                      hide={!visibleSeries[`${id}_download`]}
                    />
                  );
                })}
                {/* Upload Areas (stacked negative) - WAN streams first, LAN never stacks, then clients */}
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="wan_streams"
                  stackId={stackChart ? "upload" : undefined}
                  stroke="#ff7300"
                  fill="url(#wanStreams)"
                  name="WAN Streams Bandwidth"
                  isAnimationActive={true}
                  animationDuration={300}
                  animationEasing="ease-in-out"
                  hide={!visibleSeries.wan_streams}
                />
                <Line
                  yAxisId="left"
                  type="monotone"
                  dataKey="lan_streams"
                  stroke="#10b981"
                  strokeDasharray="5 5"
                  strokeWidth={3}
                  dot={false}
                  name="LAN Streams Bandwidth"
                  isAnimationActive={true}
                  animationDuration={300}
                  animationEasing="ease-in-out"
                  connectNulls={true}
                  hide={!visibleSeries.lan_streams}
                />
                {clientOrder.map((id) => {
                  if (!seriesSupportsUpload(id)) return null;
                  const info = getSeriesInfo(id);
                  return (
                    <Area
                      key={`${id}_upload`}
                      yAxisId="left"
                      type="monotone"
                      dataKey={`${id}_upload`}
                      stackId={stackChart ? "upload" : undefined}
                      stroke={info.color}
                      fill={`url(#${ulGradientId(id)})`}
                      name={`${info.name} Upload`}
                      isAnimationActive={true}
                      animationDuration={300}
                      animationEasing="ease-in-out"
                      hide={!visibleSeries[`${id}_upload`]}
                    />
                  );
                })}
              </ComposedChart>
            </ResponsiveContainer>
          </div>
          {showPerServer && hasMultipleServers && (
            <div className="mt-6">
              <p className="text-sm font-medium text-muted-foreground mb-2">
                Stream bandwidth by media server (Mbps)
              </p>
              <ResponsiveContainer width="100%" height={200}>
                <LineChart
                  data={perServerPoints}
                  margin={{ top: 4, right: 10, left: 10, bottom: 20 }}
                >
                  <CartesianGrid strokeDasharray="3 3" stroke="#444" />
                  <XAxis
                    dataKey="timestamp"
                    tickFormatter={formatXAxis}
                    angle={-45}
                    textAnchor="end"
                    height={60}
                    stroke="#888"
                  />
                  <YAxis
                    tickFormatter={(v) => `${Number(v).toFixed(0)}`}
                    stroke="#888"
                    label={{
                      value: 'Mbps',
                      angle: -90,
                      position: 'insideLeft',
                      style: { fill: '#888', textAnchor: 'middle' },
                    }}
                  />
                  <Tooltip
                    formatter={(value: number, name: string) => [`${Number(value).toFixed(2)} Mbps`, name]}
                    labelFormatter={(label) => {
                      const utcLabel = String(label).endsWith('Z') ? label : label + 'Z';
                      return formatInTimeZone(new Date(utcLabel), Intl.DateTimeFormat().resolvedOptions().timeZone, 'PPpp');
                    }}
                    contentStyle={{
                      backgroundColor: 'rgba(0, 0, 0, 0.9)',
                      border: '1px solid #666',
                      borderRadius: '4px',
                    }}
                  />
                  <Legend />
                  {perServerSeries.map((serverId, idx) => (
                    <Line
                      key={serverId}
                      type="monotone"
                      dataKey={serverId}
                      name={mediaServerNames[serverId] ?? serverId}
                      stroke={PER_SERVER_COLORS[idx % PER_SERVER_COLORS.length]}
                      strokeWidth={2}
                      dot={false}
                      isAnimationActive={true}
                      animationDuration={300}
                      animationEasing="ease-in-out"
                      connectNulls={true}
                    />
                  ))}
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
          </>
        )}
      </CardContent>
    </Card>
  );
};

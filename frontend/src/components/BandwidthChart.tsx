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
  Line,
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
import { Loader2, AlertCircle, Layers, BarChart3, ArrowUpDown } from 'lucide-react';

// Gradient ID mapping for each client
const DOWNLOAD_GRADIENT_IDS: Record<string, string> = {
  qbittorrent: 'qbDownload',
  sabnzbd: 'sabDownload',
  nzbget: 'nzbgetDownload',
  transmission: 'transmissionDownload',
  deluge: 'delugeDownload',
};

const UPLOAD_GRADIENT_IDS: Record<string, string> = {
  qbittorrent: 'qbUpload',
  transmission: 'transmissionUpload',
  deluge: 'delugeUpload',
};

interface DownloadClient {
  id: string;
  type: string;
  name: string;
  enabled: boolean;
  color: string;
  supports_upload: boolean;
}

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

  // Define which series are "download" type vs "upload" type
  const downloadKeys = [
    'qbittorrent_download', 'sabnzbd_download', 'nzbget_download', 'transmission_download', 'deluge_download',
    'qbittorrent_download_limit_line', 'sabnzbd_download_limit_line', 'nzbget_download_limit_line',
    'transmission_download_limit_line', 'deluge_download_limit_line', 'snmp_download'
  ];
  // uploadKeys used for categorization - items not in downloadKeys are considered uploads
  const _uploadKeys = [
    'qbittorrent_upload', 'transmission_upload', 'deluge_upload', 'plex_streams',
    'qbittorrent_upload_limit_line', 'transmission_upload_limit_line', 'deluge_upload_limit_line', 'snmp_upload'
  ];
  void _uploadKeys; // Suppress unused variable warning

  // Sort payload: downloads first (alphabetically by name), then uploads (alphabetically by name)
  const sortedPayload = [...payload].sort((a, b) => {
    const aIsDownload = downloadKeys.includes(a.dataKey);
    const bIsDownload = downloadKeys.includes(b.dataKey);

    // Downloads come before uploads
    if (aIsDownload && !bIsDownload) return -1;
    if (!aIsDownload && bIsDownload) return 1;

    // Within same category, sort alphabetically by display name
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
}

// Default visible series configuration
const defaultVisibleSeries: Record<string, boolean> = {
  // Download speeds
  qbittorrent_download: true,
  sabnzbd_download: true,
  nzbget_download: true,
  transmission_download: true,
  deluge_download: true,
  // Upload speeds
  qbittorrent_upload: true,
  transmission_upload: true,
  deluge_upload: true,
  plex_streams: true,
  // Download limits
  qbittorrent_download_limit_line: false,
  sabnzbd_download_limit_line: false,
  nzbget_download_limit_line: false,
  transmission_download_limit_line: false,
  deluge_download_limit_line: false,
  // Upload limits
  qbittorrent_upload_limit_line: false,
  transmission_upload_limit_line: false,
  deluge_upload_limit_line: false,
  // SNMP
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
}) => {
  const [rawData, setRawData] = useState<ChartDataPoint[]>([]);
  const [data, setData] = useState<ChartDataPoint[]>([]);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [error, setError] = useState('');
  const [scalingRatio, setScalingRatio] = useState(1);
  const [visibleSeries, setVisibleSeries] = useState<Record<string, boolean>>(loadVisibleSeries);
  const [downloadClients, setDownloadClients] = useState<DownloadClient[]>([]);
  const [snmpEnabled, setSnmpEnabled] = useState<boolean>(false);
  const [stackChart, setStackChart] = useState<boolean>(() => {
    const saved = localStorage.getItem('speedarr_chart_stacked');
    return saved !== null ? JSON.parse(saved) : false;
  });
  const [flipped, setFlipped] = useState<boolean>(() => {
    const saved = localStorage.getItem('speedarr_chart_flipped');
    return saved !== null ? JSON.parse(saved) : false;
  });
  const [clientOrder, setClientOrder] = useState<string[]>(() => {
    try {
      const saved = localStorage.getItem('speedarr_chart_client_order');
      if (saved) return JSON.parse(saved);
    } catch {}
    return [];
  });

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

        // Build client list from status response
        const clientMap = new Map<string, DownloadClient>();
        const dlClients = status.bandwidth?.download?.clients || [];
        const ulClients = status.bandwidth?.upload?.clients || [];

        if (dlClients.length === 0 && ulClients.length === 0) {
          console.warn('[BandwidthChart] Status response returned 0 clients. Response status:', status.status);
        }

        for (const c of dlClients) {
          clientMap.set(c.type, {
            id: c.type, type: c.type, name: c.name,
            enabled: true, color: c.color, supports_upload: false,
          });
        }
        for (const c of ulClients) {
          if (clientMap.has(c.type)) {
            clientMap.get(c.type)!.supports_upload = true;
          } else {
            clientMap.set(c.type, {
              id: c.type, type: c.type, name: c.name,
              enabled: true, color: c.color, supports_upload: true,
            });
          }
        }
        const clients = Array.from(clientMap.values());
        setDownloadClients(clients);

        // Compute client order immediately (same batch)
        const enabledTypes = clients.map(c => c.type);
        setClientOrder(prev => {
          const kept = prev.filter(t => enabledTypes.includes(t));
          const newClients = enabledTypes.filter(t => !kept.includes(t));
          return kept.length > 0 ? [...kept, ...newClients] : enabledTypes;
        });

        setSnmpEnabled(status.snmp_enabled ?? false);
      } catch (err) {
        console.error('Failed to load client info:', err);
      }
    };
    loadClientInfo();
  }, []);

  // Reconcile clientOrder with actual enabled clients
  useEffect(() => {
    if (downloadClients.length === 0) return;
    const enabledTypes = downloadClients.map(c => c.type);
    setClientOrder(prev => {
      const kept = prev.filter(t => enabledTypes.includes(t));
      const newClients = enabledTypes.filter(t => !kept.includes(t));
      const merged = [...kept, ...newClients];
      if (merged.length === prev.length && merged.every((t, i) => t === prev[i])) return prev;
      return merged;
    });
  }, [downloadClients]);

  // Get client info by type with fallback defaults
  const getClientInfo = useMemo(() => {
    const defaults: Record<string, { name: string; color: string }> = {
      qbittorrent: { name: 'qBittorrent', color: '#3b82f6' },
      sabnzbd: { name: 'SABnzbd', color: '#facc15' },
      nzbget: { name: 'NZBGet', color: '#22c55e' },
      transmission: { name: 'Transmission', color: '#ef4444' },
      deluge: { name: 'Deluge', color: '#8b5cf6' },
    };

    return (type: string) => {
      const client = downloadClients.find(c => c.type === type);
      if (client) {
        return { name: client.name, color: client.color };
      }
      return defaults[type] || { name: type, color: '#888888' };
    };
  }, [downloadClients]);

  // Memoize client info lookups to avoid recalculating on every render
  const clientInfos = useMemo(() => ({
    qbittorrent: getClientInfo('qbittorrent'),
    sabnzbd: getClientInfo('sabnzbd'),
    nzbget: getClientInfo('nzbget'),
    transmission: getClientInfo('transmission'),
    deluge: getClientInfo('deluge'),
  }), [getClientInfo]);

  const qbitInfo = clientInfos.qbittorrent;
  const sabInfo = clientInfos.sabnzbd;
  const nzbgetInfo = clientInfos.nzbget;
  const transmissionInfo = clientInfos.transmission;
  const delugeInfo = clientInfos.deluge;

  // Check if a client type is enabled
  const isClientEnabled = useMemo(() => {
    return (type: string) => {
      const client = downloadClients.find(c => c.type === type);
      return client?.enabled ?? false;
    };
  }, [downloadClients]);

  // Check if a client supports upload
  const clientSupportsUpload = useMemo(() => {
    return (type: string) => {
      const client = downloadClients.find(c => c.type === type);
      return client?.supports_upload ?? false;
    };
  }, [downloadClients]);

  // Check if all data series are hidden (only check enabled clients)
  const allMetricsHidden = useMemo(() => {
    // Build list of keys that are actually visible in the legend
    const activeKeys: string[] = [];

    // Download clients - only include if enabled
    if (isClientEnabled('qbittorrent')) activeKeys.push('qbittorrent_download');
    if (isClientEnabled('sabnzbd')) activeKeys.push('sabnzbd_download');
    if (isClientEnabled('nzbget')) activeKeys.push('nzbget_download');
    if (isClientEnabled('transmission')) activeKeys.push('transmission_download');
    if (isClientEnabled('deluge')) activeKeys.push('deluge_download');

    // Upload clients - only include if enabled and supports upload
    if (isClientEnabled('qbittorrent') && clientSupportsUpload('qbittorrent')) activeKeys.push('qbittorrent_upload');
    if (isClientEnabled('transmission') && clientSupportsUpload('transmission')) activeKeys.push('transmission_upload');
    if (isClientEnabled('deluge') && clientSupportsUpload('deluge')) activeKeys.push('deluge_upload');

    // Plex streams are always shown
    activeKeys.push('plex_streams');

    // SNMP is only shown in legend when SNMP is enabled
    if (snmpEnabled) {
      activeKeys.push('snmp_download', 'snmp_upload');
    }

    // If no clients are enabled at all, don't show the message
    if (activeKeys.length === 0) return false;

    return activeKeys.every(key => !visibleSeries[key]);
  }, [visibleSeries, isClientEnabled, clientSupportsUpload, snmpEnabled]);

  // Save visible series to localStorage when it changes
  useEffect(() => {
    try {
      localStorage.setItem('speedarr_chart_visible_series', JSON.stringify(visibleSeries));
    } catch (e) {
      console.error('Failed to save chart preferences:', e);
    }
  }, [visibleSeries]);

  // Memoize aggregation - only recomputes when rawData or dataInterval changes
  const aggregatedData = useMemo(() => {
    if (rawData.length === 0) return [];
    if (dataInterval === 'raw') return rawData;

    const intervalMinutes = dataInterval as number;
    const intervalMs = intervalMinutes * 60 * 1000;
    const buckets: Map<number, ChartDataPoint[]> = new Map();

    // Group data points into time buckets
    rawData.forEach((point) => {
      const timestamp = new Date(point.timestamp).getTime();
      const bucketKey = Math.floor(timestamp / intervalMs) * intervalMs;

      if (!buckets.has(bucketKey)) {
        buckets.set(bucketKey, []);
      }
      buckets.get(bucketKey)!.push(point);
    });

    // Average each bucket, including limits
    const aggregated = Array.from(buckets.entries()).map(([bucketTime, points]) => {
      const avg = {
        timestamp: new Date(bucketTime).toISOString(),
        download_speed: points.reduce((sum, p) => sum + (p.download_speed || 0), 0) / points.length,
        // Per-client download speeds
        qbittorrent_speed: points.reduce((sum, p) => sum + (p.qbittorrent_speed || 0), 0) / points.length,
        sabnzbd_speed: points.reduce((sum, p) => sum + (p.sabnzbd_speed || 0), 0) / points.length,
        nzbget_speed: points.reduce((sum, p) => sum + (p.nzbget_speed || 0), 0) / points.length,
        transmission_speed: points.reduce((sum, p) => sum + (p.transmission_speed || 0), 0) / points.length,
        deluge_speed: points.reduce((sum, p) => sum + (p.deluge_speed || 0), 0) / points.length,
        upload_speed: points.reduce((sum, p) => sum + (p.upload_speed || 0), 0) / points.length,
        // Per-client upload speeds
        qbittorrent_upload_speed: points.reduce((sum, p) => sum + (p.qbittorrent_upload_speed || 0), 0) / points.length,
        transmission_upload_speed: points.reduce((sum, p) => sum + (p.transmission_upload_speed || 0), 0) / points.length,
        deluge_upload_speed: points.reduce((sum, p) => sum + (p.deluge_upload_speed || 0), 0) / points.length,
        stream_bandwidth: points.reduce((sum, p) => sum + (p.stream_bandwidth || 0), 0) / points.length,
        active_streams_count: points.reduce((sum, p) => sum + (p.active_streams_count || 0), 0) / points.length,
        // Per-client download limits
        qbittorrent_download_limit: points.reduce((sum, p) => sum + (p.qbittorrent_download_limit || 0), 0) / points.length,
        sabnzbd_download_limit: points.reduce((sum, p) => sum + (p.sabnzbd_download_limit || 0), 0) / points.length,
        nzbget_download_limit: points.reduce((sum, p) => sum + (p.nzbget_download_limit || 0), 0) / points.length,
        transmission_download_limit: points.reduce((sum, p) => sum + (p.transmission_download_limit || 0), 0) / points.length,
        deluge_download_limit: points.reduce((sum, p) => sum + (p.deluge_download_limit || 0), 0) / points.length,
        // Per-client upload limits
        qbittorrent_upload_limit: points.reduce((sum, p) => sum + (p.qbittorrent_upload_limit || 0), 0) / points.length,
        transmission_upload_limit: points.reduce((sum, p) => sum + (p.transmission_upload_limit || 0), 0) / points.length,
        deluge_upload_limit: points.reduce((sum, p) => sum + (p.deluge_upload_limit || 0), 0) / points.length,
        // Average SNMP data
        snmp_download_speed: points.reduce((sum, p) => sum + (p.snmp_download_speed || 0), 0) / points.length,
        snmp_upload_speed: points.reduce((sum, p) => sum + (p.snmp_upload_speed || 0), 0) / points.length,
      };
      return avg;
    });

    return aggregated.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  }, [rawData, dataInterval]);

  const fetchData = useCallback(async () => {
    setError('');
    try {
      // Fetch chart data with per-datapoint limits
      const chartResponse = await apiClient.getBandwidthChartData({
        hours: timeRange.hours,
        interval_minutes: 1,
      });

      setRawData(chartResponse.data);
    } catch (err) {
      setError('Failed to load bandwidth data');
      console.error('Error fetching bandwidth chart data:', err);
    } finally {
      setIsInitialLoad(false);
    }
  }, [timeRange.hours]);

  // Memoize transformed chart data - depends on aggregated data and visibleSeries for scaling
  const transformedData = useMemo(() => {
    if (aggregatedData.length === 0) return { data: [], ratio: 1 };

    // Find max values for scaling - only include visible series
    // When flipped, uploads are positive (on top) and downloads are negated (below zero)
    let maxPositive = 0;
    let maxToNegate = 0;

    aggregatedData.forEach((point) => {
      // Compute download totals from visible series
      let totalDownload = 0;
      if (visibleSeries.qbittorrent_download) totalDownload += point.qbittorrent_speed || 0;
      if (visibleSeries.sabnzbd_download) totalDownload += point.sabnzbd_speed || 0;
      if (visibleSeries.nzbget_download) totalDownload += point.nzbget_speed || 0;
      if (visibleSeries.transmission_download) totalDownload += point.transmission_speed || 0;
      if (visibleSeries.deluge_download) totalDownload += point.deluge_speed || 0;

      const snmpDownloadVal = visibleSeries.snmp_download ? (point.snmp_download_speed || 0) : 0;

      // Compute upload totals from visible series
      let totalUpload = 0;
      if (visibleSeries.plex_streams) totalUpload += point.stream_bandwidth || 0;
      if (visibleSeries.qbittorrent_upload) totalUpload += point.qbittorrent_upload_speed || 0;
      if (visibleSeries.transmission_upload) totalUpload += point.transmission_upload_speed || 0;
      if (visibleSeries.deluge_upload) totalUpload += point.deluge_upload_speed || 0;

      const snmpUploadVal = visibleSeries.snmp_upload ? (point.snmp_upload_speed || 0) : 0;

      // Include upload limits only if their respective limit lines are visible
      let maxUploadLimit = 0;
      if (visibleSeries.qbittorrent_upload_limit_line) maxUploadLimit = Math.max(maxUploadLimit, point.qbittorrent_upload_limit || 0);
      if (visibleSeries.transmission_upload_limit_line) maxUploadLimit = Math.max(maxUploadLimit, point.transmission_upload_limit || 0);
      if (visibleSeries.deluge_upload_limit_line) maxUploadLimit = Math.max(maxUploadLimit, point.deluge_upload_limit || 0);

      if (flipped) {
        // Uploads on top (positive), downloads negated
        maxPositive = Math.max(maxPositive, totalUpload, snmpUploadVal, maxUploadLimit);
        maxToNegate = Math.max(maxToNegate, totalDownload, snmpDownloadVal);
      } else {
        // Downloads on top (positive), uploads negated
        maxPositive = Math.max(maxPositive, totalDownload, snmpDownloadVal);
        maxToNegate = Math.max(maxToNegate, totalUpload, snmpUploadVal, maxUploadLimit);
      }
    });

    // Calculate scaling ratio
    const ratio = (maxPositive > 0 && maxToNegate > 0) ? maxPositive / maxToNegate : 1;

    // Transform data and include limits as line data
    // When flipped, uploads stay positive and downloads get negated+scaled (and vice versa)
    const chartData = aggregatedData.map((point) => ({
      ...point,
      // Download series
      qbittorrent_download: flipped ? -Math.abs(point.qbittorrent_speed || 0) * ratio : (point.qbittorrent_speed || 0),
      sabnzbd_download: flipped ? -Math.abs(point.sabnzbd_speed || 0) * ratio : (point.sabnzbd_speed || 0),
      nzbget_download: flipped ? -Math.abs(point.nzbget_speed || 0) * ratio : (point.nzbget_speed || 0),
      transmission_download: flipped ? -Math.abs(point.transmission_speed || 0) * ratio : (point.transmission_speed || 0),
      deluge_download: flipped ? -Math.abs(point.deluge_speed || 0) * ratio : (point.deluge_speed || 0),
      // Upload series
      plex_streams: flipped ? Math.abs(point.stream_bandwidth || 0) : -Math.abs(point.stream_bandwidth || 0) * ratio,
      qbittorrent_upload: flipped ? Math.abs(point.qbittorrent_upload_speed || 0) : -Math.abs(point.qbittorrent_upload_speed || 0) * ratio,
      transmission_upload: flipped ? Math.abs(point.transmission_upload_speed || 0) : -Math.abs(point.transmission_upload_speed || 0) * ratio,
      deluge_upload: flipped ? Math.abs(point.deluge_upload_speed || 0) : -Math.abs(point.deluge_upload_speed || 0) * ratio,
      // Download limit lines
      qbittorrent_download_limit_line: flipped ? (point.qbittorrent_download_limit ? -Math.abs(point.qbittorrent_download_limit) * ratio : null) : (point.qbittorrent_download_limit || null),
      sabnzbd_download_limit_line: flipped ? (point.sabnzbd_download_limit ? -Math.abs(point.sabnzbd_download_limit) * ratio : null) : (point.sabnzbd_download_limit || null),
      nzbget_download_limit_line: flipped ? (point.nzbget_download_limit ? -Math.abs(point.nzbget_download_limit) * ratio : null) : (point.nzbget_download_limit || null),
      transmission_download_limit_line: flipped ? (point.transmission_download_limit ? -Math.abs(point.transmission_download_limit) * ratio : null) : (point.transmission_download_limit || null),
      deluge_download_limit_line: flipped ? (point.deluge_download_limit ? -Math.abs(point.deluge_download_limit) * ratio : null) : (point.deluge_download_limit || null),
      // Upload limit lines
      qbittorrent_upload_limit_line: flipped ? (point.qbittorrent_upload_limit || null) : (point.qbittorrent_upload_limit ? -Math.abs(point.qbittorrent_upload_limit) * ratio : null),
      transmission_upload_limit_line: flipped ? (point.transmission_upload_limit || null) : (point.transmission_upload_limit ? -Math.abs(point.transmission_upload_limit) * ratio : null),
      deluge_upload_limit_line: flipped ? (point.deluge_upload_limit || null) : (point.deluge_upload_limit ? -Math.abs(point.deluge_upload_limit) * ratio : null),
      // SNMP bandwidth
      snmp_download: flipped ? (point.snmp_download_speed ? -Math.abs(point.snmp_download_speed) * ratio : null) : (point.snmp_download_speed ?? null),
      snmp_upload: flipped ? (point.snmp_upload_speed ?? null) : (point.snmp_upload_speed ? -Math.abs(point.snmp_upload_speed) * ratio : null),
    }));

    return { data: chartData, ratio };
  }, [aggregatedData, visibleSeries, stackChart, flipped]);

  // Update state from memoized values
  useEffect(() => {
    setData(transformedData.data);
    setScalingRatio(transformedData.ratio);
  }, [transformedData]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [fetchData]);


  const formatXAxis = (timestamp: string) => {
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // Ensure timestamp is parsed as UTC (API returns UTC without 'Z' suffix)
    const utcTimestamp = timestamp.endsWith('Z') ? timestamp : timestamp + 'Z';
    if (timeRange.hours <= 6) {
      return formatInTimeZone(new Date(utcTimestamp), tz, 'HH:mm');
    } else if (timeRange.hours <= 24) {
      return formatInTimeZone(new Date(utcTimestamp), tz, 'HH:mm');
    } else {
      return formatInTimeZone(new Date(utcTimestamp), tz, 'MM/dd HH:mm');
    }
  };

  const formatTooltip = (value: number, name: string) => {
    // Show absolute value for uploads/streams (they're stored as negative and scaled)
    let absValue = Math.abs(value);

    // If this is upload or stream (negative value), unscale it
    if (value < 0 && scalingRatio !== 1) {
      absValue = absValue / scalingRatio;
    }

    return [`${absValue.toFixed(2)} Mbps`, name];
  };

  const formatYAxis = (value: number) => {
    // For negative values (upload/stream), unscale them for display
    if (value < 0 && scalingRatio !== 1) {
      return (Math.abs(value) / scalingRatio).toFixed(0);
    }
    return Math.abs(value).toFixed(0);
  };

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
                    {clientOrder.map((clientType) => (
                      <SelectItem key={clientType} value={clientType}>
                        {getClientInfo(clientType).name} first (bottom)
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
              <SelectTrigger className="w-[140px]" aria-label="Select time range for chart data">
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
          <ResponsiveContainer width="100%" height={700}>
              <ComposedChart
                data={data}
                margin={{ top: 10, right: 10, left: 10, bottom: 20 }}
                stackOffset="sign"
              >
                <defs>
                  {/* Download gradients - only for enabled clients */}
                  {isClientEnabled('qbittorrent') && (
                    <linearGradient id="qbDownload" x1="0" y1={flipped ? "1" : "0"} x2="0" y2={flipped ? "0" : "1"}>
                      <stop offset="5%" stopColor={qbitInfo.color} stopOpacity={0.8}/>
                      <stop offset="95%" stopColor={qbitInfo.color} stopOpacity={0.3}/>
                    </linearGradient>
                  )}
                  {isClientEnabled('sabnzbd') && (
                    <linearGradient id="sabDownload" x1="0" y1={flipped ? "1" : "0"} x2="0" y2={flipped ? "0" : "1"}>
                      <stop offset="5%" stopColor={sabInfo.color} stopOpacity={0.8}/>
                      <stop offset="95%" stopColor={sabInfo.color} stopOpacity={0.3}/>
                    </linearGradient>
                  )}
                  {isClientEnabled('nzbget') && (
                    <linearGradient id="nzbgetDownload" x1="0" y1={flipped ? "1" : "0"} x2="0" y2={flipped ? "0" : "1"}>
                      <stop offset="5%" stopColor={nzbgetInfo.color} stopOpacity={0.8}/>
                      <stop offset="95%" stopColor={nzbgetInfo.color} stopOpacity={0.3}/>
                    </linearGradient>
                  )}
                  {isClientEnabled('transmission') && (
                    <linearGradient id="transmissionDownload" x1="0" y1={flipped ? "1" : "0"} x2="0" y2={flipped ? "0" : "1"}>
                      <stop offset="5%" stopColor={transmissionInfo.color} stopOpacity={0.8}/>
                      <stop offset="95%" stopColor={transmissionInfo.color} stopOpacity={0.3}/>
                    </linearGradient>
                  )}
                  {isClientEnabled('deluge') && (
                    <linearGradient id="delugeDownload" x1="0" y1={flipped ? "1" : "0"} x2="0" y2={flipped ? "0" : "1"}>
                      <stop offset="5%" stopColor={delugeInfo.color} stopOpacity={0.8}/>
                      <stop offset="95%" stopColor={delugeInfo.color} stopOpacity={0.3}/>
                    </linearGradient>
                  )}
                  {/* Upload gradients - only for enabled clients that support upload */}
                  {isClientEnabled('qbittorrent') && clientSupportsUpload('qbittorrent') && (
                    <linearGradient id="qbUpload" x1="0" y1={flipped ? "0" : "1"} x2="0" y2={flipped ? "1" : "0"}>
                      <stop offset="5%" stopColor={qbitInfo.color} stopOpacity={0.8}/>
                      <stop offset="95%" stopColor={qbitInfo.color} stopOpacity={0.3}/>
                    </linearGradient>
                  )}
                  {isClientEnabled('transmission') && clientSupportsUpload('transmission') && (
                    <linearGradient id="transmissionUpload" x1="0" y1={flipped ? "0" : "1"} x2="0" y2={flipped ? "1" : "0"}>
                      <stop offset="5%" stopColor={transmissionInfo.color} stopOpacity={0.8}/>
                      <stop offset="95%" stopColor={transmissionInfo.color} stopOpacity={0.3}/>
                    </linearGradient>
                  )}
                  {isClientEnabled('deluge') && clientSupportsUpload('deluge') && (
                    <linearGradient id="delugeUpload" x1="0" y1={flipped ? "0" : "1"} x2="0" y2={flipped ? "1" : "0"}>
                      <stop offset="5%" stopColor={delugeInfo.color} stopOpacity={0.8}/>
                      <stop offset="95%" stopColor={delugeInfo.color} stopOpacity={0.3}/>
                    </linearGradient>
                  )}
                  {/* Plex streams gradient - always shown */}
                  <linearGradient id="plexStreams" x1="0" y1={flipped ? "0" : "1"} x2="0" y2={flipped ? "1" : "0"}>
                    <stop offset="5%" stopColor="#ff7300" stopOpacity={0.8}/>
                    <stop offset="95%" stopColor="#ff7300" stopOpacity={0.3}/>
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
                  domain={['auto', 'auto']}
                />
                <Tooltip
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
                {/* Per-client download limit lines - only show for enabled clients */}
                {isClientEnabled('qbittorrent') && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="qbittorrent_download_limit_line"
                    stroke={qbitInfo.color}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    name={`${qbitInfo.name} DL Limit`}
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.qbittorrent_download_limit_line}
                  />
                )}
                {isClientEnabled('sabnzbd') && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="sabnzbd_download_limit_line"
                    stroke={sabInfo.color}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    name={`${sabInfo.name} DL Limit`}
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.sabnzbd_download_limit_line}
                  />
                )}
                {isClientEnabled('nzbget') && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="nzbget_download_limit_line"
                    stroke={nzbgetInfo.color}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    name={`${nzbgetInfo.name} DL Limit`}
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.nzbget_download_limit_line}
                  />
                )}
                {isClientEnabled('transmission') && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="transmission_download_limit_line"
                    stroke={transmissionInfo.color}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    name={`${transmissionInfo.name} DL Limit`}
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.transmission_download_limit_line}
                  />
                )}
                {isClientEnabled('deluge') && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="deluge_download_limit_line"
                    stroke={delugeInfo.color}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    name={`${delugeInfo.name} DL Limit`}
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.deluge_download_limit_line}
                  />
                )}
                {/* Per-client upload limit lines - only show for enabled clients that support upload */}
                {isClientEnabled('qbittorrent') && clientSupportsUpload('qbittorrent') && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="qbittorrent_upload_limit_line"
                    stroke={qbitInfo.color}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    name={`${qbitInfo.name} UL Limit`}
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.qbittorrent_upload_limit_line}
                  />
                )}
                {isClientEnabled('transmission') && clientSupportsUpload('transmission') && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="transmission_upload_limit_line"
                    stroke={transmissionInfo.color}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    name={`${transmissionInfo.name} UL Limit`}
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.transmission_upload_limit_line}
                  />
                )}
                {isClientEnabled('deluge') && clientSupportsUpload('deluge') && (
                  <Line
                    yAxisId="left"
                    type="monotone"
                    dataKey="deluge_upload_limit_line"
                    stroke={delugeInfo.color}
                    strokeDasharray="5 5"
                    strokeWidth={2}
                    dot={false}
                    name={`${delugeInfo.name} UL Limit`}
                    isAnimationActive={true}
                    animationDuration={300}
                    animationEasing="ease-in-out"
                    connectNulls={true}
                    hide={!visibleSeries.deluge_upload_limit_line}
                  />
                )}
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
                {/* Download Areas (stacked positive) - order controlled by stackOrder */}
                {clientOrder.map((clientType) => {
                  if (!isClientEnabled(clientType)) return null;
                  const info = getClientInfo(clientType);
                  const gradientId = DOWNLOAD_GRADIENT_IDS[clientType];
                  return (
                    <Area
                      key={`${clientType}_download`}
                      yAxisId="left"
                      type="monotone"
                      dataKey={`${clientType}_download`}
                      stackId={stackChart ? "download" : undefined}
                      stroke={info.color}
                      fill={`url(#${gradientId})`}
                      name={`${info.name} Download`}
                      isAnimationActive={true}
                      animationDuration={300}
                      animationEasing="ease-in-out"
                      hide={!visibleSeries[`${clientType}_download`]}
                    />
                  );
                })}
                {/* Upload Areas (stacked negative) - Plex always first, then clients in stack order */}
                <Area
                  yAxisId="left"
                  type="monotone"
                  dataKey="plex_streams"
                  stackId={stackChart ? "upload" : undefined}
                  stroke="#ff7300"
                  fill="url(#plexStreams)"
                  name="Plex Streams Bitrate"
                  isAnimationActive={true}
                  animationDuration={300}
                  animationEasing="ease-in-out"
                  hide={!visibleSeries.plex_streams}
                />
                {clientOrder.map((clientType) => {
                  if (!isClientEnabled(clientType) || !clientSupportsUpload(clientType)) return null;
                  const gradientId = UPLOAD_GRADIENT_IDS[clientType];
                  if (!gradientId) return null;
                  const info = getClientInfo(clientType);
                  return (
                    <Area
                      key={`${clientType}_upload`}
                      yAxisId="left"
                      type="monotone"
                      dataKey={`${clientType}_upload`}
                      stackId={stackChart ? "upload" : undefined}
                      stroke={info.color}
                      fill={`url(#${gradientId})`}
                      name={`${info.name} Upload`}
                      isAnimationActive={true}
                      animationDuration={300}
                      animationEasing="ease-in-out"
                      hide={!visibleSeries[`${clientType}_upload`]}
                    />
                  );
                })}
              </ComposedChart>
            </ResponsiveContainer>
          </>
        )}
      </CardContent>
    </Card>
  );
};

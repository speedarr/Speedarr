import React, { useState, useEffect, useMemo } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  Legend,
  ResponsiveContainer,
} from 'recharts';
import { formatInTimeZone } from 'date-fns-tz';
import { apiClient } from '@/api/client';
import type { ChartDataPoint } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle } from 'lucide-react';
import type { TimeRange, DataInterval } from './BandwidthChart';
import { filterDataByZoomRange, type ZoomRange } from '@/hooks/useChartZoom';

interface StreamCountChartProps {
  timeRange: TimeRange;
  dataInterval: DataInterval;
  zoomRange?: ZoomRange | null;
}

export const StreamCountChart: React.FC<StreamCountChartProps> = ({ timeRange, dataInterval, zoomRange }) => {
  const [rawData, setRawData] = useState<ChartDataPoint[]>([]);
  const [data, setData] = useState<any[]>([]);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [error, setError] = useState('');
  const [visibleSeries, setVisibleSeries] = useState<Record<string, boolean>>({
    wan_streams: true,
    lan_streams: true,
  });

  const aggregateData = (rawPoints: ChartDataPoint[], intervalMinutes: number) => {
    if (rawPoints.length === 0) return [];

    const intervalMs = intervalMinutes * 60 * 1000;
    const buckets: Map<number, ChartDataPoint[]> = new Map();

    // Group data points into time buckets
    rawPoints.forEach((point) => {
      const timestamp = new Date(point.timestamp).getTime();
      const bucketKey = Math.floor(timestamp / intervalMs) * intervalMs;

      if (!buckets.has(bucketKey)) {
        buckets.set(bucketKey, []);
      }
      buckets.get(bucketKey)!.push(point);
    });

    // Average stream counts in each bucket
    const aggregated = Array.from(buckets.entries()).map(([bucketTime, points]) => {
      // WAN: use wan_streams_count if available, fall back to active_streams_count for old data
      const avgWan = points.reduce((sum, p) => sum + (p.wan_streams_count != null ? p.wan_streams_count : (p.active_streams_count || 0)), 0) / points.length;
      const avgLan = points.reduce((sum, p) => sum + (p.lan_streams_count || 0), 0) / points.length;
      return {
        timestamp: new Date(bucketTime).toISOString(),
        wan_streams: Math.round(avgWan),
        lan_streams: Math.round(avgLan),
      };
    });

    return aggregated.sort((a, b) => new Date(a.timestamp).getTime() - new Date(b.timestamp).getTime());
  };

  const fetchData = async () => {
    setError('');
    try {
      const chartResponse = await apiClient.getBandwidthChartData({
        hours: timeRange.hours,
        interval_minutes: 1,
      });

      setRawData(chartResponse.data);
    } catch (err) {
      setError('Failed to load stream count data');
      console.error('Error fetching stream count data:', err);
    } finally {
      setIsInitialLoad(false);
    }
  };

  // Apply zoom filter before processing
  const zoomedRawData = useMemo(() => filterDataByZoomRange(rawData, zoomRange ?? null), [rawData, zoomRange]);

  // Process data when interval changes or zoomed data updates
  useEffect(() => {
    if (zoomedRawData.length === 0) {
      setData([]);
      return;
    }

    // Aggregate or use raw data based on interval
    const processedData = dataInterval === 'raw'
      ? zoomedRawData.map(point => ({
          timestamp: point.timestamp,
          // Backward compat: wan falls back to combined count for old data
          wan_streams: point.wan_streams_count != null ? point.wan_streams_count : (point.active_streams_count || 0),
          lan_streams: point.lan_streams_count || 0,
        }))
      : aggregateData(zoomedRawData, dataInterval);

    setData(processedData);
  }, [zoomedRawData, dataInterval]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [timeRange.hours]);

  // Calculate zoomed duration for XAxis formatting
  const zoomedDurationHours = useMemo(() => {
    if (!zoomRange || zoomedRawData.length < 2) return null;
    const first = new Date((zoomedRawData[0].timestamp.endsWith('Z') ? zoomedRawData[0].timestamp : zoomedRawData[0].timestamp + 'Z')).getTime();
    const last = new Date((zoomedRawData[zoomedRawData.length - 1].timestamp.endsWith('Z') ? zoomedRawData[zoomedRawData.length - 1].timestamp : zoomedRawData[zoomedRawData.length - 1].timestamp + 'Z')).getTime();
    return (last - first) / (1000 * 60 * 60);
  }, [zoomRange, zoomedRawData]);

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

  const handleLegendClick = (e: any) => {
    const dataKey = e.dataKey;
    if (dataKey) {
      setVisibleSeries(prev => ({ ...prev, [dataKey]: !prev[dataKey] }));
    }
  };

  return (
    <Card>
      <CardHeader>
        <CardTitle>Plex Streams</CardTitle>
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
            <AlertDescription>No stream count data available for the selected time range.</AlertDescription>
          </Alert>
        ) : (
          <ResponsiveContainer width="100%" height={400}>
            <LineChart
              data={data}
              margin={{ top: 10, right: 10, left: 10, bottom: 20 }}
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
                label={{
                  value: 'Active Streams',
                  angle: -90,
                  position: 'insideLeft',
                  style: { fill: '#888', textAnchor: 'middle' }
                }}
                stroke="#888"
                allowDecimals={false}
              />
              <Tooltip
                labelFormatter={(label) => {
                  const utcLabel = String(label).endsWith('Z') ? label : label + 'Z';
                  return formatInTimeZone(new Date(utcLabel), Intl.DateTimeFormat().resolvedOptions().timeZone, 'PPpp');
                }}
                formatter={(value: number, name: string) => [value, name]}
                contentStyle={{
                  backgroundColor: 'rgba(0, 0, 0, 0.9)',
                  border: '1px solid #666',
                  borderRadius: '4px'
                }}
              />
              <Legend onClick={handleLegendClick} />
              <Line
                type="monotone"
                dataKey="wan_streams"
                stroke="#ff7300"
                strokeWidth={2}
                dot={{ fill: '#ff7300', r: 3 }}
                name="WAN Streams"
                isAnimationActive={true}
                animationDuration={300}
                animationEasing="ease-in-out"
                hide={!visibleSeries.wan_streams}
              />
              <Line
                type="monotone"
                dataKey="lan_streams"
                stroke="#10b981"
                strokeWidth={2}
                dot={{ fill: '#10b981', r: 3 }}
                name="LAN Streams"
                isAnimationActive={true}
                animationDuration={300}
                animationEasing="ease-in-out"
                hide={!visibleSeries.lan_streams}
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
};

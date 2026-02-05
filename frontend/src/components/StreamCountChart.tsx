import React, { useState, useEffect } from 'react';
import {
  LineChart,
  Line,
  XAxis,
  YAxis,
  CartesianGrid,
  Tooltip,
  ResponsiveContainer,
} from 'recharts';
import { formatInTimeZone } from 'date-fns-tz';
import { apiClient } from '@/api/client';
import type { ChartDataPoint } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle } from 'lucide-react';
import type { TimeRange, DataInterval } from './BandwidthChart';

interface StreamCountChartProps {
  timeRange: TimeRange;
  dataInterval: DataInterval;
}

export const StreamCountChart: React.FC<StreamCountChartProps> = ({ timeRange, dataInterval }) => {
  const [rawData, setRawData] = useState<ChartDataPoint[]>([]);
  const [data, setData] = useState<any[]>([]);
  const [isInitialLoad, setIsInitialLoad] = useState(true);
  const [error, setError] = useState('');

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

    // Average stream count in each bucket
    const aggregated = Array.from(buckets.entries()).map(([bucketTime, points]) => {
      const avgCount = points.reduce((sum, p) => sum + (p.active_streams_count || 0), 0) / points.length;
      return {
        timestamp: new Date(bucketTime).toISOString(),
        stream_count: Math.round(avgCount), // Round to nearest integer for stream count
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

  // Process data when interval changes or raw data updates
  useEffect(() => {
    if (rawData.length === 0) {
      setData([]);
      return;
    }

    // Aggregate or use raw data based on interval
    const processedData = dataInterval === 'raw'
      ? rawData.map(point => ({
          timestamp: point.timestamp,
          stream_count: point.active_streams_count || 0,
        }))
      : aggregateData(rawData, dataInterval);

    setData(processedData);
  }, [rawData, dataInterval]);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 30000); // Refresh every 30s
    return () => clearInterval(interval);
  }, [timeRange.hours]);

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
                formatter={(value: number) => [value, 'Streams']}
                contentStyle={{
                  backgroundColor: 'rgba(0, 0, 0, 0.9)',
                  border: '1px solid #666',
                  borderRadius: '4px'
                }}
              />
              <Line
                type="monotone"
                dataKey="stream_count"
                stroke="#ff7300"
                strokeWidth={2}
                dot={{ fill: '#ff7300', r: 3 }}
                name="Active Streams"
                isAnimationActive={true}
                animationDuration={300}
                animationEasing="ease-in-out"
              />
            </LineChart>
          </ResponsiveContainer>
        )}
      </CardContent>
    </Card>
  );
};

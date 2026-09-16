import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { BandwidthChart } from '@/components/BandwidthChart';
import { ActiveStreams } from '@/components/ActiveStreams';
import { StreamCountChart } from '@/components/StreamCountChart';
import type { ZoomRange } from '@/hooks/useChartZoom';
import { TemporaryLimits } from '@/components/TemporaryLimits';
import { ThrottlingBanner } from '@/components/ThrottlingBanner';
import { BandwidthOverview } from '@/components/BandwidthOverview';
import { DashboardPanel } from '@/components/DashboardPanel';
import { useDashboardLayout } from '@/hooks/useDashboardLayout';
import type { PanelId } from '@/lib/dashboardLayout';
import {
  activeStreamsSummary,
  bandwidthChartSummary,
  overviewSummary,
  streamCountSummary,
  temporaryLimitsSummary,
} from '@/lib/dashboardSummaries';
import type { SystemStatus, TemporaryLimitState } from '@/types';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle } from 'lucide-react';

interface TimeRange {
  label: string;
  hours: number;
}

const timeRanges: TimeRange[] = [
  { label: 'Last 30 Minutes', hours: 0.5 },
  { label: 'Last Hour', hours: 1 },
  { label: 'Last 2 Hours', hours: 2 },
  { label: 'Last 6 Hours', hours: 6 },
  { label: 'Last 12 Hours', hours: 12 },
  { label: 'Last 24 Hours', hours: 24 },
  { label: 'Last 3 Days', hours: 72 },
];

type DataInterval = 'raw' | 0.25 | 0.5 | 1 | 5 | 10 | 15 | 30 | 60;

// Map time ranges to recommended data intervals
const getRecommendedInterval = (hours: number): DataInterval => {
  if (hours <= 2) return 0.25;         // 30 min, 1 hr, 2 hr: 15 sec
  if (hours <= 6) return 0.5;          // 6 hr: 30 sec
  if (hours <= 24) return 1;           // 12 hr, 24 hr: 1 min
  return 5;                            // 3 days: 5 min
};

interface PanelSpec {
  title: string;
  visible: boolean;
  summary: string;
  /** Renders the panel content with the shell's controls to place in its title row. */
  content: (controls: React.ReactNode) => React.ReactNode;
}

export const Home: React.FC = () => {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [tempLimits, setTempLimits] = useState<TemporaryLimitState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [timeRange, setTimeRange] = useState<TimeRange>(timeRanges[2]); // Default: Last 2 Hours
  const [dataInterval, setDataInterval] = useState<DataInterval>(0.25); // Default: 15 sec (for 2 hour range)
  const [zoomRange, setZoomRange] = useState<ZoomRange | null>(null);

  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const { layout, move, toggle, reset, isDefault } = useDashboardLayout();

  // A collapsed bandwidth chart cannot show its Reset Zoom button, so drop the zoom it published.
  const chartCollapsed = layout.collapsed.includes('bandwidth-chart');
  useEffect(() => {
    if (chartCollapsed) setZoomRange(null);
  }, [chartCollapsed]);

  // Wrapper to also update data interval when time range changes
  const handleTimeRangeChange = (newRange: TimeRange) => {
    setTimeRange(newRange);
    setDataInterval(getRecommendedInterval(newRange.hours));
  };

  const fetchStatus = useCallback(async () => {
    try {
      const [statusResponse, tempLimitsResponse] = await Promise.all([
        apiClient.getSystemStatus(),
        apiClient.getTemporaryLimits(),
      ]);
      setStatus(statusResponse);
      setTempLimits(tempLimitsResponse);
      setError('');
    } catch (err) {
      setError('Failed to load system status');
      console.error('Error fetching system status:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchStatus();
    const interval = setInterval(fetchStatus, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, [fetchStatus]);

  if (isLoading) {
    return (
      <div className="flex justify-center p-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Configured media servers (every server in media_server_statuses, connected or not).
  const configuredServerCount = status?.media_server_statuses
    ? Object.keys(status.media_server_statuses).length
    : 0;

  const panels: Record<PanelId, PanelSpec> = {
    'overview': {
      title: 'Overview',
      visible: status !== null,
      summary: overviewSummary(status, tempLimits),
      content: (controls) =>
        status ? <BandwidthOverview status={status} tempLimits={tempLimits} controls={controls} /> : null,
    },
    'temporary-limits': {
      title: 'Temporary Limits',
      // Non-admins only see this panel while an override is active (was a guard inside the component).
      visible: isAdmin || !!tempLimits?.active,
      summary: temporaryLimitsSummary(tempLimits),
      content: (controls) => (
        <TemporaryLimits throttlingDisabled={status ? !status.throttling_enabled : false} controls={controls} />
      ),
    },
    'bandwidth-chart': {
      title: 'Bandwidth Usage',
      visible: true,
      summary: bandwidthChartSummary(status),
      content: (controls) => (
        <BandwidthChart
          timeRange={timeRange}
          setTimeRange={handleTimeRangeChange}
          dataInterval={dataInterval}
          setDataInterval={setDataInterval}
          timeRanges={timeRanges}
          onZoomChange={setZoomRange}
          configuredServerCount={configuredServerCount}
          controls={controls}
        />
      ),
    },
    'stream-count': {
      title: 'Stream Count',
      visible: true,
      summary: streamCountSummary(status),
      content: (controls) => (
        <StreamCountChart timeRange={timeRange} dataInterval={dataInterval} zoomRange={zoomRange} controls={controls} />
      ),
    },
    'active-streams': {
      title: 'Active Streams',
      visible: true,
      summary: activeStreamsSummary(status),
      content: (controls) => <ActiveStreams configuredServerCount={configuredServerCount} controls={controls} />,
    },
  };

  const visibleIds = layout.order.filter((id) => panels[id].visible);

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {status && <ThrottlingBanner status={status} onReenabled={fetchStatus} />}

      {visibleIds.map((id, index) => (
        <DashboardPanel
          key={id}
          id={id}
          title={panels[id].title}
          summary={panels[id].summary}
          collapsed={layout.collapsed.includes(id)}
          canMoveUp={index > 0}
          canMoveDown={index < visibleIds.length - 1}
          isDefaultLayout={isDefault}
          onMoveUp={() => move(id, 'up', visibleIds)}
          onMoveDown={() => move(id, 'down', visibleIds)}
          onResetLayout={reset}
          onToggleCollapsed={() => toggle(id)}
        >
          {panels[id].content}
        </DashboardPanel>
      ))}
    </div>
  );
};

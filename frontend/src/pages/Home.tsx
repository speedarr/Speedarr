import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/api/client';
import { BandwidthChart } from '@/components/BandwidthChart';
import { ActiveStreams } from '@/components/ActiveStreams';
import { TemporaryLimits } from '@/components/TemporaryLimits';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import type { SystemStatus } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, AlertTriangle, Frown, Clock } from 'lucide-react';

interface TemporaryLimitState {
  active: boolean;
  download_mbps: number | null;
  upload_mbps: number | null;
  expires_at: string | null;
  remaining_minutes: number | null;
}

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

export const Home: React.FC = () => {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [tempLimits, setTempLimits] = useState<TemporaryLimitState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [timeRange, setTimeRange] = useState<TimeRange>(timeRanges[2]); // Default: Last 2 Hours
  const [dataInterval, setDataInterval] = useState<DataInterval>(0.25); // Default: 15 sec (for 2 hour range)

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

  return (
    <div className="space-y-6">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {/* Bandwidth Overview */}
      {status && (
        <div className="grid grid-cols-1 md:grid-cols-3 gap-4">
          <Card>
            <CardHeader>
              <CardTitle className="text-base">Download Bandwidth</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between items-center">
                {tempLimits?.active && tempLimits.download_mbps !== null ? (
                  <span className="text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
                    <Clock className="h-3 w-3" aria-hidden="true" />
                    <span>Temporary Limit:</span>
                  </span>
                ) : (
                  <span className="text-sm text-muted-foreground">Total Limit:</span>
                )}
                <span className={`font-semibold ${tempLimits?.active && tempLimits.download_mbps !== null ? 'text-red-500 dark:text-red-400' : ''}`}>
                  {tempLimits?.active && tempLimits.download_mbps !== null
                    ? tempLimits.download_mbps.toFixed(0)
                    : status.bandwidth.download.total_limit.toFixed(0)} Mbps
                </span>
              </div>
              {status.bandwidth.download.clients?.map((client) => (
                <div key={client.type} className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground" style={{ color: client.error ? undefined : client.color }}>
                    {client.error ? (
                      <span className="text-red-500 dark:text-red-400 flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        {client.name}:
                      </span>
                    ) : (
                      <>{client.name}:</>
                    )}
                  </span>
                  {client.error ? (
                    <span className="text-sm font-semibold text-red-500 dark:text-red-400">Unreachable</span>
                  ) : (
                    <span className="font-semibold">
                      {client.speed.toFixed(0)} / {client.limit.toFixed(0)} Mbps
                    </span>
                  )}
                </div>
              ))}
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">Available:</span>
                <span className="font-semibold text-green-600 dark:text-green-400">
                  {(tempLimits?.active && tempLimits.download_mbps !== null
                    ? Math.max(0, tempLimits.download_mbps - status.bandwidth.download.current_usage)
                    : status.bandwidth.download.available
                  ).toFixed(0)} Mbps
                </span>
              </div>
            </CardContent>
          </Card>

          {/* Plex Streams Count with WAN Usage (when SNMP enabled) */}
          <Card className="flex items-center">
            <CardContent className="py-6 px-2 sm:px-4 w-full">
              {status.snmp_enabled ? (
                <div className="grid grid-cols-3 items-center justify-items-center">
                  {/* WAN Download - Left */}
                  <div className="flex flex-col items-center justify-center">
                    <p className="text-sm text-muted-foreground mb-1">WAN Download</p>
                    {status.snmp_status && !status.snmp_status.connected ? (
                      <>
                        <AlertTriangle className="h-6 w-6 text-red-500 dark:text-red-400" />
                        <p className="text-xs text-red-500 dark:text-red-400 mt-1">SNMP Unreachable</p>
                      </>
                    ) : (
                      <>
                        <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                          {status.bandwidth.download.snmp_speed !== null && status.bandwidth.download.snmp_speed !== undefined
                            ? `${status.bandwidth.download.snmp_speed.toFixed(0)}`
                            : '--'}
                        </p>
                        <p className="text-sm text-muted-foreground">Mbps</p>
                      </>
                    )}
                  </div>

                  {/* Plex Streams - Center */}
                  <div className="flex flex-col items-center justify-center border-x border-border py-2 w-full">
                    {status.plex_status && !status.plex_status.connected ? (
                      <>
                        <AlertTriangle className="h-16 w-16 text-red-500 dark:text-red-400" />
                        <p className="text-sm text-red-500 dark:text-red-400 mt-2">Plex Unreachable</p>
                      </>
                    ) : status.active_streams === 0 ? (
                      <>
                        <Frown className="h-16 w-16 text-muted-foreground" />
                        <p className="text-sm text-muted-foreground mt-2">No Plex Streams</p>
                      </>
                    ) : (
                      <>
                        <div className="text-6xl font-bold text-orange-500 dark:text-orange-400">
                          {status.active_streams}
                        </div>
                        <p className="text-sm text-muted-foreground mt-1">
                          Plex {status.active_streams === 1 ? 'Stream' : 'Streams'}
                        </p>
                        <p className="text-xl font-semibold text-orange-500 dark:text-orange-400 text-center">
                          {(status.bandwidth.upload.stream_bandwidth ?? 0).toFixed(1)} Mbps Bitrate
                        </p>
                      </>
                    )}
                  </div>

                  {/* WAN Upload - Right */}
                  <div className="flex flex-col items-center justify-center">
                    <p className="text-sm text-muted-foreground mb-1">WAN Upload</p>
                    {status.snmp_status && !status.snmp_status.connected ? (
                      <>
                        <AlertTriangle className="h-6 w-6 text-red-500 dark:text-red-400" />
                        <p className="text-xs text-red-500 dark:text-red-400 mt-1">SNMP Unreachable</p>
                      </>
                    ) : (
                      <>
                        <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
                          {status.bandwidth.upload.snmp_speed !== null && status.bandwidth.upload.snmp_speed !== undefined
                            ? `${status.bandwidth.upload.snmp_speed.toFixed(0)}`
                            : '--'}
                        </p>
                        <p className="text-sm text-muted-foreground">Mbps</p>
                      </>
                    )}
                  </div>
                </div>
              ) : (
                /* Plex Streams Only (no SNMP) - Centered */
                <div className="flex flex-col items-center justify-center">
                  {status.plex_status && !status.plex_status.connected ? (
                    <>
                      <AlertTriangle className="h-16 w-16 text-red-500 dark:text-red-400" />
                      <p className="text-sm text-red-500 dark:text-red-400 mt-2">Plex Unreachable</p>
                    </>
                  ) : status.active_streams === 0 ? (
                    <>
                      <Frown className="h-16 w-16 text-muted-foreground" />
                      <p className="text-sm text-muted-foreground mt-2">No Plex Streams</p>
                    </>
                  ) : (
                    <>
                      <div className="text-6xl font-bold text-orange-500 dark:text-orange-400">
                        {status.active_streams}
                      </div>
                      <p className="text-sm text-muted-foreground mt-1">
                        Plex {status.active_streams === 1 ? 'Stream' : 'Streams'}
                      </p>
                      <p className="text-xl font-semibold text-orange-500 dark:text-orange-400 text-center">
                        {(status.bandwidth.upload.stream_bandwidth ?? 0).toFixed(1)} Mbps Bitrate
                      </p>
                    </>
                  )}
                </div>
              )}
            </CardContent>
          </Card>

          <Card>
            <CardHeader>
              <CardTitle className="text-base">Upload Bandwidth</CardTitle>
            </CardHeader>
            <CardContent className="space-y-3">
              <div className="flex justify-between items-center">
                {tempLimits?.active && tempLimits.upload_mbps !== null ? (
                  <span className="text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
                    <Clock className="h-3 w-3" aria-hidden="true" />
                    <span>Temporary Limit:</span>
                  </span>
                ) : (
                  <span className="text-sm text-muted-foreground">Total Limit:</span>
                )}
                <span className={`font-semibold ${tempLimits?.active && tempLimits.upload_mbps !== null ? 'text-red-500 dark:text-red-400' : ''}`}>
                  {tempLimits?.active && tempLimits.upload_mbps !== null
                    ? tempLimits.upload_mbps.toFixed(0)
                    : status.bandwidth.upload.total_limit.toFixed(0)} Mbps
                </span>
              </div>
              {status.bandwidth.upload.clients?.map((client) => (
                <div key={client.type} className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground" style={{ color: client.error ? undefined : client.color }}>
                    {client.error ? (
                      <span className="text-red-500 dark:text-red-400 flex items-center gap-1">
                        <AlertTriangle className="h-3 w-3" />
                        {client.name}:
                      </span>
                    ) : (
                      <>{client.name}:</>
                    )}
                  </span>
                  {client.error ? (
                    <span className="text-sm font-semibold text-red-500 dark:text-red-400">Unreachable</span>
                  ) : (
                    <span className="font-semibold">
                      {client.speed.toFixed(0)} / {client.limit.toFixed(0)} Mbps
                    </span>
                  )}
                </div>
              ))}
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">Plex Reserved:</span>
                <span className="font-semibold text-orange-500 dark:text-orange-400">
                  {(status.bandwidth.upload.reserved_bandwidth ?? 0).toFixed(0)} Mbps
                </span>
              </div>
              {(status.bandwidth.upload.reserved_bandwidth ?? 0) > status.bandwidth.upload.total_limit && (
                <Alert variant="destructive" className="py-2">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription className="text-xs">
                    Plex reserved ({(status.bandwidth.upload.reserved_bandwidth ?? 0).toFixed(0)} Mbps) exceeds upload limit ({status.bandwidth.upload.total_limit.toFixed(0)} Mbps). Upload clients limited to 1% each.
                  </AlertDescription>
                </Alert>
              )}
              {tempLimits?.active && tempLimits.upload_mbps !== null &&
               (status.bandwidth.upload.reserved_bandwidth ?? 0) > tempLimits.upload_mbps && (
                <Alert variant="destructive" className="py-2">
                  <AlertCircle className="h-4 w-4" />
                  <AlertDescription className="text-xs">
                    Plex reserved ({(status.bandwidth.upload.reserved_bandwidth ?? 0).toFixed(0)} Mbps) exceeds temporary upload limit ({tempLimits.upload_mbps.toFixed(0)} Mbps). Upload clients limited to 1% each.
                  </AlertDescription>
                </Alert>
              )}
              {(status.bandwidth.upload.holding_bandwidth ?? 0) > 0 && (
                <div className="flex justify-between items-center">
                  <span className="text-sm text-muted-foreground">Holding:</span>
                  <span className="font-semibold text-orange-500 dark:text-orange-400">
                    {(status.bandwidth.upload.holding_bandwidth ?? 0).toFixed(0)} Mbps
                  </span>
                </div>
              )}
              <div className="flex justify-between items-center">
                <span className="text-sm text-muted-foreground">Available:</span>
                <span className="font-semibold text-green-600 dark:text-green-400">
                  {(tempLimits?.active && tempLimits.upload_mbps !== null
                    ? Math.max(0, tempLimits.upload_mbps - status.bandwidth.upload.current_usage)
                    : status.bandwidth.upload.available
                  ).toFixed(0)} Mbps
                </span>
              </div>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Temporary Limits */}
      <ErrorBoundary>
        <TemporaryLimits />
      </ErrorBoundary>

      {/* Bandwidth Chart */}
      <ErrorBoundary>
        <BandwidthChart
          timeRange={timeRange}
          setTimeRange={handleTimeRangeChange}
          dataInterval={dataInterval}
          setDataInterval={setDataInterval}
          timeRanges={timeRanges}
        />
      </ErrorBoundary>

      {/* Active Streams */}
      <ErrorBoundary>
        <ActiveStreams
          timeRange={timeRange}
          dataInterval={dataInterval}
        />
      </ErrorBoundary>
    </div>
  );
};

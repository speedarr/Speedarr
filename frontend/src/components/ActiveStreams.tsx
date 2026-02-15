import React, { useState, useEffect, useCallback } from 'react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import type { ActiveStream, StreamReservation } from '@/types';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import { Badge } from '@/components/ui/badge';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  AlertDialog,
  AlertDialogAction,
  AlertDialogCancel,
  AlertDialogContent,
  AlertDialogDescription,
  AlertDialogFooter,
  AlertDialogHeader,
  AlertDialogTitle,
} from '@/components/ui/alert-dialog';
import { Play, Pause, StopCircle, Loader2, AlertCircle, X } from 'lucide-react';
import { StreamCountChart } from './StreamCountChart';
import type { TimeRange, DataInterval } from './BandwidthChart';
import type { ZoomRange } from '@/hooks/useChartZoom';
import { formatInTimeZone } from 'date-fns-tz';

const getStateIcon = (state: string) => {
  switch (state) {
    case 'playing':
      return <Play className="h-4 w-4 text-green-500" aria-hidden="true" />;
    case 'paused':
      return <Pause className="h-4 w-4 text-yellow-500" aria-hidden="true" />;
    case 'stopped':
      return <StopCircle className="h-4 w-4 text-red-500" aria-hidden="true" />;
    default:
      return null;
  }
};

const getStateBadgeVariant = (state: string): "default" | "secondary" | "destructive" | "outline" => {
  switch (state) {
    case 'playing':
      return 'default';
    case 'paused':
      return 'secondary';
    case 'stopped':
      return 'destructive';
    default:
      return 'outline';
  }
};

interface ActiveStreamsProps {
  timeRange: TimeRange;
  dataInterval: DataInterval;
  zoomRange?: ZoomRange | null;
}

export const ActiveStreams: React.FC<ActiveStreamsProps> = ({ timeRange, dataInterval, zoomRange }) => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [streams, setStreams] = useState<ActiveStream[]>([]);
  const [reservations, setReservations] = useState<StreamReservation[]>([]);
  const [totalBandwidth, setTotalBandwidth] = useState(0);
  const [totalReserved, setTotalReserved] = useState(0);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [clearingReservation, setClearingReservation] = useState<string | null>(null);
  const [confirmClearReservation, setConfirmClearReservation] = useState<StreamReservation | null>(null);

  const fetchData = useCallback(async () => {
    try {
      const response = await apiClient.getActiveStreams();
      // Sort streams by bitrate from high to low
      const sortedStreams = [...response.active_streams].sort(
        (a, b) => b.stream_bitrate_mbps - a.stream_bitrate_mbps
      );
      setStreams(sortedStreams);
      setReservations(response.reservations);
      setTotalBandwidth(response.total_bandwidth_mbps);
      setTotalReserved(response.total_reserved_mbps);
      setError('');
    } catch (err) {
      setError('Failed to load active streams');
      console.error('Error fetching active streams:', err);
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchData();
    const interval = setInterval(fetchData, 5000); // Refresh every 5s
    return () => clearInterval(interval);
  }, [fetchData]);

  const handleClearReservation = async (reservation: StreamReservation) => {
    if (!reservation.id) return;

    setClearingReservation(reservation.id);
    try {
      await apiClient.clearBandwidthReservation(reservation.id);
      // Refresh data after clearing
      await fetchData();
    } catch (err) {
      console.error('Error clearing reservation:', err);
      setError('Failed to clear bandwidth reservation');
    } finally {
      setClearingReservation(null);
      setConfirmClearReservation(null);
    }
  };

  if (isLoading) {
    return (
      <>
        <StreamCountChart timeRange={timeRange} dataInterval={dataInterval} zoomRange={zoomRange} />
        <Card>
          <CardContent className="flex justify-center p-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </>
    );
  }

  return (
    <>
      <StreamCountChart timeRange={timeRange} dataInterval={dataInterval} zoomRange={zoomRange} />
      <Card>
      <CardHeader>
        <div className="flex flex-col sm:flex-row items-start sm:items-center justify-between gap-4">
          <CardTitle>Active Streams</CardTitle>
          <div className="flex flex-wrap gap-2">
            <Badge variant="outline" className="text-sm">
              {streams.length} Active
            </Badge>
            <Badge variant="outline" className="text-sm">
              {totalBandwidth.toFixed(1)} Mbps
            </Badge>
            {totalReserved > 0 && (
              <Badge variant="secondary" className="text-sm">
                {totalReserved.toFixed(1)} Mbps Reserved
              </Badge>
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

        {streams.length === 0 && !error && (
          <Alert>
            <AlertDescription>No active streams at the moment.</AlertDescription>
          </Alert>
        )}

        {streams.length > 0 && (
          <div className="border rounded-lg overflow-hidden">
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Status</TableHead>
                  <TableHead>User</TableHead>
                  <TableHead>Title</TableHead>
                  <TableHead>Quality</TableHead>
                  <TableHead>Transcode</TableHead>
                  <TableHead className="text-right">Bitrate</TableHead>
                  <TableHead>Network</TableHead>
                  <TableHead>Platform</TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {streams.map((stream) => (
                  <TableRow key={stream.session_id}>
                    <TableCell>
                      <div className="flex items-center gap-2">
                        {getStateIcon(stream.state)}
                        <Badge variant={getStateBadgeVariant(stream.state)}>
                          {stream.state}
                        </Badge>
                      </div>
                    </TableCell>
                    <TableCell>{stream.user_name}</TableCell>
                    <TableCell>
                      <div className="max-w-[300px] truncate text-sm" title={stream.display_title}>
                        {stream.display_title}
                      </div>
                    </TableCell>
                    <TableCell>
                      {stream.quality_profile && (
                        <Badge variant="outline">{stream.quality_profile}</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {stream.transcode_decision && (
                        <Badge variant={stream.transcode_decision === 'transcode' ? 'secondary' : 'outline'}>
                          {stream.transcode_decision}
                        </Badge>
                      )}
                    </TableCell>
                    <TableCell className="text-right">
                      <span className="font-semibold">
                        {stream.stream_bitrate_mbps.toFixed(1)} Mbps
                      </span>
                    </TableCell>
                    <TableCell>
                      <Badge variant={stream.is_lan ? 'secondary' : 'outline'}>
                        {stream.is_lan ? 'LAN' : 'WAN'}
                      </Badge>
                    </TableCell>
                    <TableCell>
                      <span className="text-sm text-muted-foreground">
                        {stream.platform || stream.player || 'Unknown'}
                      </span>
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          </div>
        )}

        {reservations.length > 0 && (
          <div className="mt-6">
            <h3 className="text-sm font-semibold mb-3">Bandwidth Holdings</h3>
            <div className="border rounded-lg overflow-hidden">
              <Table>
                <TableHeader>
                  <TableRow>
                    <TableHead>User</TableHead>
                    <TableHead>Player</TableHead>
                    <TableHead className="text-right">Bandwidth</TableHead>
                    <TableHead>Expires At</TableHead>
                    {isAdmin && <TableHead className="w-[80px]"></TableHead>}
                  </TableRow>
                </TableHeader>
                <TableBody>
                  {reservations.map((res, idx) => (
                    <TableRow key={res.id || idx}>
                      <TableCell>{res.user_name || 'Unknown'}</TableCell>
                      <TableCell>{res.player || 'Unknown'}</TableCell>
                      <TableCell className="text-right">
                        {res.bandwidth_mbps.toFixed(1)} Mbps
                      </TableCell>
                      <TableCell>
                        {formatInTimeZone(
                          new Date(res.expires_at.endsWith('Z') ? res.expires_at : res.expires_at + 'Z'),
                          Intl.DateTimeFormat().resolvedOptions().timeZone,
                          'dd/MM/yyyy hh:mm:ss a'
                        )}
                      </TableCell>
                      {isAdmin && (
                        <TableCell>
                          <Button
                            variant="ghost"
                            size="sm"
                            onClick={() => setConfirmClearReservation(res)}
                            disabled={clearingReservation === res.id}
                            className="h-8 w-8 p-0"
                          >
                            {clearingReservation === res.id ? (
                              <Loader2 className="h-4 w-4 animate-spin" />
                            ) : (
                              <X className="h-4 w-4" />
                            )}
                          </Button>
                        </TableCell>
                      )}
                    </TableRow>
                  ))}
                </TableBody>
              </Table>
            </div>
          </div>
        )}

        {/* Confirmation Dialog */}
        <AlertDialog open={!!confirmClearReservation} onOpenChange={() => setConfirmClearReservation(null)}>
          <AlertDialogContent>
            <AlertDialogHeader>
              <AlertDialogTitle>Clear Bandwidth Reservation?</AlertDialogTitle>
              <AlertDialogDescription>
                Are you sure you want to release the bandwidth reservation for{' '}
                <strong>{confirmClearReservation?.user_name || 'Unknown'}</strong>?
                This will immediately free up {confirmClearReservation?.bandwidth_mbps.toFixed(1)} Mbps.
              </AlertDialogDescription>
            </AlertDialogHeader>
            <AlertDialogFooter>
              <AlertDialogCancel>Cancel</AlertDialogCancel>
              <AlertDialogAction onClick={() => confirmClearReservation && handleClearReservation(confirmClearReservation)}>
                Clear Reservation
              </AlertDialogAction>
            </AlertDialogFooter>
          </AlertDialogContent>
        </AlertDialog>
      </CardContent>
    </Card>
    </>
  );
};

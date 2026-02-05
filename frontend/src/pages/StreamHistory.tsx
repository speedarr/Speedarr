import React, { useState, useEffect } from 'react';
import { apiClient } from '@/api/client';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Button } from '@/components/ui/button';
import { Loader2, AlertCircle, ChevronLeft, ChevronRight } from 'lucide-react';
import { formatInTimeZone } from 'date-fns-tz';
import type { StreamSummary } from '@/types';

interface StreamHistoryItem {
  id: number;
  session_id: string;
  user_name: string;
  user_id: string;
  media_title: string;
  display_title: string;
  media_type: string;
  started_at: string | null;
  ended_at: string | null;
  duration_seconds: number | null;
  stream_bandwidth_mbps: number | null;
  quality_profile: string | null;
  player: string | null;
  ip_address: string | null;
}

export const StreamHistory: React.FC = () => {
  const [streams, setStreams] = useState<StreamHistoryItem[]>([]);
  const [summary, setSummary] = useState<StreamSummary | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [days, setDays] = useState(7);
  const [offset, setOffset] = useState(0);
  const [hasMore, setHasMore] = useState(true);
  const limit = 50;

  const fetchData = async () => {
    setIsLoading(true);
    setError('');
    try {
      const [historyResponse, summaryResponse] = await Promise.all([
        apiClient.getStreamHistory({ days, limit, offset }),
        apiClient.getStreamSummary(days),
      ]);

      setStreams(historyResponse.streams as StreamHistoryItem[]);
      setSummary(summaryResponse as StreamSummary);
      setHasMore(historyResponse.streams.length === limit);
    } catch (err) {
      setError('Failed to load stream history');
      console.error('Error fetching stream history:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchData();
  }, [days, offset]);

  const formatDateTime = (isoString: string | null): string => {
    if (!isoString) return '-';
    const tz = Intl.DateTimeFormat().resolvedOptions().timeZone;
    // Ensure timestamp is parsed as UTC (API returns UTC without 'Z' suffix)
    const utcString = isoString.endsWith('Z') ? isoString : isoString + 'Z';
    return formatInTimeZone(new Date(utcString), tz, 'MMM d, HH:mm');
  };

  return (
    <div className="space-y-6">
      {/* Summary Cards */}
      {summary && (
        <div className="grid grid-cols-2 md:grid-cols-3 lg:grid-cols-6 gap-4">
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{summary.total_streams}</div>
              <p className="text-sm text-muted-foreground">Total Streams</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{summary.unique_users}</div>
              <p className="text-sm text-muted-foreground">Unique Users</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{summary.min_bandwidth_mbps.toFixed(1)} Mbps</div>
              <p className="text-sm text-muted-foreground">Lowest Bandwidth</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{summary.avg_bandwidth_mbps.toFixed(1)} Mbps</div>
              <p className="text-sm text-muted-foreground">Avg Bandwidth</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{summary.peak_individual_bandwidth_mbps.toFixed(1)} Mbps</div>
              <p className="text-sm text-muted-foreground">Highest Individual</p>
            </CardContent>
          </Card>
          <Card>
            <CardContent className="pt-6">
              <div className="text-2xl font-bold">{summary.peak_combined_bandwidth_mbps.toFixed(1)} Mbps</div>
              <p className="text-sm text-muted-foreground">Highest Combined</p>
            </CardContent>
          </Card>
        </div>
      )}

      {/* Stream History Table */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <CardTitle>Stream History</CardTitle>
            <Select value={days.toString()} onValueChange={(v) => { setDays(parseInt(v)); setOffset(0); }}>
              <SelectTrigger className="w-[150px]">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="1">Last 24 Hours</SelectItem>
                <SelectItem value="7">Last 7 Days</SelectItem>
                <SelectItem value="30">Last 30 Days</SelectItem>
                <SelectItem value="90">Last 90 Days</SelectItem>
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {isLoading ? (
            <div className="flex justify-center p-8">
              <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
            </div>
          ) : streams.length === 0 ? (
            <div className="text-center p-8 text-muted-foreground">
              No stream history found for the selected period.
            </div>
          ) : (
            <>
              <div className="rounded-md border">
                <Table>
                  <TableHeader>
                    <TableRow>
                      <TableHead>User</TableHead>
                      <TableHead>Media</TableHead>
                      <TableHead>Started</TableHead>
                      <TableHead>Bandwidth</TableHead>
                      <TableHead>Player</TableHead>
                    </TableRow>
                  </TableHeader>
                  <TableBody>
                    {streams.map((stream) => (
                      <TableRow key={stream.id}>
                        <TableCell className="font-medium">{stream.user_name}</TableCell>
                        <TableCell className="max-w-[200px] truncate" title={stream.display_title}>
                          {stream.display_title}
                        </TableCell>
                        <TableCell>{formatDateTime(stream.started_at)}</TableCell>
                        <TableCell>
                          {stream.stream_bandwidth_mbps?.toFixed(1) || '-'} Mbps
                        </TableCell>
                        <TableCell>{stream.player || '-'}</TableCell>
                      </TableRow>
                    ))}
                  </TableBody>
                </Table>
              </div>

              {/* Pagination */}
              <div className="flex items-center justify-between mt-4">
                <div className="text-sm text-muted-foreground">
                  Showing {offset + 1} - {offset + streams.length} streams
                </div>
                <div className="flex gap-2">
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setOffset(Math.max(0, offset - limit))}
                    disabled={offset === 0}
                  >
                    <ChevronLeft className="h-4 w-4 mr-1" />
                    Previous
                  </Button>
                  <Button
                    variant="outline"
                    size="sm"
                    onClick={() => setOffset(offset + limit)}
                    disabled={!hasMore}
                  >
                    Next
                    <ChevronRight className="h-4 w-4 ml-1" />
                  </Button>
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>
    </div>
  );
};

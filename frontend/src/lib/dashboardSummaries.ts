/**
 * One-line summaries shown in a collapsed dashboard panel header (issue #86), derived from the
 * status and temporary-limit state Home already polls, so a collapsed panel costs no requests.
 */
import type { SystemStatus, TemporaryLimitState } from '@/types';

export type Direction = 'download' | 'upload';

const SEP = ' · ';
const UNKNOWN = '--';

const mbps = (value: number): string => `${value.toFixed(0)} Mbps`;

/** Human-readable time left on a temporary limit. Moved verbatim from TemporaryLimits.tsx. */
export function formatRemainingTime(minutes: number | null, expiresAt: string | null): string {
  if (minutes === null && expiresAt === null) return 'Until cleared';
  if (minutes === null) return '--';
  if (minutes < 1) return 'Less than 1 minute';
  if (minutes < 60) return `${Math.round(minutes)} minute${Math.round(minutes) !== 1 ? 's' : ''}`;
  const hours = Math.floor(minutes / 60);
  const mins = Math.round(minutes % 60);
  if (mins === 0) return `${hours} hour${hours !== 1 ? 's' : ''}`;
  return `${hours}h ${mins}m`;
}

/** The limit the dashboard should show: an active temporary limit for that direction, else the total. */
export function effectiveLimit(status: SystemStatus, temp: TemporaryLimitState | null, direction: Direction): number {
  const override = temp?.active ? (direction === 'download' ? temp.download_mbps : temp.upload_mbps) : null;
  return override ?? status.bandwidth[direction].total_limit;
}

const streamsPhrase = (count: number, noun: string): string => {
  if (count === 0) return `No ${noun}s`;
  return `${count} ${noun}${count === 1 ? '' : 's'}`;
};

export function overviewSummary(status: SystemStatus | null, temp: TemporaryLimitState | null): string {
  if (!status) return UNKNOWN;
  const dl = `↓ ${status.bandwidth.download.current_usage.toFixed(0)} / ${mbps(effectiveLimit(status, temp, 'download'))}`;
  const ul = `↑ ${status.bandwidth.upload.current_usage.toFixed(0)} / ${mbps(effectiveLimit(status, temp, 'upload'))}`;
  return [dl, streamsPhrase(status.active_streams, 'stream'), ul].join(SEP);
}

export function temporaryLimitsSummary(temp: TemporaryLimitState | null): string {
  if (!temp) return UNKNOWN;
  if (!temp.active) return 'No temporary limit';
  const parts: string[] = [];
  if (temp.download_mbps !== null) parts.push(`↓ ${mbps(temp.download_mbps)}`);
  if (temp.upload_mbps !== null) parts.push(`↑ ${mbps(temp.upload_mbps)}`);
  const remaining = formatRemainingTime(temp.remaining_minutes, temp.expires_at);
  if (remaining === 'Until cleared') parts.push(remaining);
  else if (remaining !== '--') parts.push(`${remaining} left`);
  return parts.join(SEP);
}

export function bandwidthChartSummary(status: SystemStatus | null): string {
  if (!status) return UNKNOWN;
  return `↓ ${mbps(status.bandwidth.download.current_usage)}${SEP}↑ ${mbps(status.bandwidth.upload.current_usage)} now`;
}

export function streamCountSummary(status: SystemStatus | null): string {
  if (!status) return UNKNOWN;
  return streamsPhrase(status.active_streams, 'active stream');
}

export function activeStreamsSummary(status: SystemStatus | null): string {
  if (!status) return UNKNOWN;
  if (status.active_streams === 0) return 'No active streams';
  const wan = status.bandwidth.upload.wan_stream_bandwidth ?? status.bandwidth.upload.stream_bandwidth ?? 0;
  const lan = status.bandwidth.upload.lan_stream_bandwidth ?? 0;
  const parts = [`${status.active_streams} active`];
  if (wan > 0) parts.push(`${wan.toFixed(1)} Mbps WAN`);
  if (lan > 0) parts.push(`${lan.toFixed(1)} Mbps LAN`);
  return parts.join(SEP);
}

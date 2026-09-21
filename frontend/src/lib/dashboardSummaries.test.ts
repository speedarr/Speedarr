import { describe, it, expect } from 'vitest';
import type { SystemStatus, TemporaryLimitState } from '@/types';
import {
  activeStreamsSummary,
  bandwidthChartSummary,
  effectiveLimit,
  formatRemainingTime,
  overviewSummary,
  streamCountSummary,
  temporaryLimitsSummary,
} from './dashboardSummaries';

const makeStatus = (over: Partial<SystemStatus> = {}): SystemStatus => ({
  status: 'ok',
  active_streams: 0,
  is_throttled: false,
  throttling_enabled: true,
  bandwidth: {
    download: { total_limit: 900, current_usage: 120.4, available: 779.6 },
    upload: { total_limit: 100, current_usage: 40, available: 60 },
  },
  ...over,
});

const makeTemp = (over: Partial<TemporaryLimitState> = {}): TemporaryLimitState => ({
  active: true,
  download_mbps: 100,
  upload_mbps: 20,
  expires_at: '2026-09-16T12:00:00',
  remaining_minutes: 130,
  source: 'api',
  set_by: 'corey',
  ...over,
});

describe('formatRemainingTime (moved from TemporaryLimits, behaviour preserved)', () => {
  it('handles the null and sub-minute cases', () => {
    expect(formatRemainingTime(null, null)).toBe('Until cleared');
    expect(formatRemainingTime(null, '2026-09-16T12:00:00')).toBe('--');
    expect(formatRemainingTime(0.4, 'x')).toBe('Less than 1 minute');
  });

  it('formats minutes, whole hours and hours+minutes', () => {
    expect(formatRemainingTime(1, 'x')).toBe('1 minute');
    expect(formatRemainingTime(45, 'x')).toBe('45 minutes');
    expect(formatRemainingTime(60, 'x')).toBe('1 hour');
    expect(formatRemainingTime(120, 'x')).toBe('2 hours');
    expect(formatRemainingTime(130, 'x')).toBe('2h 10m');
  });
});

describe('effectiveLimit', () => {
  it('is the total limit without an active temporary limit', () => {
    expect(effectiveLimit(makeStatus(), null, 'download')).toBe(900);
    expect(effectiveLimit(makeStatus(), makeTemp({ active: false }), 'upload')).toBe(100);
  });

  it('is the temporary limit for a direction that has one, per direction', () => {
    const temp = makeTemp({ download_mbps: 100, upload_mbps: null });
    expect(effectiveLimit(makeStatus(), temp, 'download')).toBe(100);
    expect(effectiveLimit(makeStatus(), temp, 'upload')).toBe(100); // no upload override: total_limit
  });
});

describe('overviewSummary', () => {
  it('shows usage over limit for both directions and the stream count', () => {
    expect(overviewSummary(makeStatus({ active_streams: 2 }), null)).toBe('↓ 120 / 900 Mbps · 2 streams · ↑ 40 / 100 Mbps');
  });

  it('uses singular and "No streams"', () => {
    expect(overviewSummary(makeStatus({ active_streams: 1 }), null)).toContain('· 1 stream ·');
    expect(overviewSummary(makeStatus(), null)).toContain('· No streams ·');
  });

  it('substitutes an active temporary limit for the total', () => {
    expect(overviewSummary(makeStatus(), makeTemp({ download_mbps: 100, upload_mbps: null })))
      .toBe('↓ 120 / 100 Mbps · No streams · ↑ 40 / 100 Mbps');
  });

  it('is -- without status', () => {
    expect(overviewSummary(null, null)).toBe('--');
  });
});

describe('temporaryLimitsSummary', () => {
  it('lists the limited directions and the time left', () => {
    expect(temporaryLimitsSummary(makeTemp())).toBe('↓ 100 Mbps · ↑ 20 Mbps · 2h 10m left');
  });

  it('omits a direction without a limit and shows Until cleared without a duration', () => {
    expect(temporaryLimitsSummary(makeTemp({ upload_mbps: null, remaining_minutes: null, expires_at: null })))
      .toBe('↓ 100 Mbps · Until cleared');
  });

  it('reports no limit when inactive and -- when unknown', () => {
    expect(temporaryLimitsSummary(makeTemp({ active: false }))).toBe('No temporary limit');
    expect(temporaryLimitsSummary(null)).toBe('--');
  });

  it('omits the time segment when the remaining minutes are unknown but an expiry exists', () => {
    expect(temporaryLimitsSummary(makeTemp({ remaining_minutes: null }))).toBe('↓ 100 Mbps · ↑ 20 Mbps');
  });
});

describe('bandwidthChartSummary', () => {
  it('shows the current usage in both directions', () => {
    expect(bandwidthChartSummary(makeStatus())).toBe('↓ 120 Mbps · ↑ 40 Mbps now');
    expect(bandwidthChartSummary(null)).toBe('--');
  });
});

describe('streamCountSummary', () => {
  it('counts with singular, plural and none', () => {
    expect(streamCountSummary(makeStatus())).toBe('No active streams');
    expect(streamCountSummary(makeStatus({ active_streams: 1 }))).toBe('1 active stream');
    expect(streamCountSummary(makeStatus({ active_streams: 3 }))).toBe('3 active streams');
    expect(streamCountSummary(null)).toBe('--');
  });
});

describe('activeStreamsSummary', () => {
  const withStreams = (upload: Partial<SystemStatus['bandwidth']['upload']>) =>
    makeStatus({
      active_streams: 2,
      bandwidth: {
        download: { total_limit: 900, current_usage: 120, available: 780 },
        upload: { total_limit: 100, current_usage: 40, available: 60, ...upload },
      },
    });

  it('shows the count with WAN and LAN bitrates to one decimal', () => {
    expect(activeStreamsSummary(withStreams({ wan_stream_bandwidth: 25.04, lan_stream_bandwidth: 3.2 })))
      .toBe('2 active · 25.0 Mbps WAN · 3.2 Mbps LAN');
  });

  it('omits zero parts and falls back to stream_bandwidth for WAN', () => {
    expect(activeStreamsSummary(withStreams({ wan_stream_bandwidth: 25, lan_stream_bandwidth: 0 }))).toBe('2 active · 25.0 Mbps WAN');
    expect(activeStreamsSummary(withStreams({ stream_bandwidth: 12.5 }))).toBe('2 active · 12.5 Mbps WAN');
    expect(activeStreamsSummary(withStreams({}))).toBe('2 active');
  });

  it('reports none and unknown', () => {
    expect(activeStreamsSummary(makeStatus())).toBe('No active streams');
    expect(activeStreamsSummary(null)).toBe('--');
  });
});

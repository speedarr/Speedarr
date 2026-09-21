import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';
import type { SystemStatus } from '@/types';

// Every request stays pending unless a test resolves it by method name: the title row and its
// controls must be there before any data arrives, and stay there once it has.
const { resolved } = vi.hoisted(() => ({ resolved: {} as Record<string, unknown> }));
vi.mock('@/api/client', () => ({
  apiClient: new Proxy(
    {},
    { get: (_target, name: string) => () => (name in resolved ? Promise.resolve(resolved[name]) : new Promise(() => {})) },
  ),
}));
vi.mock('@/contexts/AuthContext', () => ({
  useAuth: () => ({ user: { id: 1, username: 'admin', role: 'admin' }, login: vi.fn() }),
}));

import { BandwidthChart } from './BandwidthChart';
import { StreamCountChart } from './StreamCountChart';
import { ActiveStreams } from './ActiveStreams';
import { TemporaryLimits } from './TemporaryLimits';
import { BandwidthOverview } from './BandwidthOverview';

const controls = <button type="button">panel controls</button>;
const timeRange = { label: 'Last 2 Hours', hours: 2 };

const status: SystemStatus = {
  status: 'ok',
  active_streams: 0,
  is_throttled: false,
  throttling_enabled: true,
  bandwidth: {
    download: { total_limit: 900, current_usage: 120, available: 780 },
    upload: { total_limit: 100, current_usage: 40, available: 60 },
  },
};

const expectTitleRowWithControls = (title: string) => {
  expect(screen.getByRole('heading', { name: title })).toBeInTheDocument();
  expect(screen.getByRole('button', { name: 'panel controls' })).toBeInTheDocument();
};

describe('panel content components render their title row with the controls while loading', () => {
  it('BandwidthChart', () => {
    render(
      <BandwidthChart
        timeRange={timeRange}
        setTimeRange={() => {}}
        dataInterval={0.25}
        setDataInterval={() => {}}
        timeRanges={[timeRange]}
        configuredServerCount={0}
        controls={controls}
      />,
    );
    expectTitleRowWithControls('Bandwidth Usage');
  });

  it('StreamCountChart', () => {
    render(<StreamCountChart timeRange={timeRange} dataInterval={0.25} controls={controls} />);
    expectTitleRowWithControls('Stream Count');
  });

  it('ActiveStreams', () => {
    render(<ActiveStreams configuredServerCount={0} controls={controls} />);
    expectTitleRowWithControls('Active Streams');
  });

  it('TemporaryLimits', () => {
    render(<TemporaryLimits controls={controls} />);
    expectTitleRowWithControls('Temporary Limits');
  });

  it('ActiveStreams keeps the controls in the title row once the streams have loaded', async () => {
    resolved.getActiveStreams = { active_streams: [], reservations: [], total_reserved_mbps: 0 };
    try {
      render(<ActiveStreams configuredServerCount={0} controls={controls} />);
      await screen.findByText('No active streams at the moment.');
      expectTitleRowWithControls('Active Streams');
      expect(screen.getByText('0 Active')).toBeInTheDocument();
    } finally {
      delete resolved.getActiveStreams;
    }
  });
});

describe('BandwidthOverview', () => {
  it('renders the controls and only a screen-reader heading of its own', () => {
    render(<BandwidthOverview status={status} tempLimits={null} controls={controls} />);
    expect(screen.getByRole('button', { name: 'panel controls' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Download Bandwidth' })).toBeInTheDocument();
    expect(screen.getByRole('heading', { name: 'Upload Bandwidth' })).toBeInTheDocument();
    // Bridges the h1 → h4 gap for assistive tech without adding a visible title row.
    expect(screen.getByRole('heading', { name: 'Overview' })).toHaveClass('sr-only');
  });
});

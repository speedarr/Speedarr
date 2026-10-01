import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';

const { api } = vi.hoisted(() => ({
  api: { getBandwidthChartData: vi.fn(), getSystemStatus: vi.fn() },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { BandwidthChart } from './BandwidthChart';

// Audit B3-1: see StreamCountChart.test.tsx.
const empty = { data: [], start_time: '', end_time: '', interval_minutes: 0 };
const range = { label: 'Last 2 Hours', hours: 2 };
const status = { status: 'running', bandwidth: { download: { clients: [] }, upload: { clients: [] } } };

const renderChart = (dataInterval: 'raw' | 0.25 | 5) =>
  render(
    <BandwidthChart
      timeRange={range}
      setTimeRange={vi.fn()}
      dataInterval={dataInterval}
      setDataInterval={vi.fn()}
      timeRanges={[range]}
      configuredServerCount={1}
    />,
  );

describe('BandwidthChart request interval', () => {
  beforeEach(() => {
    api.getBandwidthChartData.mockReset();
    api.getBandwidthChartData.mockResolvedValue(empty);
    api.getSystemStatus.mockReset();
    api.getSystemStatus.mockResolvedValue(status);
  });

  it('asks for the display interval, 0 for raw, and refetches when it changes', async () => {
    const { rerender } = renderChart(0.25);
    await waitFor(() =>
      expect(api.getBandwidthChartData).toHaveBeenCalledWith({ hours: 2, interval_minutes: 0.25 }),
    );
    rerender(
      <BandwidthChart
        timeRange={range}
        setTimeRange={vi.fn()}
        dataInterval="raw"
        setDataInterval={vi.fn()}
        timeRanges={[range]}
        configuredServerCount={1}
      />,
    );
    await waitFor(() =>
      expect(api.getBandwidthChartData).toHaveBeenLastCalledWith({ hours: 2, interval_minutes: 0 }),
    );
  });
});

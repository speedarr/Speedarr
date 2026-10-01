import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';

const { api } = vi.hoisted(() => ({
  api: { getBandwidthChartData: vi.fn() },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { StreamCountChart } from './StreamCountChart';

// Audit B3-1: the API averages rows into the interval it is asked for, so the chart must ask for
// the interval it is about to display (0 = raw) and ask again when the picker changes.
const empty = { data: [], start_time: '', end_time: '', interval_minutes: 0 };
const range = { label: 'Last 2 Hours', hours: 2 };

describe('StreamCountChart request interval', () => {
  beforeEach(() => {
    api.getBandwidthChartData.mockReset();
    api.getBandwidthChartData.mockResolvedValue(empty);
  });

  it('asks for the display interval, 0 for raw, and refetches when it changes', async () => {
    const { rerender } = render(<StreamCountChart timeRange={range} dataInterval={0.25} />);
    await waitFor(() =>
      expect(api.getBandwidthChartData).toHaveBeenCalledWith({ hours: 2, interval_minutes: 0.25 }),
    );
    rerender(<StreamCountChart timeRange={range} dataInterval="raw" />);
    await waitFor(() =>
      expect(api.getBandwidthChartData).toHaveBeenLastCalledWith({ hours: 2, interval_minutes: 0 }),
    );
    rerender(<StreamCountChart timeRange={range} dataInterval={5} />);
    await waitFor(() =>
      expect(api.getBandwidthChartData).toHaveBeenLastCalledWith({ hours: 2, interval_minutes: 5 }),
    );
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, waitFor } from '@testing-library/react';

const { api } = vi.hoisted(() => ({
  api: { getSettingsSection: vi.fn(), getBandwidthChartData: vi.fn() },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { SNMPStatusBadge } from './SNMPStatusBadge';

// Audit B3-1: the badge decides "active" by point.snmp_download_speed/upload_speed !== null, and a
// bucketed point never carries null (missing/null counts as 0 in a bucket), so it must ask for raw rows.
const settings = { section: 'snmp', config: { enabled: true } };
const empty = { data: [], start_time: '', end_time: '', interval_minutes: 0 };

describe('SNMPStatusBadge request interval', () => {
  beforeEach(() => {
    api.getSettingsSection.mockReset();
    api.getSettingsSection.mockResolvedValue(settings);
    api.getBandwidthChartData.mockReset();
    api.getBandwidthChartData.mockResolvedValue(empty);
  });

  it('asks for raw rows', async () => {
    render(<SNMPStatusBadge />);
    await waitFor(() =>
      expect(api.getBandwidthChartData).toHaveBeenCalledWith({ hours: 1, interval_minutes: 0 }),
    );
  });
});

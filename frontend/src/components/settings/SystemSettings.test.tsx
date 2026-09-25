import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Audit F3b-1: the Polling Interval field stored parseInt of the raw value with no guard.
const { api } = vi.hoisted(() => ({
  api: {
    getSettingsSection: vi.fn(),
    updateSettingsSection: vi.fn(),
    checkVersion: vi.fn(),
    gatherLogs: vi.fn(),
  },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { SystemSettings } from './SystemSettings';
import { UnsavedChangesProvider } from '@/contexts/UnsavedChangesContext';

const config = { update_frequency: 5, log_level: 'INFO', speedarr_url: '', require_login: true };

const renderTab = () =>
  render(
    <UnsavedChangesProvider>
      <SystemSettings />
    </UnsavedChangesProvider>,
  );

describe('SystemSettings cleared numeric fields (audit F3b-1)', () => {
  beforeEach(() => {
    api.getSettingsSection.mockResolvedValue({ config: { ...config } });
    api.checkVersion.mockResolvedValue({
      current_version: 'dev', current_commit: 'unknown', current_branch: 'develop', update_available: false,
    });
    api.updateSettingsSection.mockReset();
    api.updateSettingsSection.mockResolvedValue({});
  });

  it('keeps the Polling Interval at its last value when cleared', async () => {
    renderTab();
    const input = await screen.findByLabelText('Polling Interval (seconds)');
    fireEvent.change(input, { target: { value: '' } });
    expect(input).toHaveValue(5);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(api.updateSettingsSection.mock.calls[0][1].update_frequency).toBe(5);
  });

  it('still stores a typed Polling Interval', async () => {
    renderTab();
    const input = await screen.findByLabelText('Polling Interval (seconds)');
    fireEvent.change(input, { target: { value: '10' } });
    expect(input).toHaveValue(10);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(api.updateSettingsSection.mock.calls[0][1].update_frequency).toBe(10);
  });
});

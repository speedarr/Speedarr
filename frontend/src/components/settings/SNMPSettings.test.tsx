import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Audit F3b-1: the Port field stored parseInt of the raw value with no guard.
const { api } = vi.hoisted(() => ({
  api: {
    getSettingsSection: vi.fn(),
    updateSettingsSection: vi.fn(),
    testSNMPConnection: vi.fn(),
    discoverSNMPInterfaces: vi.fn(),
    pollSNMPSpeeds: vi.fn(),
  },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { SNMPSettings } from './SNMPSettings';
import { UnsavedChangesProvider } from '@/contexts/UnsavedChangesContext';

const config = { enabled: true, host: '10.0.0.1', port: 161, version: 'v2c', community: '***REDACTED***', interface: '' };

const renderTab = () =>
  render(
    <UnsavedChangesProvider>
      <SNMPSettings />
    </UnsavedChangesProvider>,
  );

describe('SNMPSettings cleared numeric fields (audit F3b-1)', () => {
  beforeEach(() => {
    api.getSettingsSection.mockResolvedValue({ config: { ...config } });
    api.updateSettingsSection.mockReset();
    api.updateSettingsSection.mockResolvedValue({});
  });

  it('keeps the Port at its last value when cleared', async () => {
    renderTab();
    const input = await screen.findByLabelText('Port');
    fireEvent.change(input, { target: { value: '' } });
    expect(input).toHaveValue(161);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(api.updateSettingsSection.mock.calls[0][1].port).toBe(161);
  });

  it('still stores a typed Port', async () => {
    renderTab();
    const input = await screen.findByLabelText('Port');
    fireEvent.change(input, { target: { value: '1161' } });
    expect(input).toHaveValue(1161);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(api.updateSettingsSection.mock.calls[0][1].port).toBe(1161);
  });
});

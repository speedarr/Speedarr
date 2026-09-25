import { describe, it, expect, vi, beforeEach } from 'vitest';
import React from 'react';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const { api } = vi.hoisted(() => ({
  api: {
    getSettingsSection: vi.fn(),
    updateSettingsSection: vi.fn(),
  },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { HistorySettings } from './HistorySettings';
import { UnsavedChangesProvider, useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';
import { UnsavedChangesWarning } from '@/components/settings/UnsavedChangesWarning';

// The sidebar's way of leaving the page: arm a destination and raise the banner.
const Leave: React.FC = () => {
  const { setPendingNavigation, triggerWarning } = useUnsavedChangesContext();
  return <button onClick={() => { setPendingNavigation('/'); triggerWarning(); }}>Leave</button>;
};

const renderTab = () =>
  render(
    <UnsavedChangesProvider>
      <HistorySettings />
      <Leave />
      <UnsavedChangesWarning />
    </UnsavedChangesProvider>,
  );

describe("HistorySettings and the banner's Save Now", () => {
  beforeEach(() => {
    api.getSettingsSection.mockResolvedValue({ config: { retention_days: 3 } });
    api.updateSettingsSection.mockReset();
    api.updateSettingsSection.mockResolvedValue({});
  });

  // The verifier's browser reproduction: 3 -> 17 -> 42, Save Now, and the API held 17.
  it('sends the value at the click, not the value at the first edit (audit T5-1)', async () => {
    renderTab();
    const input = await screen.findByLabelText('Retention Period (days)');
    fireEvent.change(input, { target: { value: '17' } });
    fireEvent.change(input, { target: { value: '42' } });
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save Now' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(api.updateSettingsSection).toHaveBeenCalledWith('history', { retention_days: 42 });
    await waitFor(() => expect(screen.queryByText('You have unsaved changes')).toBeNull());
    expect(input).toHaveValue(42);
  });

  it('keeps the banner and the edit when the write is refused (audit T5-2)', async () => {
    api.updateSettingsSection.mockRejectedValue(new Error('write refused'));
    renderTab();
    const input = await screen.findByLabelText('Retention Period (days)');
    fireEvent.change(input, { target: { value: '42' } });
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save Now' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(await screen.findByText('write refused')).toBeInTheDocument();
    expect(screen.getByText('You have unsaved changes')).toBeInTheDocument();
    expect(input).toHaveValue(42);
  });
});

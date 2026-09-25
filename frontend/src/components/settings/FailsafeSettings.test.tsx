import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Media Server Timeout is the hold on a silent server's last-known streams (#102): the help text must say so.
const { api } = vi.hoisted(() => ({
  api: {
    getSettingsSection: vi.fn(),
    getDownloadClients: vi.fn(),
    updateSettingsSection: vi.fn(),
  },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { FailsafeSettings } from './FailsafeSettings';
import { UnsavedChangesProvider } from '@/contexts/UnsavedChangesContext';

const sections: Record<string, unknown> = {
  failsafe: {
    plex_timeout: 300,
    shutdown_download_speed: null,
    shutdown_upload_speed: null,
    shutdown_download_client_percents: {},
    shutdown_upload_client_percents: {},
  },
  bandwidth: { download: { total_limit: 100 }, upload: { total_limit: 50 } },
};

describe('FailsafeSettings', () => {
  it("describes the Media Server Timeout as the hold on a silent server's streams", async () => {
    api.getSettingsSection.mockImplementation(async (section: string) => ({ config: sections[section] }));
    api.getDownloadClients.mockResolvedValue({ clients: [] });
    render(
      <UnsavedChangesProvider>
        <FailsafeSettings />
      </UnsavedChangesProvider>,
    );
    expect(await screen.findByLabelText('Media Server Timeout (seconds)')).toHaveValue(300);
    expect(screen.getByText(/last-known streams stay reserved/i)).toBeInTheDocument();
    expect(screen.queryByText(/assume no active streams/i)).toBeNull();
  });
});

// Audit F3b-1: a cleared numeric field held NaN, which the request sent as null.
const renderFailsafe = () => {
  api.getSettingsSection.mockImplementation(async (section: string) => ({
    config: JSON.parse(JSON.stringify(sections[section])),
  }));
  api.getDownloadClients.mockResolvedValue({ clients: [] });
  api.updateSettingsSection.mockReset();
  api.updateSettingsSection.mockResolvedValue({});
  render(
    <UnsavedChangesProvider>
      <FailsafeSettings />
    </UnsavedChangesProvider>,
  );
};

describe('FailsafeSettings cleared numeric fields (audit F3b-1)', () => {
  it('keeps the Media Server Timeout at its last value when the field is cleared', async () => {
    renderFailsafe();
    const input = await screen.findByLabelText('Media Server Timeout (seconds)');
    fireEvent.change(input, { target: { value: '' } });
    expect(input).toHaveValue(300);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(api.updateSettingsSection.mock.calls[0][1].plex_timeout).toBe(300);
  });

  it('still stores a typed Media Server Timeout', async () => {
    renderFailsafe();
    const input = await screen.findByLabelText('Media Server Timeout (seconds)');
    fireEvent.change(input, { target: { value: '45' } });
    expect(input).toHaveValue(45);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(api.updateSettingsSection.mock.calls[0][1].plex_timeout).toBe(45);
  });
});

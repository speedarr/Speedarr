import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

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

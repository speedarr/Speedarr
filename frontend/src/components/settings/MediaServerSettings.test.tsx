import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { AxiosError, type AxiosResponse } from 'axios';

// Emby and Jellyfin left experimental (#32): the card must not carry the badge or the feedback note.
const { api } = vi.hoisted(() => ({
  api: {
    getMediaServers: vi.fn(),
    updateMediaServers: vi.fn(),
    testConnection: vi.fn(),
  },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { MediaServerSettings } from './MediaServerSettings';
import { UnsavedChangesProvider } from '@/contexts/UnsavedChangesContext';

const embyServer = {
  id: 'emby-1',
  name: 'Emby',
  type: 'emby',
  enabled: true,
  url: 'http://192.168.1.100:8096',
  token: '',
  api_key: 'abc',
  include_lan_streams: false,
  lan_networks: [],
};

describe('MediaServerSettings', () => {
  it('renders an Emby server without an Experimental badge or feedback note', async () => {
    api.getMediaServers.mockResolvedValue({ servers: [embyServer] });
    render(
      <UnsavedChangesProvider>
        <MediaServerSettings />
      </UnsavedChangesProvider>,
    );
    expect((await screen.findAllByText('Emby')).length).toBeGreaterThan(0);
    expect(screen.queryByText('Experimental')).toBeNull();
    expect(screen.queryByText(/support is experimental/i)).toBeNull();
  });

  // A save that moves a stored secret to a new address is refused with a 400 (audit NEW-5): the
  // panel shows the server's reason and keeps the edit so the user can type the secret and retry.
  it('shows the refusal reason and keeps the edit when a save is refused', async () => {
    const plex = { ...embyServer, id: 'plex-1', name: 'Plex', type: 'plex', url: 'http://plex:32400',
                   token: '***REDACTED***', api_key: '' };
    const detail = 'Media server "Plex": enter the token to change its address';
    api.getMediaServers.mockClear().mockResolvedValue({ servers: [plex] });
    api.updateMediaServers.mockRejectedValue(new AxiosError(
      'Request failed with status code 400', 'ERR_BAD_REQUEST', undefined, undefined,
      { status: 400, data: { detail } } as AxiosResponse,
    ));
    render(
      <UnsavedChangesProvider>
        <MediaServerSettings />
      </UnsavedChangesProvider>,
    );
    fireEvent.click(await screen.findByRole('button', { expanded: false }));
    fireEvent.change(screen.getByDisplayValue('http://plex:32400'), { target: { value: 'http://new-plex:32400' } });
    fireEvent.click(screen.getByRole('button', { name: /Save All Changes/ }));

    expect(await screen.findByText(detail)).toBeTruthy();
    expect(screen.getByDisplayValue('http://new-plex:32400')).toBeTruthy();
    expect(api.getMediaServers).toHaveBeenCalledTimes(1);
  });
});

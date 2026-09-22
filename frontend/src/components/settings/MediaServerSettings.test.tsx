import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

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
});

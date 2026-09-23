import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';

vi.mock('@/api/client', () => ({ apiClient: { testConnection: vi.fn() } }));

import { DownloadClientsStep } from './DownloadClientsStep';
import { DownloadClientConfig } from '../types';

// #109: client cards had no Display Name field, so every qBittorrent was "qBittorrent" until
// renamed in Settings. The add dropdown is a Radix Select that jsdom can't drive without
// user-event, so the numbering rule itself is covered by lib/defaultNames.test.ts.
const client = (id: string, name: string): DownloadClientConfig => ({
  id, type: 'qbittorrent', name, enabled: true, url: 'http://qbittorrent:8080',
  username: '', password: '', api_key: '', color: '#3b82f6', supports_upload: true,
});

describe('DownloadClientsStep display names', () => {
  it('shows an editable Display Name on each card', () => {
    const onDataChange = vi.fn();
    render(
      <DownloadClientsStep
        data={[client('a', 'qBittorrent'), client('b', 'qBittorrent 2')]}
        onDataChange={onDataChange}
        showValidation={false}
        errors={[]}
        isLoading={false}
      />,
    );
    const inputs = screen.getAllByLabelText('Display name') as HTMLInputElement[];
    expect(inputs.map(i => i.value)).toEqual(['qBittorrent', 'qBittorrent 2']);

    fireEvent.change(inputs[1], { target: { value: 'Seedbox' } });
    const calls = onDataChange.mock.calls;
    const latest = calls[calls.length - 1][0] as DownloadClientConfig[];
    expect(latest.map(c => c.name)).toEqual(['qBittorrent', 'Seedbox']);
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// The API client is replaced by three spies; each test seeds the settings sections it needs.
const { api, sections } = vi.hoisted(() => ({
  api: {
    getSettingsSection: vi.fn(),
    getDownloadClients: vi.fn(),
    updateSettingsSection: vi.fn(),
  },
  sections: {} as Record<string, unknown>,
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { BandwidthSettings } from './BandwidthSettings';
import { UnsavedChangesProvider } from '@/contexts/UnsavedChangesContext';

const bandwidthSection = () => ({
  demand_aware_allocation: true,
  download: { total_limit: 100, min_limit_mbps: 1, inactive_safety_net_percent: 10, client_percents: {} },
  upload: { total_limit: 50, min_limit_mbps: 1, upload_client_percents: {} },
  streams: { bandwidth_calculation: 'auto', manual_per_stream: 10, overhead_percent: 100, download_reserve_percent: 20 },
});

function renderWithFailsafe(failsafe: { shutdown_download_speed: number | null; shutdown_upload_speed: number | null }) {
  sections.bandwidth = bandwidthSection();
  sections.failsafe = {
    plex_timeout: 300,
    ...failsafe,
    shutdown_download_client_percents: {},
    shutdown_upload_client_percents: {},
  };
  api.getSettingsSection.mockImplementation(async (section: string) => ({
    config: JSON.parse(JSON.stringify(sections[section])),
  }));
  api.getDownloadClients.mockResolvedValue({ clients: [] });
  api.updateSettingsSection.mockResolvedValue({});
  render(
    <UnsavedChangesProvider>
      <BandwidthSettings />
    </UnsavedChangesProvider>,
  );
}

async function raiseDownloadLimitAndSave(to: number) {
  const input = await screen.findByLabelText('Total Download Limit (Mbps)');
  fireEvent.change(input, { target: { value: String(to) } });
  fireEvent.click(screen.getByRole('button', { name: 'Save All Bandwidth Settings' }));
  await waitFor(() =>
    expect(api.updateSettingsSection).toHaveBeenCalledWith(
      'bandwidth',
      expect.objectContaining({ download: expect.objectContaining({ total_limit: to }) }),
    ),
  );
  await screen.findByText(/Bandwidth settings saved/);
}

const failsafeSaves = () => api.updateSettingsSection.mock.calls.filter(([section]) => section === 'failsafe');

describe('BandwidthSettings save and the failsafe speeds', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps failsafe speeds the user customised when a limit changes', async () => {
    renderWithFailsafe({ shutdown_download_speed: 25, shutdown_upload_speed: 5 });
    await raiseDownloadLimitAndSave(200);
    expect(failsafeSaves()).toEqual([]);
  });

  it('moves a failsafe speed still at its 10% default along with the limit', async () => {
    renderWithFailsafe({ shutdown_download_speed: 10, shutdown_upload_speed: null });
    await raiseDownloadLimitAndSave(200);
    expect(failsafeSaves()).toHaveLength(1);
    expect(failsafeSaves()[0][1]).toMatchObject({ shutdown_download_speed: 20, shutdown_upload_speed: null });
  });
});

// Audit F3b-1: four numeric handlers stored parseFloat of the raw value with no guard, so a
// cleared field held NaN and the save sent null. The Inactive Safety Net input exists in two
// branches (two clients, three or more), so both are exercised.
const client = (id: string) => ({ id, type: 'qbittorrent', name: id, enabled: true, color: '#3b82f6', supports_upload: true });

function renderWithMode(mode: 'manual' | 'auto', clients: ReturnType<typeof client>[] = []) {
  const bandwidth = bandwidthSection();
  bandwidth.streams.bandwidth_calculation = mode;
  sections.bandwidth = bandwidth;
  sections.failsafe = {
    plex_timeout: 300,
    shutdown_download_speed: null,
    shutdown_upload_speed: null,
    shutdown_download_client_percents: {},
    shutdown_upload_client_percents: {},
  };
  api.getSettingsSection.mockImplementation(async (section: string) => ({
    config: JSON.parse(JSON.stringify(sections[section])),
  }));
  api.getDownloadClients.mockResolvedValue({ clients });
  api.updateSettingsSection.mockResolvedValue({});
  render(
    <UnsavedChangesProvider>
      <BandwidthSettings />
    </UnsavedChangesProvider>,
  );
}

const savedBandwidth = () => api.updateSettingsSection.mock.calls.find(([section]) => section === 'bandwidth')![1];

async function clearAndSave(label: string, loaded: number) {
  const input = await screen.findByLabelText(label);
  fireEvent.change(input, { target: { value: '' } });
  expect(input).toHaveValue(loaded);
  fireEvent.click(screen.getByRole('button', { name: 'Save All Bandwidth Settings' }));
  await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalled());
}

describe('BandwidthSettings cleared numeric fields (audit F3b-1)', () => {
  beforeEach(() => {
    vi.clearAllMocks();
  });

  it('keeps Bandwidth Per Stream at its last value when cleared, and takes a decimal', async () => {
    renderWithMode('manual');
    const input = await screen.findByLabelText('Bandwidth Per Stream (Mbps)');
    fireEvent.change(input, { target: { value: '1.5' } });
    expect(input).toHaveValue(1.5);
    fireEvent.change(input, { target: { value: '' } });
    expect(input).toHaveValue(1.5);
    fireEvent.click(screen.getByRole('button', { name: 'Save All Bandwidth Settings' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalled());
    expect(savedBandwidth().streams.manual_per_stream).toBe(1.5);
  });

  it('keeps Protocol Overhead % at its last value when cleared', async () => {
    renderWithMode('auto');
    await clearAndSave('Protocol Overhead %', 100);
    expect(savedBandwidth().streams.overhead_percent).toBe(100);
  });

  it('keeps Inactive Safety Net % at its last value when cleared (two clients)', async () => {
    renderWithMode('auto', [client('a'), client('b')]);
    await clearAndSave('Inactive Safety Net %', 10);
    expect(savedBandwidth().download.inactive_safety_net_percent).toBe(10);
  });

  it('keeps Inactive Safety Net % at its last value when cleared (three clients)', async () => {
    renderWithMode('auto', [client('a'), client('b'), client('c')]);
    await clearAndSave('Inactive Safety Net %', 10);
    expect(savedBandwidth().download.inactive_safety_net_percent).toBe(10);
  });
});

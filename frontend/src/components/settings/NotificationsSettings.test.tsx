import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

const { api } = vi.hoisted(() => ({
  api: {
    getSettingsSection: vi.fn(),
    updateSettingsSection: vi.fn(),
    testConnection: vi.fn(),
  },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { NotificationsSettings } from './NotificationsSettings';
import { UnsavedChangesProvider } from '@/contexts/UnsavedChangesContext';

// #106: priority existed in the config for Pushover, Gotify and ntfy but no card showed it.
const events = ['stream_started'];
const config = {
  discord: { enabled: false, webhook_url: '', events },
  pushover: { enabled: true, user_key: '***REDACTED***', api_token: '***REDACTED***', priority: 1, events },
  telegram: { enabled: false, bot_token: '', chat_id: '', events },
  gotify: { enabled: true, server_url: 'http://gotify:80', app_token: '***REDACTED***', priority: 5, events },
  ntfy: { enabled: true, server_url: 'https://ntfy.sh', topic: 'speedarr', priority: 5, events },
  stream_count_threshold: null,
  stream_bitrate_threshold: null,
  threshold_cooldown_minutes: 0,
};

const renderTab = () =>
  render(
    <UnsavedChangesProvider>
      <NotificationsSettings />
    </UnsavedChangesProvider>,
  );

describe('NotificationsSettings priority', () => {
  beforeEach(() => {
    api.getSettingsSection.mockResolvedValue({ config });
    api.updateSettingsSection.mockReset();
    api.updateSettingsSection.mockResolvedValue({});
  });

  it('shows each enabled agent\'s saved priority', async () => {
    renderTab();
    expect(await screen.findByLabelText('Pushover priority')).toHaveTextContent('High');
    expect(screen.getByLabelText('ntfy priority')).toHaveTextContent('Max');
    expect((screen.getByLabelText('Gotify priority') as HTMLInputElement).value).toBe('5');
  });

  it('saves a changed Gotify priority with the section', async () => {
    renderTab();
    const input = await screen.findByLabelText('Gotify priority');
    fireEvent.change(input, { target: { value: '8' } });
    fireEvent.click(screen.getByRole('button', { name: /^save/i }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    const [section, payload] = api.updateSettingsSection.mock.calls[0];
    expect(section).toBe('notifications');
    expect(payload.gotify.priority).toBe(8);
  });
});

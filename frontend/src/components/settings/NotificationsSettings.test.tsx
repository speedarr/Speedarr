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

// Audit T1-3: chat id and topic are secrets; the API returns the placeholder for a saved value.
const maskedConfig = {
  ...config,
  telegram: { enabled: true, bot_token: '***REDACTED***', chat_id: '***REDACTED***', events },
  ntfy: { ...config.ntfy, topic: '***REDACTED***' },
};

describe('NotificationsSettings masked chat id and topic (audit T1-3)', () => {
  beforeEach(() => {
    api.getSettingsSection.mockResolvedValue({ config: maskedConfig });
    api.updateSettingsSection.mockReset();
    api.updateSettingsSection.mockResolvedValue({});
    api.testConnection.mockReset();
    api.testConnection.mockResolvedValue({ success: true, message: 'ok' });
  });

  it('shows a saved chat id and topic as set, never their values', async () => {
    renderTab();
    const chat = (await screen.findByLabelText('Chat ID')) as HTMLInputElement;
    expect(chat.value).toBe('');
    expect(chat.placeholder).toBe('Chat ID is set');
    expect(chat.type).toBe('password');
    const topic = screen.getByLabelText('Topic') as HTMLInputElement;
    expect(topic.value).toBe('');
    expect(topic.placeholder).toBe('Topic is set');
    expect(topic.type).toBe('password');
  });

  it('typing over the placeholder saves the new value and leaves the untouched one as the placeholder', async () => {
    renderTab();
    const topic = await screen.findByLabelText('Topic');
    fireEvent.change(topic, { target: { value: 'new-topic' } });
    fireEvent.click(screen.getByRole('button', { name: /^save/i }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    const [, payload] = api.updateSettingsSection.mock.calls[0];
    expect(payload.ntfy.topic).toBe('new-topic');
    expect(payload.telegram.chat_id).toBe('***REDACTED***');
  });

  it('tests ntfy and Telegram against the saved values when they are masked', async () => {
    renderTab();
    await screen.findByLabelText('Topic');
    fireEvent.click(screen.getByRole('button', { name: /test ntfy/i }));
    await waitFor(() => expect(api.testConnection).toHaveBeenCalledWith('ntfy', expect.anything(), true));
    await waitFor(() => expect(screen.getByRole('button', { name: /test telegram/i })).toBeEnabled());
    fireEvent.click(screen.getByRole('button', { name: /test telegram/i }));
    await waitFor(() => expect(api.testConnection).toHaveBeenCalledWith('telegram', expect.anything(), true));
  });

  it('sends "use existing" for Telegram when only the chat id is masked', async () => {
    api.getSettingsSection.mockResolvedValue({
      config: {
        ...maskedConfig,
        telegram: { enabled: true, bot_token: '123456:AUDITMARK-fresh-bot-token', chat_id: '***REDACTED***', events },
      },
    });
    renderTab();
    await screen.findByLabelText('Chat ID');
    fireEvent.click(screen.getByRole('button', { name: /test telegram/i }));
    await waitFor(() => expect(api.testConnection).toHaveBeenCalledWith('telegram', expect.anything(), true));
  });
});

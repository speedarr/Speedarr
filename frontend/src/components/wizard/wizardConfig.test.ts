import { describe, it, expect } from 'vitest';
import { validateNotifications } from './wizardConfig';
import { DEFAULT_WIZARD_STATE, NotificationsConfig, WizardState } from './types';

// #107: the wizard let Pushover, Telegram, Gotify or ntfy be enabled with empty
// credentials because the validator only ever looked at Discord.
const allOff: NotificationsConfig = {
  discord: { enabled: false, webhook_url: '' },
  pushover: { enabled: false, user_key: '', api_token: '' },
  telegram: { enabled: false, bot_token: '', chat_id: '' },
  gotify: { enabled: false, server_url: '', app_token: '' },
  ntfy: { enabled: false, server_url: 'https://ntfy.sh', topic: '' },
};

const stateWith = (overrides: Partial<NotificationsConfig>): WizardState => ({
  ...DEFAULT_WIZARD_STATE,
  notifications: { ...allOff, ...overrides },
});

describe('validateNotifications', () => {
  it('passes when no agent is enabled', async () => {
    expect(await validateNotifications(stateWith({}))).toEqual({ valid: true, errors: [] });
  });

  it('still rejects Discord without a webhook URL', async () => {
    const result = await validateNotifications(stateWith({ discord: { enabled: true, webhook_url: '  ' } }));
    expect(result.valid).toBe(false);
    expect(result.errors.join(' ')).toMatch(/discord/i);
  });

  it('rejects Pushover enabled without credentials', async () => {
    const result = await validateNotifications(stateWith({ pushover: { enabled: true, user_key: '', api_token: '' } }));
    expect(result.valid).toBe(false);
    expect(result.errors.join(' ')).toMatch(/pushover/i);
  });

  it('accepts Pushover enabled with credentials', async () => {
    const result = await validateNotifications(stateWith({ pushover: { enabled: true, user_key: 'u', api_token: 't' } }));
    expect(result).toEqual({ valid: true, errors: [] });
  });

  it('rejects Telegram without a bot token or chat ID', async () => {
    const result = await validateNotifications(stateWith({ telegram: { enabled: true, bot_token: 'b', chat_id: '' } }));
    expect(result.valid).toBe(false);
    expect(result.errors.join(' ')).toMatch(/telegram/i);
  });

  it('rejects Gotify without a server URL or app token', async () => {
    const result = await validateNotifications(stateWith({ gotify: { enabled: true, server_url: '', app_token: 't' } }));
    expect(result.valid).toBe(false);
    expect(result.errors.join(' ')).toMatch(/gotify/i);
  });

  it('rejects ntfy without a topic', async () => {
    const result = await validateNotifications(stateWith({ ntfy: { enabled: true, server_url: 'https://ntfy.sh', topic: '' } }));
    expect(result.valid).toBe(false);
    expect(result.errors.join(' ')).toMatch(/ntfy/i);
  });

  it('reports every misconfigured agent, not just the first', async () => {
    const result = await validateNotifications(stateWith({
      pushover: { enabled: true, user_key: '', api_token: '' },
      ntfy: { enabled: true, server_url: 'https://ntfy.sh', topic: '' },
    }));
    expect(result.errors.join(' ')).toMatch(/pushover/i);
    expect(result.errors.join(' ')).toMatch(/ntfy/i);
  });
});

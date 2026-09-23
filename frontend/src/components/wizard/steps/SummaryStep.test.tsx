import { describe, it, expect, vi } from 'vitest';
import { render, screen } from '@testing-library/react';

// #107: the Summary step reported only Discord, so enabling Pushover alone read
// "Notifications disabled". The step only needs goToStep from the wizard context.
vi.mock('../WizardContext', () => ({ useWizard: () => ({ goToStep: vi.fn() }) }));

import { SummaryStep } from './SummaryStep';
import { DEFAULT_WIZARD_STATE, NotificationsConfig, WizardState } from '../types';

const allOff: NotificationsConfig = {
  discord: { enabled: false, webhook_url: '' },
  pushover: { enabled: false, user_key: '', api_token: '' },
  telegram: { enabled: false, bot_token: '', chat_id: '' },
  gotify: { enabled: false, server_url: '', app_token: '' },
  ntfy: { enabled: false, server_url: 'https://ntfy.sh', topic: '' },
};

const renderWith = (overrides: Partial<NotificationsConfig>) => {
  const state: WizardState = { ...DEFAULT_WIZARD_STATE, notifications: { ...allOff, ...overrides } };
  render(<SummaryStep data={state} onDataChange={() => {}} showValidation={false} errors={[]} isLoading={false} />);
};

describe('SummaryStep notifications', () => {
  it('lists Pushover when it is the only enabled agent', () => {
    renderWith({ pushover: { enabled: true, user_key: 'u', api_token: 't' } });
    expect(screen.getByText('Pushover')).toBeInTheDocument();
    expect(screen.queryByText('Notifications disabled')).toBeNull();
  });

  it('lists every enabled agent', () => {
    renderWith({
      discord: { enabled: true, webhook_url: 'https://discord.example/hook' },
      ntfy: { enabled: true, server_url: 'https://ntfy.sh', topic: 'speedarr' },
    });
    expect(screen.getByText('Discord')).toBeInTheDocument();
    expect(screen.getByText('ntfy')).toBeInTheDocument();
    expect(screen.queryByText('Pushover')).toBeNull();
  });

  it('says notifications are disabled only when no agent is enabled', () => {
    renderWith({});
    expect(screen.getByText('Notifications disabled')).toBeInTheDocument();
  });
});

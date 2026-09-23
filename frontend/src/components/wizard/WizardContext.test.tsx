import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, act } from '@testing-library/react';
import { MemoryRouter } from 'react-router';

// #107: Complete Setup posted failsafe fields that FailsafeConfig doesn't have
// (enabled, shutdown_delay, restoration_delay, minimum_holding_time) and a
// streams block whose manual_per_stream disagreed with the backend default.
const { api } = vi.hoisted(() => ({
  api: {
    initializeConfig: vi.fn().mockResolvedValue(undefined),
    updateMediaServers: vi.fn().mockResolvedValue(undefined),
    updateDownloadClients: vi.fn().mockResolvedValue(undefined),
    updateSettingsSection: vi.fn().mockResolvedValue(undefined),
    completeSetup: vi.fn().mockResolvedValue(undefined),
  },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { WizardProvider, useWizard } from './WizardContext';
import { DEFAULT_WIZARD_STATE } from './types';

let finish: () => Promise<void> = async () => {};
const Grab = () => {
  finish = useWizard().finishWizard;
  return null;
};

const sectionPayload = (section: string) =>
  api.updateSettingsSection.mock.calls.find(([name]) => name === section)?.[1];

describe('finishWizard payloads', () => {
  beforeEach(() => {
    api.updateSettingsSection.mockClear();
    localStorage.setItem('speedarr_wizard_state', JSON.stringify({
      ...DEFAULT_WIZARD_STATE,
      bandwidth: { download: { total_limit: 100 }, upload: { total_limit: 50 } },
    }));
  });

  it('posts only the two shutdown speeds to the failsafe section', async () => {
    render(<MemoryRouter><WizardProvider><Grab /></WizardProvider></MemoryRouter>);
    await act(async () => { await finish(); });
    expect(sectionPayload('failsafe')).toEqual({
      shutdown_download_speed: 10,
      shutdown_upload_speed: 5,
    });
  });

  it('leaves the streams settings at their backend defaults', async () => {
    render(<MemoryRouter><WizardProvider><Grab /></WizardProvider></MemoryRouter>);
    await act(async () => { await finish(); });
    expect(sectionPayload('bandwidth')).not.toHaveProperty('streams');
  });
});

import { describe, it, expect, vi, beforeEach } from 'vitest';
import { render, screen, fireEvent, waitFor } from '@testing-library/react';

// Audit F3b-1: the two hold-time fields stored parseInt of the raw value with no guard, so a
// cleared field held NaN and the save sent null.
const { api } = vi.hoisted(() => ({
  api: {
    getSettingsSection: vi.fn(),
    updateSettingsSection: vi.fn(),
  },
}));
vi.mock('@/api/client', () => ({ apiClient: api }));

import { RestorationSettings } from './RestorationSettings';
import { UnsavedChangesProvider } from '@/contexts/UnsavedChangesContext';

const config = { delays: { episode_end: 600, movie_end: 1800 } };

const renderTab = () =>
  render(
    <UnsavedChangesProvider>
      <RestorationSettings />
    </UnsavedChangesProvider>,
  );

const saved = () => api.updateSettingsSection.mock.calls[0][1];

describe('RestorationSettings cleared numeric fields (audit F3b-1)', () => {
  beforeEach(() => {
    api.getSettingsSection.mockResolvedValue({ config: JSON.parse(JSON.stringify(config)) });
    api.updateSettingsSection.mockReset();
    api.updateSettingsSection.mockResolvedValue({});
  });

  it.each([
    ['Episode End Hold Time (seconds)', 'episode_end', 600],
    ['Movie End Hold Time (seconds)', 'movie_end', 1800],
  ])('keeps %s at its last value when cleared', async (label, key, loaded) => {
    renderTab();
    const input = await screen.findByLabelText(label);
    fireEvent.change(input, { target: { value: '' } });
    expect(input).toHaveValue(loaded);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(saved().delays[key]).toBe(loaded);
  });

  it('still stores a typed hold time', async () => {
    renderTab();
    const input = await screen.findByLabelText('Movie End Hold Time (seconds)');
    fireEvent.change(input, { target: { value: '900' } });
    expect(input).toHaveValue(900);
    fireEvent.click(screen.getByRole('button', { name: 'Save Changes' }));
    await waitFor(() => expect(api.updateSettingsSection).toHaveBeenCalledTimes(1));
    expect(saved().delays.movie_end).toBe(900);
  });
});

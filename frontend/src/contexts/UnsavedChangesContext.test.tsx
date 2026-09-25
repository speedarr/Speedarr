import { describe, it, expect, vi, beforeEach } from 'vitest';
import React, { useRef, useState } from 'react';
import { render, screen, fireEvent, waitFor, act } from '@testing-library/react';
import { UnsavedChangesProvider, useUnsavedChangesContext } from './UnsavedChangesContext';
import { UnsavedChangesWarning } from '@/components/settings/UnsavedChangesWarning';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useSettingsTab } from '@/hooks/useSettingsTab';

// The banner scrolls a panel's Save button into view; the jsdom no-op lives in test/setup.ts.
const scrollIntoView = vi.spyOn(Element.prototype, 'scrollIntoView');

type Save = (value: number) => Promise<boolean>;

// A stand-in for a settings panel: one number in state, the real dirty tracking, the real
// registration through useSettingsTab, a Save button that carries the ref the banner scrolls to.
const Probe: React.FC<{ tabId: string; initial: number; onSave: Save }> = ({ tabId, initial, onSave }) => {
  const [config, setConfig] = useState({ n: initial });
  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<{ n: number }>({ n: initial });
  const isDirty = hasUnsavedChanges(config);

  const handleSave = async (): Promise<boolean> => {
    const ok = await onSave(config.n);
    if (ok) resetOriginal(config);
    return ok;
  };

  useSettingsTab(tabId, isDirty, saveButtonRef, () => handleSave(), () => {
    const original = discardChanges();
    if (original) setConfig(original);
  });

  return (
    <div>
      <label htmlFor={`${tabId}-value`}>{tabId} value</label>
      <input
        id={`${tabId}-value`}
        type="number"
        value={config.n}
        onChange={(e) => { const v = parseInt(e.target.value); if (!isNaN(v)) setConfig({ n: v }); }}
      />
      <button ref={saveButtonRef} onClick={handleSave}>{tabId} save</button>
    </div>
  );
};

// What Dashboard and Settings put around the panels: the two ways to leave (sidebar navigation,
// tab strip) and a readout of the state their navigation effects act on.
const Shell: React.FC<{ children: React.ReactNode }> = ({ children }) => {
  const { hasDirtyTabs, pendingNavigation, pendingTabChange, setPendingNavigation, setPendingTabChange, triggerWarning } =
    useUnsavedChangesContext();
  return (
    <>
      {children}
      <button onClick={() => { setPendingNavigation('/'); triggerWarning(); }}>Leave</button>
      <button onClick={() => { setPendingTabChange('bandwidth'); triggerWarning(); }}>Switch tab</button>
      <div data-testid="readout">{`dirty:${hasDirtyTabs} nav:${pendingNavigation ?? 'none'} tab:${pendingTabChange ?? 'none'}`}</div>
      <UnsavedChangesWarning />
    </>
  );
};

const Harness: React.FC<{ children: React.ReactNode }> = ({ children }) => (
  <UnsavedChangesProvider>
    <Shell>{children}</Shell>
  </UnsavedChangesProvider>
);

const readout = () => screen.getByTestId('readout');
const banner = () => screen.queryByText('You have unsaved changes');
const edit = (tabId: string, value: number) =>
  fireEvent.change(screen.getByLabelText(`${tabId} value`), { target: { value: String(value) } });
const leaveAndSaveNow = async () => {
  fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
  fireEvent.click(await screen.findByRole('button', { name: 'Save Now' }));
};

beforeEach(() => {
  scrollIntoView.mockClear();
});

describe('Save Now reads the live form (audit T5-1)', () => {
  it('saves the value at the click, not the value at the first edit', async () => {
    const save = vi.fn<Save>(async () => true);
    render(<Harness><Probe tabId="probe" initial={3} onSave={save} /></Harness>);
    edit('probe', 17);
    edit('probe', 42);
    await leaveAndSaveNow();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith(42);
    await waitFor(() => expect(readout()).toHaveTextContent('dirty:false'));
    expect(banner()).toBeNull();
  });

  it('unregisters the panel on unmount', async () => {
    const { rerender } = render(<Harness><Probe tabId="probe" initial={3} onSave={async () => true} /></Harness>);
    edit('probe', 4);
    expect(readout()).toHaveTextContent('dirty:true');
    rerender(<Harness><></></Harness>);
    await waitFor(() => expect(readout()).toHaveTextContent('dirty:false'));
  });

  // main.tsx mounts the app under StrictMode, which runs every effect twice in development.
  it('behaves the same under StrictMode', async () => {
    const save = vi.fn<Save>(async () => true);
    render(
      <React.StrictMode>
        <Harness><Probe tabId="probe" initial={3} onSave={save} /></Harness>
      </React.StrictMode>,
    );
    edit('probe', 17);
    edit('probe', 42);
    expect(readout()).toHaveTextContent('dirty:true');
    await leaveAndSaveNow();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(save).toHaveBeenCalledWith(42);
    await waitFor(() => expect(readout()).toHaveTextContent('dirty:false'));
  });
});

describe('Save Now that is refused or fails (audit T5-2)', () => {
  it('keeps the banner and the destination when the save reports false, and points at the panel', async () => {
    const save = vi.fn<Save>(async () => false);
    render(<Harness><Probe tabId="probe" initial={3} onSave={save} /></Harness>);
    edit('probe', 42);
    await leaveAndSaveNow();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(banner()).not.toBeNull();
    expect(readout()).toHaveTextContent('dirty:true nav:/ tab:none');
    expect(screen.getByLabelText('probe value')).toHaveValue(42);
    // once when the banner opened, once more for the failure, both on the probe's Save button
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(2));
    expect(scrollIntoView.mock.contexts[1]).toBe(screen.getByRole('button', { name: 'probe save' }));
  });

  it('treats a save that rejects as failed', async () => {
    const save = vi.fn<Save>(async () => { throw new Error('boom'); });
    render(<Harness><Probe tabId="probe" initial={3} onSave={save} /></Harness>);
    edit('probe', 42);
    await leaveAndSaveNow();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(banner()).not.toBeNull();
    expect(readout()).toHaveTextContent('dirty:true nav:/ tab:none');
    expect(screen.getByLabelText('probe value')).toHaveValue(42);
  });

  it('keeps a pending tab change armed the same way', async () => {
    const save = vi.fn<Save>(async () => false);
    render(<Harness><Probe tabId="probe" initial={3} onSave={save} /></Harness>);
    edit('probe', 42);
    fireEvent.click(screen.getByRole('button', { name: 'Switch tab' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Save Now' }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(banner()).not.toBeNull();
    expect(readout()).toHaveTextContent('dirty:true nav:none tab:bandwidth');
  });

  it('disables the banner while the save runs, so a double click starts one save', async () => {
    let finish!: (ok: boolean) => void;
    const save = vi.fn<Save>(() => new Promise<boolean>((resolve) => { finish = resolve; }));
    const { container } = render(<Harness><Probe tabId="probe" initial={3} onSave={save} /></Harness>);
    edit('probe', 42);
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    const saveNow = await screen.findByRole('button', { name: 'Save Now' });
    fireEvent.click(saveNow);
    fireEvent.click(saveNow);
    await waitFor(() => expect(saveNow).toBeDisabled());
    expect(screen.getByRole('button', { name: 'Discard' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Dismiss' })).toBeDisabled();
    expect(container.querySelector('.animate-spin')).not.toBeNull();
    expect(save).toHaveBeenCalledTimes(1);
    await act(async () => { finish(true); });
    await waitFor(() => expect(banner()).toBeNull());
    expect(readout()).toHaveTextContent('dirty:false nav:/ tab:none');
  });

  it('the X after a failed Save Now hides the banner, drops the destinations and keeps the edit', async () => {
    const save = vi.fn<Save>(async () => false);
    render(<Harness><Probe tabId="probe" initial={3} onSave={save} /></Harness>);
    edit('probe', 42);
    await leaveAndSaveNow();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    fireEvent.click(screen.getByRole('button', { name: 'Dismiss' }));
    expect(banner()).toBeNull();
    expect(readout()).toHaveTextContent('dirty:true nav:none tab:none');
    expect(screen.getByLabelText('probe value')).toHaveValue(42);
  });

  it('a retry that succeeds hides the banner with the destination still armed', async () => {
    const save = vi.fn<Save>().mockResolvedValueOnce(false).mockResolvedValueOnce(true);
    render(<Harness><Probe tabId="probe" initial={3} onSave={save} /></Harness>);
    edit('probe', 42);
    await leaveAndSaveNow();
    await waitFor(() => expect(save).toHaveBeenCalledTimes(1));
    expect(banner()).not.toBeNull();
    fireEvent.click(screen.getByRole('button', { name: 'Save Now' }));
    await waitFor(() => expect(save).toHaveBeenCalledTimes(2));
    await waitFor(() => expect(banner()).toBeNull());
    expect(readout()).toHaveTextContent('dirty:false nav:/ tab:none');
  });

  it('Discard reverts the panel and hides the banner', async () => {
    render(<Harness><Probe tabId="probe" initial={3} onSave={async () => true} /></Harness>);
    edit('probe', 42);
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard' }));
    expect(screen.getByLabelText('probe value')).toHaveValue(3);
    expect(banner()).toBeNull();
    await waitFor(() => expect(readout()).toHaveTextContent('dirty:false nav:/ tab:none'));
  });
});

// The Services tab mounts two panels (media servers, download clients); both can be dirty at once.
describe('Save Now and Discard act on every dirty panel (audit T5-3)', () => {
  const renderTwo = (saveA: Save, saveB: Save) =>
    render(
      <Harness>
        <Probe tabId="alpha" initial={1} onSave={saveA} />
        <Probe tabId="beta" initial={2} onSave={saveB} />
      </Harness>,
    );

  it('saves both dirty panels and proceeds', async () => {
    const saveA = vi.fn<Save>(async () => true);
    const saveB = vi.fn<Save>(async () => true);
    renderTwo(saveA, saveB);
    edit('alpha', 11);
    edit('beta', 22);
    await leaveAndSaveNow();
    await waitFor(() => expect(saveB).toHaveBeenCalledWith(22));
    expect(saveA).toHaveBeenCalledWith(11);
    await waitFor(() => expect(banner()).toBeNull());
    expect(readout()).toHaveTextContent('dirty:false nav:/ tab:none');
  });

  it('attempts both, keeps the banner and points at the panel that failed', async () => {
    const saveA = vi.fn<Save>(async () => true);
    const saveB = vi.fn<Save>(async () => false);
    renderTwo(saveA, saveB);
    edit('alpha', 11);
    edit('beta', 22);
    await leaveAndSaveNow();
    await waitFor(() => expect(saveB).toHaveBeenCalledTimes(1));
    expect(saveA).toHaveBeenCalledTimes(1);
    expect(banner()).not.toBeNull();
    expect(readout()).toHaveTextContent('dirty:true nav:/ tab:none');
    await waitFor(() => expect(scrollIntoView).toHaveBeenCalledTimes(2));
    expect(scrollIntoView.mock.contexts[1]).toBe(screen.getByRole('button', { name: 'beta save' }));
  });

  it('Discard reverts both dirty panels', async () => {
    renderTwo(async () => true, async () => true);
    edit('alpha', 11);
    edit('beta', 22);
    fireEvent.click(screen.getByRole('button', { name: 'Leave' }));
    fireEvent.click(await screen.findByRole('button', { name: 'Discard' }));
    expect(screen.getByLabelText('alpha value')).toHaveValue(1);
    expect(screen.getByLabelText('beta value')).toHaveValue(2);
    expect(banner()).toBeNull();
    await waitFor(() => expect(readout()).toHaveTextContent('dirty:false nav:/ tab:none'));
  });
});

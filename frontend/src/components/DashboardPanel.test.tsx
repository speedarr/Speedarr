import { useState, type ReactNode } from 'react';
import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DashboardPanel, type DashboardPanelProps } from './DashboardPanel';

const noop = () => {};

// Stand-in for a content component: it owns its title row and places the controls at its end.
const body = (controls: ReactNode) => (
  <div>
    <div className="flex justify-between">
      <h3>Bandwidth Usage</h3>
      {controls}
    </div>
    <p>chart body</p>
  </div>
);

const renderPanel = ({ children = body, ...over }: Partial<DashboardPanelProps> = {}) =>
  render(
    <DashboardPanel
      id="bandwidth-chart"
      title="Bandwidth Usage"
      summary="↓ 120 Mbps · ↑ 40 Mbps now"
      collapsed={false}
      canMoveUp={true}
      canMoveDown={true}
      isDefaultLayout={false}
      onToggleCollapsed={noop}
      onMoveUp={noop}
      onMoveDown={noop}
      onResetLayout={noop}
      {...over}
    >
      {children}
    </DashboardPanel>,
  );

// A panel that owns its collapsed state, as Home does through the layout hook; Reset expands it.
const StatefulPanel = ({ initiallyCollapsed = false }: { initiallyCollapsed?: boolean }) => {
  const [collapsed, setCollapsed] = useState(initiallyCollapsed);
  return (
    <DashboardPanel
      id="bandwidth-chart"
      title="Bandwidth Usage"
      summary="↓ 120 Mbps · ↑ 40 Mbps now"
      collapsed={collapsed}
      canMoveUp={true}
      canMoveDown={true}
      isDefaultLayout={false}
      onToggleCollapsed={() => setCollapsed((c) => !c)}
      onMoveUp={noop}
      onMoveDown={noop}
      onResetLayout={() => setCollapsed(false)}
    >
      {body}
    </DashboardPanel>
  );
};

const openMenu = () =>
  fireEvent.keyDown(screen.getByRole('button', { name: 'Bandwidth Usage options' }), { key: 'Enter' });

describe('DashboardPanel expanded', () => {
  it('renders the content through the render prop and adds no title row of its own', () => {
    const { container } = renderPanel();
    expect(screen.getByText('chart body')).toBeInTheDocument();
    expect(screen.getAllByRole('heading')).toHaveLength(1);
    expect(screen.queryByText('↓ 120 Mbps · ↑ 40 Mbps now')).not.toBeInTheDocument();
    expect(container.querySelector('[data-panel-id="bandwidth-chart"]')).toHaveAttribute('data-collapsed', 'false');
  });

  it("places the chevron and the options menu inside the content's title row", () => {
    renderPanel();
    const row = screen.getByRole('heading', { name: 'Bandwidth Usage' }).parentElement as HTMLElement;
    expect(row).toContainElement(screen.getByRole('button', { name: 'Collapse Bandwidth Usage' }));
    expect(row).toContainElement(screen.getByRole('button', { name: 'Bandwidth Usage options' }));
  });

  it('collapses from the chevron, which is marked expanded', () => {
    const onToggleCollapsed = vi.fn();
    renderPanel({ onToggleCollapsed });
    const chevron = screen.getByRole('button', { name: 'Collapse Bandwidth Usage' });
    expect(chevron).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(chevron);
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });
});

describe('DashboardPanel toggling', () => {
  it('keeps keyboard focus on the chevron across collapse and expand', () => {
    render(<StatefulPanel />);
    fireEvent.click(screen.getByRole('button', { name: 'Collapse Bandwidth Usage' }));
    expect(screen.getByRole('button', { name: 'Expand Bandwidth Usage' })).toHaveFocus();
    fireEvent.click(screen.getByRole('button', { name: 'Expand Bandwidth Usage' }));
    expect(screen.getByRole('button', { name: 'Collapse Bandwidth Usage' })).toHaveFocus();
  });

  it('refocuses the chevron when Reset layout expands a collapsed panel', () => {
    render(<StatefulPanel initiallyCollapsed />);
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reset layout' }));
    expect(screen.getByRole('button', { name: 'Collapse Bandwidth Usage' })).toHaveFocus();
  });
});

describe('DashboardPanel when the content throws', () => {
  it('keeps the title and the controls and explains how to retry', () => {
    const Boom = () => {
      throw new Error('boom');
    };
    const consoleError = vi.spyOn(console, 'error').mockImplementation(() => {});
    try {
      renderPanel({ children: () => <Boom /> });
    } finally {
      consoleError.mockRestore();
    }
    expect(screen.getByRole('heading', { name: 'Bandwidth Usage' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Collapse Bandwidth Usage' })).toBeInTheDocument();
    expect(screen.getByRole('button', { name: 'Bandwidth Usage options' })).toBeInTheDocument();
    expect(screen.getByText(/could not be shown/i)).toBeInTheDocument();
  });
});

describe('DashboardPanel collapsed', () => {
  it('renders its own title and the summary and never calls the render prop', () => {
    const children = vi.fn(body);
    const { container } = renderPanel({ collapsed: true, children });
    expect(children).not.toHaveBeenCalled();
    expect(screen.getByRole('heading', { name: 'Bandwidth Usage' })).toBeInTheDocument();
    expect(screen.getByText('↓ 120 Mbps · ↑ 40 Mbps now')).toBeInTheDocument();
    expect(screen.queryByText('chart body')).not.toBeInTheDocument();
    expect(container.querySelector('[data-panel-id="bandwidth-chart"]')).toHaveAttribute('data-collapsed', 'true');
  });

  it('offers an Expand chevron marked not expanded, and the options menu', () => {
    renderPanel({ collapsed: true });
    expect(screen.getByRole('button', { name: 'Expand Bandwidth Usage' })).toHaveAttribute('aria-expanded', 'false');
    openMenu();
    expect(screen.getByRole('menuitem', { name: 'Move up' })).toBeInTheDocument();
  });
});

describe('DashboardPanel options menu', () => {
  it('lists Move up, Move down and Reset layout', () => {
    renderPanel();
    openMenu();
    expect(screen.getByRole('menuitem', { name: 'Move up' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Move down' })).toBeInTheDocument();
    expect(screen.getByRole('menuitem', { name: 'Reset layout' })).toBeInTheDocument();
  });

  it('calls onMoveUp from Move up', () => {
    const onMoveUp = vi.fn();
    renderPanel({ onMoveUp });
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Move up' }));
    expect(onMoveUp).toHaveBeenCalledTimes(1);
  });

  it('calls onMoveDown from Move down', () => {
    const onMoveDown = vi.fn();
    renderPanel({ onMoveDown });
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Move down' }));
    expect(onMoveDown).toHaveBeenCalledTimes(1);
  });

  it('calls onResetLayout from Reset layout', () => {
    const onResetLayout = vi.fn();
    renderPanel({ onResetLayout });
    openMenu();
    fireEvent.click(screen.getByRole('menuitem', { name: 'Reset layout' }));
    expect(onResetLayout).toHaveBeenCalledTimes(1);
  });

  it('disables Move up at the top of the list and Reset layout on the default layout', () => {
    const onMoveUp = vi.fn();
    const onResetLayout = vi.fn();
    renderPanel({ canMoveUp: false, isDefaultLayout: true, onMoveUp, onResetLayout });
    openMenu();
    const up = screen.getByRole('menuitem', { name: 'Move up' });
    expect(up).toHaveAttribute('aria-disabled', 'true');
    fireEvent.click(up);
    expect(onMoveUp).not.toHaveBeenCalled();
    expect(screen.getByRole('menuitem', { name: 'Reset layout' })).toHaveAttribute('aria-disabled', 'true');
    expect(screen.getByRole('menuitem', { name: 'Move down' })).not.toHaveAttribute('aria-disabled');
  });
});

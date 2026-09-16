import { describe, it, expect, vi } from 'vitest';
import { render, screen, fireEvent } from '@testing-library/react';
import { DashboardPanel, type DashboardPanelProps } from './DashboardPanel';

const noop = () => {};

const renderPanel = (over: Partial<DashboardPanelProps> = {}) =>
  render(
    <DashboardPanel
      id="bandwidth-chart"
      title="Bandwidth Usage"
      summary="↓ 120 Mbps · ↑ 40 Mbps now"
      collapsed={false}
      editing={false}
      canMoveUp={true}
      canMoveDown={true}
      onToggleCollapsed={noop}
      onMoveUp={noop}
      onMoveDown={noop}
      {...over}
    >
      <p>chart body</p>
    </DashboardPanel>,
  );

describe('DashboardPanel expanded', () => {
  it('renders the title and the content, not the summary', () => {
    const { container } = renderPanel();
    expect(screen.getByRole('heading', { name: 'Bandwidth Usage' })).toBeInTheDocument();
    expect(screen.getByText('chart body')).toBeInTheDocument();
    expect(screen.queryByText('↓ 120 Mbps · ↑ 40 Mbps now')).not.toBeInTheDocument();
    expect(container.querySelector('[data-panel-id="bandwidth-chart"]')).toHaveAttribute('data-collapsed', 'false');
  });

  it('offers a Collapse button that is marked expanded and calls onToggleCollapsed', () => {
    const onToggleCollapsed = vi.fn();
    renderPanel({ onToggleCollapsed });
    const button = screen.getByRole('button', { name: 'Collapse Bandwidth Usage' });
    expect(button).toHaveAttribute('aria-expanded', 'true');
    fireEvent.click(button);
    expect(onToggleCollapsed).toHaveBeenCalledTimes(1);
  });

  it('shows no move buttons outside edit mode', () => {
    renderPanel();
    expect(screen.queryByRole('button', { name: 'Move Bandwidth Usage up' })).not.toBeInTheDocument();
    expect(screen.queryByRole('button', { name: 'Move Bandwidth Usage down' })).not.toBeInTheDocument();
  });
});

describe('DashboardPanel collapsed', () => {
  it('renders the summary and not the content', () => {
    const { container } = renderPanel({ collapsed: true });
    expect(screen.getByText('↓ 120 Mbps · ↑ 40 Mbps now')).toBeInTheDocument();
    expect(screen.queryByText('chart body')).not.toBeInTheDocument();
    expect(container.querySelector('[data-panel-id="bandwidth-chart"]')).toHaveAttribute('data-collapsed', 'true');
  });

  it('offers an Expand button marked not expanded', () => {
    renderPanel({ collapsed: true });
    expect(screen.getByRole('button', { name: 'Expand Bandwidth Usage' })).toHaveAttribute('aria-expanded', 'false');
  });
});

describe('DashboardPanel in edit mode', () => {
  it('shows move buttons that call their callbacks', () => {
    const onMoveUp = vi.fn();
    const onMoveDown = vi.fn();
    renderPanel({ editing: true, onMoveUp, onMoveDown });
    fireEvent.click(screen.getByRole('button', { name: 'Move Bandwidth Usage up' }));
    fireEvent.click(screen.getByRole('button', { name: 'Move Bandwidth Usage down' }));
    expect(onMoveUp).toHaveBeenCalledTimes(1);
    expect(onMoveDown).toHaveBeenCalledTimes(1);
  });

  it('disables a move button at the end of the list', () => {
    renderPanel({ editing: true, canMoveUp: false, canMoveDown: true });
    expect(screen.getByRole('button', { name: 'Move Bandwidth Usage up' })).toBeDisabled();
    expect(screen.getByRole('button', { name: 'Move Bandwidth Usage down' })).toBeEnabled();
  });

  it('keeps the collapse control while editing', () => {
    renderPanel({ editing: true });
    expect(screen.getByRole('button', { name: 'Collapse Bandwidth Usage' })).toBeInTheDocument();
  });
});

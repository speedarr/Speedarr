import React from 'react';
import { ArrowDown, ArrowUp, ChevronDown, ChevronUp } from 'lucide-react';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import type { PanelId } from '@/lib/dashboardLayout';

export interface DashboardPanelProps {
  id: PanelId;
  title: string;
  /** One line shown next to the title while collapsed. */
  summary: string;
  collapsed: boolean;
  /** Edit mode: show the move up / move down buttons. */
  editing: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  onToggleCollapsed: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  /** Panel content; mounted only while expanded. */
  children: React.ReactNode;
}

/**
 * Uniform chrome for a dashboard panel (issue #86): one card with a title bar carrying the
 * collapse chevron (always) and move buttons (edit mode), and either the content or a one-line
 * summary. Collapsed content is unmounted so its polling stops.
 */
export const DashboardPanel: React.FC<DashboardPanelProps> = ({
  id,
  title,
  summary,
  collapsed,
  editing,
  canMoveUp,
  canMoveDown,
  onToggleCollapsed,
  onMoveUp,
  onMoveDown,
  children,
}) => (
  <Card data-panel-id={id} data-collapsed={collapsed}>
    <div className="flex items-center justify-between gap-4 px-6 py-4">
      <div className="flex items-baseline gap-3 min-w-0">
        <h3 className="text-lg font-semibold leading-none">{title}</h3>
        {collapsed && <span className="text-sm text-muted-foreground truncate">{summary}</span>}
      </div>
      <div className="flex items-center gap-1 shrink-0">
        {editing && (
          <>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={onMoveUp}
              disabled={!canMoveUp}
              aria-label={`Move ${title} up`}
            >
              <ArrowUp className="h-4 w-4" aria-hidden="true" />
            </Button>
            <Button
              variant="ghost"
              size="icon"
              className="h-8 w-8"
              onClick={onMoveDown}
              disabled={!canMoveDown}
              aria-label={`Move ${title} down`}
            >
              <ArrowDown className="h-4 w-4" aria-hidden="true" />
            </Button>
          </>
        )}
        <Button
          variant="ghost"
          size="icon"
          className="h-8 w-8"
          onClick={onToggleCollapsed}
          aria-expanded={!collapsed}
          aria-label={collapsed ? `Expand ${title}` : `Collapse ${title}`}
        >
          {collapsed ? (
            <ChevronDown className="h-4 w-4" aria-hidden="true" />
          ) : (
            <ChevronUp className="h-4 w-4" aria-hidden="true" />
          )}
        </Button>
      </div>
    </div>
    {!collapsed && (
      <CardContent>
        <ErrorBoundary>{children}</ErrorBoundary>
      </CardContent>
    )}
  </Card>
);

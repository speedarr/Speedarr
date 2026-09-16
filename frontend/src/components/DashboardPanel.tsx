import React from 'react';
import { AlertCircle, ArrowDown, ArrowUp, ChevronDown, ChevronUp, MoreVertical, RotateCcw } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Card, CardContent } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import { ErrorBoundary } from '@/components/ErrorBoundary';
import type { PanelId } from '@/lib/dashboardLayout';

export interface DashboardPanelProps {
  id: PanelId;
  title: string;
  /** One line shown next to the title while collapsed. */
  summary: string;
  collapsed: boolean;
  canMoveUp: boolean;
  canMoveDown: boolean;
  /** Disables "Reset layout" in the options menu. */
  isDefaultLayout: boolean;
  onToggleCollapsed: () => void;
  onMoveUp: () => void;
  onMoveDown: () => void;
  onResetLayout: () => void;
  /**
   * Renders the panel content; called only while expanded. The content owns its title row and
   * places `controls` (the options menu and the collapse chevron) at the end of it, so the shell
   * adds no row of its own.
   */
  children: (controls: React.ReactNode) => React.ReactNode;
}

/**
 * Chrome for a dashboard panel (issue #86): one card whose content keeps its own title row and
 * hosts the controls; collapsed, the card shows the title, a one-line summary and the controls
 * instead, with the content unmounted so its polling stops.
 */
export const DashboardPanel: React.FC<DashboardPanelProps> = ({
  id,
  title,
  summary,
  collapsed,
  canMoveUp,
  canMoveDown,
  isDefaultLayout,
  onToggleCollapsed,
  onMoveUp,
  onMoveDown,
  onResetLayout,
  children,
}) => {
  // The chevron lives in whichever branch is mounted, so it remounts on every toggle and when
  // "Reset layout" expands a collapsed panel; put keyboard focus back on it afterwards.
  const chevronRef = React.useRef<HTMLButtonElement>(null);
  const refocusChevron = React.useRef(false);
  React.useLayoutEffect(() => {
    if (refocusChevron.current) {
      refocusChevron.current = false;
      chevronRef.current?.focus();
    }
  }, [collapsed]);
  const toggleCollapsed = () => {
    refocusChevron.current = true;
    onToggleCollapsed();
  };
  const resetLayout = () => {
    if (collapsed) refocusChevron.current = true;
    onResetLayout();
  };

  const controls = (
    <div className="flex items-center gap-1 shrink-0">
      <DropdownMenu>
        <DropdownMenuTrigger asChild>
          <Button variant="ghost" size="icon" className="h-8 w-8" aria-label={`${title} options`}>
            <MoreVertical className="h-4 w-4" aria-hidden="true" />
          </Button>
        </DropdownMenuTrigger>
        <DropdownMenuContent align="end">
          <DropdownMenuItem onSelect={onMoveUp} disabled={!canMoveUp}>
            <ArrowUp className="h-4 w-4 mr-2" aria-hidden="true" />
            Move up
          </DropdownMenuItem>
          <DropdownMenuItem onSelect={onMoveDown} disabled={!canMoveDown}>
            <ArrowDown className="h-4 w-4 mr-2" aria-hidden="true" />
            Move down
          </DropdownMenuItem>
          <DropdownMenuSeparator />
          <DropdownMenuItem onSelect={resetLayout} disabled={isDefaultLayout}>
            <RotateCcw className="h-4 w-4 mr-2" aria-hidden="true" />
            Reset layout
          </DropdownMenuItem>
        </DropdownMenuContent>
      </DropdownMenu>
      <Button
        ref={chevronRef}
        variant="ghost"
        size="icon"
        className="h-8 w-8"
        onClick={toggleCollapsed}
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
  );

  // A crashed content component must not take the panel's controls with it: keep the title row
  // and say how to retry (collapsing and expanding remounts the content).
  const fallback = (
    <div>
      <div className="flex items-center justify-between gap-4 mb-4">
        <h3 className="text-lg font-semibold">{title}</h3>
        {controls}
      </div>
      <Alert variant="destructive">
        <AlertCircle className="h-4 w-4" />
        <AlertDescription>
          This panel&apos;s content could not be shown. Collapse and expand it to try again.
        </AlertDescription>
      </Alert>
    </div>
  );

  return (
    <Card data-panel-id={id} data-collapsed={collapsed}>
      {collapsed ? (
        <div className="flex items-center justify-between gap-4 px-6 py-4">
          <div className="flex items-baseline gap-3 min-w-0">
            <h3 className="text-lg font-semibold leading-none">{title}</h3>
            <span className="text-sm text-muted-foreground truncate">{summary}</span>
          </div>
          {controls}
        </div>
      ) : (
        <CardContent className="pt-6">
          <ErrorBoundary fallback={fallback}>{children(controls)}</ErrorBoundary>
        </CardContent>
      )}
    </Card>
  );
};

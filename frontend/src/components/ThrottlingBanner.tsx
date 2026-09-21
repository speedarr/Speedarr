import { useState } from 'react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { Button } from '@/components/ui/button';
import { Power } from 'lucide-react';
import type { SystemStatus } from '@/types';

interface ThrottlingBannerProps {
  status: SystemStatus;
  onReenabled: () => void;
}

const formatUntil = (until: string | null | undefined): string => {
  if (!until) return 'until re-enabled';
  const date = new Date(until);
  if (isNaN(date.getTime())) return 'until re-enabled';
  return `until ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
};

export const ThrottlingBanner: React.FC<ThrottlingBannerProps> = ({ status, onReenabled }) => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';
  const [isBusy, setIsBusy] = useState(false);

  if (status.throttling_enabled) return null;

  const handleReenable = async () => {
    setIsBusy(true);
    try {
      await apiClient.resumeMonitoring();
      onReenabled();
    } catch (err) {
      console.error('Error re-enabling throttling:', err);
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <div
      className="rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20 p-3 flex items-center justify-between"
      role="status"
      aria-live="polite"
      aria-label="Speedarr throttling is disabled"
    >
      <span className="text-sm font-medium text-orange-700 dark:text-orange-300 flex items-center gap-2">
        <Power className="h-4 w-4" aria-hidden="true" />
        Throttling disabled {formatUntil(status.throttling_disabled_until)}
        {status.throttling_disabled_by && (
          <span className="text-xs text-muted-foreground">(by {status.throttling_disabled_by})</span>
        )}
      </span>
      {isAdmin && (
        <Button
          variant="ghost"
          size="sm"
          onClick={handleReenable}
          disabled={isBusy}
          className="h-7 px-2 text-orange-700 dark:text-orange-300 hover:text-orange-900 dark:hover:text-orange-100"
        >
          Re-enable now
        </Button>
      )}
    </div>
  );
};

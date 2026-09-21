import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '@/api/client';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Button } from '@/components/ui/button';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, Power } from 'lucide-react';
import type { SystemStatus } from '@/types';

const DURATION_CHOICES = [
  { value: 'indefinite', label: 'Indefinitely' },
  { value: '30', label: 'For 30 minutes' },
  { value: '60', label: 'For 1 hour' },
  { value: '120', label: 'For 2 hours' },
  { value: 'custom', label: 'Custom…' },
];

const formatUntil = (until: string | null | undefined): string => {
  if (!until) return 'until re-enabled';
  const date = new Date(until);
  if (isNaN(date.getTime())) return 'until re-enabled';
  return `until ${date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' })}`;
};

export const ThrottlingControl: React.FC = () => {
  const [status, setStatus] = useState<SystemStatus | null>(null);
  const [duration, setDuration] = useState('indefinite');
  const [customMinutes, setCustomMinutes] = useState('');
  const [validationError, setValidationError] = useState('');
  const [isBusy, setIsBusy] = useState(false);
  const [error, setError] = useState('');

  const fetchStatus = useCallback(async () => {
    try {
      setStatus(await apiClient.getSystemStatus());
      setError('');
    } catch (err) {
      console.error('Error fetching throttling status:', err);
      setError('Failed to load throttling status');
    }
  }, []);

  useEffect(() => {
    fetchStatus();
  }, [fetchStatus]);

  const handleDisable = async () => {
    setValidationError('');
    let minutes: number | null = null;
    if (duration === 'custom') {
      const parsed = parseInt(customMinutes, 10);
      if (isNaN(parsed) || parsed < 1 || parsed > 10080) {
        setValidationError('Enter a duration between 1 and 10080 minutes.');
        return;
      }
      minutes = parsed;
    } else if (duration !== 'indefinite') {
      minutes = parseInt(duration, 10);
    }
    setIsBusy(true);
    try {
      await apiClient.pauseMonitoring(minutes);
      await fetchStatus();
    } catch (err) {
      console.error('Error disabling throttling:', err);
      setError('Failed to disable throttling');
    } finally {
      setIsBusy(false);
    }
  };

  const handleEnable = async () => {
    setIsBusy(true);
    try {
      await apiClient.resumeMonitoring();
      await fetchStatus();
    } catch (err) {
      console.error('Error re-enabling throttling:', err);
      setError('Failed to re-enable throttling');
    } finally {
      setIsBusy(false);
    }
  };

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Power className="h-4 w-4" />
          Throttling Control
        </CardTitle>
        <CardDescription>
          Temporarily disable Speedarr's bandwidth management. Disabling restores all download
          client speeds and stops applying limits; monitoring and the dashboard stay live.
          Changes take effect immediately — no save needed.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-3">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {!status ? (
          <div className="flex items-center gap-2 text-sm text-muted-foreground">
            <Loader2 className="h-4 w-4 animate-spin" />
            Loading status…
          </div>
        ) : status.throttling_enabled ? (
          <>
            <p className="text-sm">
              Throttling is <span className="font-medium">active</span>.
            </p>
            <div className="flex flex-wrap items-end gap-3">
              <div className="space-y-1">
                <Label htmlFor="disable-duration" className="text-xs">Duration</Label>
                <Select value={duration} onValueChange={setDuration} disabled={isBusy}>
                  <SelectTrigger id="disable-duration" className="w-40">
                    <SelectValue />
                  </SelectTrigger>
                  <SelectContent>
                    {DURATION_CHOICES.map((choice) => (
                      <SelectItem key={choice.value} value={choice.value}>
                        {choice.label}
                      </SelectItem>
                    ))}
                  </SelectContent>
                </Select>
              </div>
              {duration === 'custom' && (
                <div className="space-y-1">
                  <Label htmlFor="disable-custom-minutes" className="text-xs">Minutes (1–10080)</Label>
                  <Input
                    id="disable-custom-minutes"
                    type="number"
                    min="1"
                    max="10080"
                    className="w-28"
                    value={customMinutes}
                    onChange={(e) => setCustomMinutes(e.target.value)}
                    disabled={isBusy}
                  />
                </div>
              )}
              <Button variant="destructive" onClick={handleDisable} disabled={isBusy}>
                Disable Throttling
              </Button>
            </div>
            {validationError && (
              <p className="text-sm text-destructive">{validationError}</p>
            )}
          </>
        ) : (
          <div className="flex flex-wrap items-center justify-between gap-3 rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20 p-3">
            <span className="text-sm font-medium text-orange-700 dark:text-orange-300">
              Throttling disabled {formatUntil(status.throttling_disabled_until)}
              {status.throttling_disabled_by && (
                <span className="ml-1 text-xs text-muted-foreground">
                  (by {status.throttling_disabled_by})
                </span>
              )}
            </span>
            <Button onClick={handleEnable} disabled={isBusy}>
              Re-enable Now
            </Button>
          </div>
        )}
      </CardContent>
    </Card>
  );
};

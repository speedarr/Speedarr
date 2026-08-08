import { useCallback, useEffect, useState } from 'react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { Switch } from '@/components/ui/switch';
import { Input } from '@/components/ui/input';
import { Label } from '@/components/ui/label';
import { Button } from '@/components/ui/button';
import {
  DropdownMenu,
  DropdownMenuContent,
  DropdownMenuItem,
  DropdownMenuLabel,
  DropdownMenuSeparator,
  DropdownMenuTrigger,
} from '@/components/ui/dropdown-menu';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';

const DURATION_OPTIONS: { label: string; minutes: number | null }[] = [
  { label: 'Indefinitely', minutes: null },
  { label: 'For 30 minutes', minutes: 30 },
  { label: 'For 1 hour', minutes: 60 },
  { label: 'For 2 hours', minutes: 120 },
];

export const ThrottlingToggle: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [enabled, setEnabled] = useState<boolean | null>(null);
  const [menuOpen, setMenuOpen] = useState(false);
  const [customOpen, setCustomOpen] = useState(false);
  const [customMinutes, setCustomMinutes] = useState('');
  const [isBusy, setIsBusy] = useState(false);

  const fetchState = useCallback(async () => {
    try {
      const status = await apiClient.getSystemStatus();
      setEnabled(status.throttling_enabled);
    } catch (err) {
      console.error('Error fetching throttling state:', err);
    }
  }, []);

  useEffect(() => {
    fetchState();
    const interval = setInterval(fetchState, 5000);
    return () => clearInterval(interval);
  }, [fetchState]);

  const disableFor = async (minutes: number | null) => {
    setIsBusy(true);
    try {
      const response = await apiClient.pauseMonitoring(minutes);
      setEnabled(response.throttling_enabled);
    } catch (err) {
      console.error('Error disabling throttling:', err);
    } finally {
      setIsBusy(false);
      setMenuOpen(false);
      setCustomOpen(false);
    }
  };

  const enable = async () => {
    setIsBusy(true);
    try {
      const response = await apiClient.resumeMonitoring();
      setEnabled(response.throttling_enabled);
    } catch (err) {
      console.error('Error enabling throttling:', err);
    } finally {
      setIsBusy(false);
    }
  };

  const handleCustomConfirm = () => {
    const minutes = parseInt(customMinutes);
    if (isNaN(minutes) || minutes < 1 || minutes > 10080) return;
    disableFor(minutes);
  };

  if (!isAdmin || enabled === null) return null;

  return (
    <>
      <DropdownMenu open={menuOpen} onOpenChange={setMenuOpen}>
        <DropdownMenuTrigger asChild>
          <span
            title={enabled ? 'Throttling active - click to disable' : 'Throttling disabled - click to re-enable'}
            onClick={(e) => {
              // Re-enable directly; the duration menu only opens when disabling.
              if (!enabled) {
                e.preventDefault();
                if (!isBusy) enable();
              }
            }}
          >
            <Switch checked={enabled} disabled={isBusy} aria-label="Speedarr throttling on/off" />
          </span>
        </DropdownMenuTrigger>
        {enabled && (
          <DropdownMenuContent align="end">
            <DropdownMenuLabel>Disable throttling</DropdownMenuLabel>
            <DropdownMenuSeparator />
            {DURATION_OPTIONS.map((option) => (
              <DropdownMenuItem key={option.label} onClick={() => disableFor(option.minutes)}>
                {option.label}
              </DropdownMenuItem>
            ))}
            <DropdownMenuItem onClick={() => setCustomOpen(true)}>Custom…</DropdownMenuItem>
          </DropdownMenuContent>
        )}
      </DropdownMenu>

      <Dialog open={customOpen} onOpenChange={setCustomOpen}>
        <DialogContent className="sm:max-w-sm">
          <DialogHeader>
            <DialogTitle>Disable throttling</DialogTitle>
            <DialogDescription>Duration in minutes (1–10080).</DialogDescription>
          </DialogHeader>
          <div className="space-y-1">
            <Label htmlFor="custom-disable-minutes">Minutes</Label>
            <Input
              id="custom-disable-minutes"
              type="number"
              min="1"
              max="10080"
              value={customMinutes}
              onChange={(e) => setCustomMinutes(e.target.value)}
            />
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setCustomOpen(false)}>Cancel</Button>
            <Button onClick={handleCustomConfirm} disabled={isBusy}>Disable</Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>
    </>
  );
};

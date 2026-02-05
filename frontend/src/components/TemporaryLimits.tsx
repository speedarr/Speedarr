import React, { useState, useEffect, useRef } from 'react';
import { apiClient } from '@/api/client';
import { useAuth } from '@/contexts/AuthContext';
import { getErrorMessage } from '@/lib/utils';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Label } from '@/components/ui/label';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, Clock, X, CheckCircle } from 'lucide-react';

interface TemporaryLimitState {
  active: boolean;
  download_mbps: number | null;
  upload_mbps: number | null;
  expires_at: string | null;
  remaining_minutes: number | null;
}

export const TemporaryLimits: React.FC = () => {
  const { user } = useAuth();
  const isAdmin = user?.role === 'admin';

  const [limits, setLimits] = useState<TemporaryLimitState | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Form state
  const [downloadMbps, setDownloadMbps] = useState<string>('');
  const [uploadMbps, setUploadMbps] = useState<string>('');
  const [durationHours, setDurationHours] = useState<string>('1');

  // Ref to track timeout for cleanup
  const successTimeoutRef = useRef<ReturnType<typeof setTimeout> | null>(null);

  // Clean up timeouts on unmount
  useEffect(() => {
    return () => {
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current);
      }
    };
  }, []);

  const fetchLimits = async () => {
    try {
      const response = await apiClient.getTemporaryLimits();
      setLimits(response);
      setError('');
    } catch (err) {
      console.error('Error fetching temporary limits:', err);
    } finally {
      setIsLoading(false);
    }
  };

  useEffect(() => {
    fetchLimits();
    // Poll every 30 seconds to update remaining time
    const interval = setInterval(fetchLimits, 30000);
    return () => clearInterval(interval);
  }, []);

  const handleSetLimits = async () => {
    setIsSaving(true);
    setError('');
    setSuccess('');

    try {
      const parsedDuration = parseFloat(durationHours);
      const parsedDownload = downloadMbps ? parseFloat(downloadMbps) : null;
      const parsedUpload = uploadMbps ? parseFloat(uploadMbps) : null;

      // Validate numeric values to prevent NaN
      if (isNaN(parsedDuration) || parsedDuration <= 0) {
        setError('Duration must be a positive number');
        setIsSaving(false);
        return;
      }
      if (parsedDownload !== null && (isNaN(parsedDownload) || parsedDownload < 0)) {
        setError('Download limit must be a non-negative number');
        setIsSaving(false);
        return;
      }
      if (parsedUpload !== null && (isNaN(parsedUpload) || parsedUpload < 0)) {
        setError('Upload limit must be a non-negative number');
        setIsSaving(false);
        return;
      }

      const params: {
        download_mbps?: number | null;
        upload_mbps?: number | null;
        duration_hours: number;
      } = {
        duration_hours: parsedDuration,
      };

      if (parsedDownload !== null) {
        params.download_mbps = parsedDownload;
      }
      if (parsedUpload !== null) {
        params.upload_mbps = parsedUpload;
      }

      const response = await apiClient.setTemporaryLimits(params);
      setLimits(response);
      setSuccess('Temporary limits set successfully');
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current);
      }
      successTimeoutRef.current = setTimeout(() => setSuccess(''), 3000);

      // Clear form
      setDownloadMbps('');
      setUploadMbps('');
      setDurationHours('1');
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const handleClearLimits = async () => {
    setIsSaving(true);
    setError('');

    try {
      await apiClient.clearTemporaryLimits();
      setLimits({ active: false, download_mbps: null, upload_mbps: null, expires_at: null, remaining_minutes: null });
      setSuccess('Temporary limits cleared');
      if (successTimeoutRef.current) {
        clearTimeout(successTimeoutRef.current);
      }
      successTimeoutRef.current = setTimeout(() => setSuccess(''), 3000);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const formatRemainingTime = (minutes: number | null): string => {
    if (minutes === null) return '--';
    if (minutes < 1) return 'Less than 1 minute';
    if (minutes < 60) return `${Math.round(minutes)} minute${Math.round(minutes) !== 1 ? 's' : ''}`;
    const hours = Math.floor(minutes / 60);
    const mins = Math.round(minutes % 60);
    if (mins === 0) return `${hours} hour${hours !== 1 ? 's' : ''}`;
    return `${hours}h ${mins}m`;
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex justify-center items-center p-4">
          <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  // Hide component for non-admin users
  if (!isAdmin) {
    return null;
  }

  return (
    <Card>
      <CardHeader className="pb-3">
        <CardTitle className="text-base flex items-center gap-2">
          <Clock className="h-4 w-4" />
          Temporary Limits
        </CardTitle>
      </CardHeader>
      <CardContent className="space-y-4">
        {error && (
          <Alert variant="destructive">
            <AlertDescription>{error}</AlertDescription>
          </Alert>
        )}

        {success && (
          <Alert>
            <CheckCircle className="h-4 w-4" />
            <AlertDescription>{success}</AlertDescription>
          </Alert>
        )}

        {/* Active Limits Display */}
        {limits?.active && (
          <div
            className="rounded-lg border border-orange-200 dark:border-orange-800 bg-orange-50 dark:bg-orange-900/20 p-3 space-y-2"
            role="status"
            aria-live="polite"
            aria-label="Temporary bandwidth limits are currently active"
          >
            <div className="flex items-center justify-between">
              <span className="text-sm font-medium text-orange-700 dark:text-orange-300 flex items-center gap-1">
                <Clock className="h-3 w-3" aria-hidden="true" />
                Temporary Override Active
              </span>
              <Button
                variant="ghost"
                size="sm"
                onClick={handleClearLimits}
                disabled={isSaving}
                className="h-6 px-2 text-orange-700 dark:text-orange-300 hover:text-orange-900 dark:hover:text-orange-100"
                aria-label="Clear temporary bandwidth limits"
              >
                <X className="h-4 w-4 mr-1" aria-hidden="true" />
                Clear
              </Button>
            </div>
            <div className="grid grid-cols-3 gap-2 text-sm">
              <div>
                <span className="text-muted-foreground">Download:</span>
                <span className="ml-1 font-medium">
                  {limits.download_mbps !== null ? `${limits.download_mbps} Mbps` : 'Normal'}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Upload:</span>
                <span className="ml-1 font-medium">
                  {limits.upload_mbps !== null ? `${limits.upload_mbps} Mbps` : 'Normal'}
                </span>
              </div>
              <div>
                <span className="text-muted-foreground">Remaining:</span>
                <span className="ml-1 font-medium">
                  {formatRemainingTime(limits.remaining_minutes)}
                </span>
              </div>
            </div>
          </div>
        )}

        {/* Set New Limits Form */}
        <div className="grid grid-cols-4 gap-3 items-end">
          <div className="space-y-1">
            <Label htmlFor="temp-download" className="text-xs">Download (Mbps)</Label>
            <Input
              id="temp-download"
              type="number"
              min="0"
              step="1"
              placeholder="e.g., 100"
              value={downloadMbps}
              onChange={(e) => setDownloadMbps(e.target.value)}
              disabled={isSaving}
              className="h-8"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="temp-upload" className="text-xs">Upload (Mbps)</Label>
            <Input
              id="temp-upload"
              type="number"
              min="0"
              step="1"
              placeholder="e.g., 50"
              value={uploadMbps}
              onChange={(e) => setUploadMbps(e.target.value)}
              disabled={isSaving}
              className="h-8"
            />
          </div>
          <div className="space-y-1">
            <Label htmlFor="temp-duration" className="text-xs">Duration (Hours)</Label>
            <Input
              id="temp-duration"
              type="number"
              min="0.5"
              step="0.5"
              placeholder="1"
              value={durationHours}
              onChange={(e) => setDurationHours(e.target.value)}
              disabled={isSaving}
              className="h-8"
            />
          </div>
          <Button
            onClick={handleSetLimits}
            disabled={isSaving || (!downloadMbps && !uploadMbps)}
            size="sm"
            className="h-8"
            aria-label="Apply temporary bandwidth limits"
          >
            {isSaving && <Loader2 className="mr-1 h-3 w-3 animate-spin" aria-hidden="true" />}
            Set Limits
          </Button>
        </div>
        <p className="text-xs text-muted-foreground">
          Override normal bandwidth limits temporarily. Leave a field empty to use normal limits for that direction.
        </p>
      </CardContent>
    </Card>
  );
};

import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

interface HistoryConfig {
  retention_days: number;
}

export const HistorySettings: React.FC = () => {
  const [config, setConfig] = useState<HistoryConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<HistoryConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'history',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('history');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('history');
      setConfig(response.config);
      resetOriginal(response.config);
      setError('');
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    if (!config) return;

    // Validate retention period
    if (config.retention_days < 1 || config.retention_days > 90) {
      setError('Retention period must be between 1 and 90 days');
      return;
    }

    setIsSaving(true);
    setError('');
    setSuccess('');

    try {
      await apiClient.updateSettingsSection('history', config);
      resetOriginal(config);
      setSuccess('History settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateRetentionDays = (value: string) => {
    if (!config) return;
    const numValue = parseInt(value);
    if (!isNaN(numValue)) {
      setConfig({ ...config, retention_days: Math.min(90, Math.max(1, numValue)) });
    }
  };

  if (isLoading) {
    return (
      <Card>
        <CardContent className="flex justify-center items-center p-8">
          <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
        </CardContent>
      </Card>
    );
  }

  if (!config) {
    return (
      <Card>
        <CardContent className="p-8">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>Failed to load history configuration</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <div className="space-y-4">
      {error && (
        <Alert variant="destructive">
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>{error}</AlertDescription>
        </Alert>
      )}

      {success && (
        <Alert>
          <CheckCircle className="h-4 w-4" />
          <AlertDescription>{success}</AlertDescription>
        </Alert>
      )}

      {/* Data Retention */}
      <Card>
        <CardHeader>
          <CardTitle>Data Retention</CardTitle>
          <CardDescription>
            Configure how long historical data is kept before automatic cleanup
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="retention-days">Retention Period (days)</Label>
            <Input
              id="retention-days"
              type="number"
              min="1"
              max="90"
              step="1"
              value={config.retention_days}
              onChange={(e) => updateRetentionDays(e.target.value)}
              disabled={isSaving}
            />
            <p className="text-sm text-muted-foreground">
              Data older than this will be automatically cleaned up (1-90 days, default: 30)
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="flex gap-2 pt-4">
        <Button
          ref={saveButtonRef}
          onClick={handleSave}
          disabled={isSaving}
          className={isDirty ? 'ring-2 ring-orange-500 ring-offset-2' : ''}
        >
          {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save Changes
        </Button>
      </div>
    </div>
  );
};

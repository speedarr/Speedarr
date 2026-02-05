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

interface RestorationConfig {
  delays: {
    episode_end: number;
    movie_end: number;
  };
}

export const RestorationSettings: React.FC = () => {
  const [config, setConfig] = useState<RestorationConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<RestorationConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'restoration',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('restoration');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('restoration');
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

    setIsSaving(true);
    setError('');
    setSuccess('');

    try {
      await apiClient.updateSettingsSection('restoration', config);
      resetOriginal(config);
      setSuccess('Holding time settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateDelay = (field: 'episode_end' | 'movie_end', value: number) => {
    if (!config) return;
    setConfig({
      ...config,
      delays: { ...config.delays, [field]: value },
    });
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
            <AlertDescription>Failed to load holding time configuration</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Bandwidth Holding Times</CardTitle>
        <CardDescription>
          Configure how long to hold bandwidth allocation after a stream ends before releasing it back to downloads
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
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

        <Alert>
          <AlertCircle className="h-4 w-4" />
          <AlertDescription>
            When a stream ends, bandwidth is held for the configured duration to allow for the next episode or movie to start.
            If the same user and player start a new stream during the holding period, the hold is cancelled and bandwidth is immediately allocated to the new stream.
          </AlertDescription>
        </Alert>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="episode-delay">Episode End Hold Time (seconds)</Label>
            <Input
              id="episode-delay"
              type="number"
              min="0"
              step="1"
              value={config.delays.episode_end}
              onChange={(e) => updateDelay('episode_end', parseInt(e.target.value))}
              disabled={isSaving}
            />
            <p className="text-sm text-muted-foreground">
              Hold bandwidth after TV episode ends (default: 600 seconds / 10 minutes)
            </p>
            <p className="text-sm text-muted-foreground">
              Allows time for next episode to start without speed fluctuation
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="movie-delay">Movie End Hold Time (seconds)</Label>
            <Input
              id="movie-delay"
              type="number"
              min="0"
              step="1"
              value={config.delays.movie_end}
              onChange={(e) => updateDelay('movie_end', parseInt(e.target.value))}
              disabled={isSaving}
            />
            <p className="text-sm text-muted-foreground">
              Hold bandwidth after movie ends (default: 1800 seconds / 30 minutes)
            </p>
            <p className="text-sm text-muted-foreground">
              Allows time for credits, post-credit scenes, or next movie selection
            </p>
          </div>
        </div>

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
      </CardContent>
    </Card>
  );
};

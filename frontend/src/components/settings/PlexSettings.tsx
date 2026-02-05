import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle, ExternalLink } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { apiClient } from '@/api/client';
import { PasswordInput } from './PasswordInput';
import { TestConnectionButton } from './TestConnectionButton';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';
import { getErrorMessage } from '@/lib/utils';

interface PlexConfig {
  url: string;
  token: string;
  include_lan_streams: boolean;
}

export const PlexSettings: React.FC = () => {
  const [config, setConfig] = useState<PlexConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<PlexConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'services-plex',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('services-plex');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('plex');
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
      await apiClient.updateSettingsSection('plex', config);
      resetOriginal(config);
      setSuccess('Plex settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateConfig = (field: keyof PlexConfig, value: any) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
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
            <AlertDescription>Failed to load Plex configuration</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Plex Configuration</CardTitle>
        <CardDescription>
          Configure connection to your Plex Media Server for stream detection
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

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="plex-url">Server URL</Label>
            <Input
              id="plex-url"
              type="url"
              value={config.url}
              onChange={(e) => updateConfig('url', e.target.value)}
              placeholder="http://192.168.1.100:32400"
              disabled={isSaving}
              maxLength={512}
            />
            <p className="text-sm text-muted-foreground">
              The URL of your Plex Media Server
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="plex-token">X-Plex-Token</Label>
            <PasswordInput
              value={config.token === '***REDACTED***' ? '' : config.token}
              onChange={(e) => updateConfig('token', e.target.value)}
              placeholder={config.token === '***REDACTED***' ? 'Current token is set' : 'Enter X-Plex-Token'}
              disabled={isSaving}
              maxLength={128}
            />
            <p className="text-sm text-muted-foreground flex items-center gap-1">
              Your X-Plex-Token for authentication.{' '}
              <a
                href="https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/"
                target="_blank"
                rel="noopener noreferrer"
                className="text-primary hover:underline inline-flex items-center"
              >
                How to find your token <ExternalLink className="h-3 w-3 ml-1" />
              </a>
            </p>
          </div>

          <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="include-lan">Include LAN Streams in Bandwidth</Label>
              <p className="text-sm text-muted-foreground">
                Count LAN streams in bandwidth calculations. When disabled, only WAN streams affect upload limits.
                The dashboard will still show all streams.
              </p>
            </div>
            <Switch
              id="include-lan"
              checked={config.include_lan_streams || false}
              onCheckedChange={(checked) => updateConfig('include_lan_streams', checked)}
              disabled={isSaving}
            />
          </div>
        </div>

        <div className="flex flex-wrap gap-2 pt-4">
          <Button
            ref={saveButtonRef}
            onClick={handleSave}
            disabled={isSaving}
            className={isDirty ? 'ring-2 ring-orange-500 ring-offset-2' : ''}
          >
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Changes
          </Button>

          <TestConnectionButton
            service="plex"
            config={config}
            disabled={isSaving || !config.url || !config.token}
            useExisting={config.token === '***REDACTED***'}
          />
        </div>
      </CardContent>
    </Card>
  );
};

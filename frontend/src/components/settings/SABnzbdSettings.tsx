import React, { useState, useEffect } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { PasswordInput } from './PasswordInput';
import { TestConnectionButton } from './TestConnectionButton';

interface SABnzbdConfig {
  url: string;
  api_key: string;
  enabled: boolean;
  max_speed_mbps: number;
}

export const SABnzbdSettings: React.FC = () => {
  const [config, setConfig] = useState<SABnzbdConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('sabnzbd');
      setConfig(response.config);
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
      await apiClient.updateSettingsSection('sabnzbd', config);
      setSuccess('SABnzbd settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateConfig = (field: keyof SABnzbdConfig, value: any) => {
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
            <AlertDescription>Failed to load SABnzbd configuration</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>SABnzbd Configuration</CardTitle>
        <CardDescription>
          Configure connection to your SABnzbd download client
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

        <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
          <div className="space-y-0.5">
            <Label htmlFor="sab-enabled">Enable SABnzbd</Label>
            <p className="text-sm text-muted-foreground">
              Enable bandwidth management for SABnzbd
            </p>
          </div>
          <Switch
            id="sab-enabled"
            checked={config.enabled}
            onCheckedChange={(checked) => updateConfig('enabled', checked)}
            disabled={isSaving}
          />
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="sab-url">Server URL</Label>
            <Input
              id="sab-url"
              type="url"
              value={config.url}
              onChange={(e) => updateConfig('url', e.target.value)}
              placeholder="http://sabnzbd.local:8080"
              disabled={isSaving || !config.enabled}
            />
            <p className="text-sm text-muted-foreground">
              The URL of your SABnzbd Web UI
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="sab-api-key">API Key</Label>
            <PasswordInput
              value={config.api_key === '***REDACTED***' ? '' : config.api_key}
              onChange={(e) => updateConfig('api_key', e.target.value)}
              placeholder={config.api_key === '***REDACTED***' ? 'Current API key is set' : 'Enter API key'}
              disabled={isSaving || !config.enabled}
            />
            <p className="text-sm text-muted-foreground">
              Found in SABnzbd Config → General → API Key
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="sab-max-speed">Maximum Speed (Mbps)</Label>
            <Input
              id="sab-max-speed"
              type="number"
              min="1"
              step="0.1"
              value={config.max_speed_mbps}
              onChange={(e) => updateConfig('max_speed_mbps', parseFloat(e.target.value))}
              placeholder="900"
              disabled={isSaving || !config.enabled}
            />
            <p className="text-sm text-muted-foreground">
              {config.max_speed_mbps > 0 && (
                <span className="font-medium text-foreground">{(config.max_speed_mbps / 8).toFixed(1)} MB/s</span>
              )}
              {config.max_speed_mbps > 0 && ' — '}
              Must match SABnzbd's Config → General → Maximum line speed
            </p>
          </div>
        </div>

        <div className="flex gap-2 pt-4">
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Changes
          </Button>

          {config.enabled && (
            <TestConnectionButton
              service="sabnzbd"
              config={config}
              disabled={isSaving || !config.url || !config.api_key}
              useExisting={config.api_key === '***REDACTED***'}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
};

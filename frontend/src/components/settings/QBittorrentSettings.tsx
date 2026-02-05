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

interface QBittorrentConfig {
  url: string;
  username: string;
  password: string;
  enabled: boolean;
}

export const QBittorrentSettings: React.FC = () => {
  const [config, setConfig] = useState<QBittorrentConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('qbittorrent');
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
      await apiClient.updateSettingsSection('qbittorrent', config);
      setSuccess('qBittorrent settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateConfig = (field: keyof QBittorrentConfig, value: any) => {
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
            <AlertDescription>Failed to load qBittorrent configuration</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>qBittorrent Configuration</CardTitle>
        <CardDescription>
          Configure connection to your qBittorrent download client
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
            <Label htmlFor="qb-enabled">Enable qBittorrent</Label>
            <p className="text-sm text-muted-foreground">
              Enable bandwidth management for qBittorrent
            </p>
          </div>
          <Switch
            id="qb-enabled"
            checked={config.enabled}
            onCheckedChange={(checked) => updateConfig('enabled', checked)}
            disabled={isSaving}
          />
        </div>

        <div className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="qb-url">Server URL</Label>
            <Input
              id="qb-url"
              type="url"
              value={config.url}
              onChange={(e) => updateConfig('url', e.target.value)}
              placeholder="http://qbittorrent.local:8080"
              disabled={isSaving || !config.enabled}
            />
            <p className="text-sm text-muted-foreground">
              The URL of your qBittorrent Web UI
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="qb-username">Username</Label>
            <Input
              id="qb-username"
              type="text"
              value={config.username}
              onChange={(e) => updateConfig('username', e.target.value)}
              placeholder="admin"
              disabled={isSaving || !config.enabled}
              autoComplete="username"
            />
          </div>

          <div className="space-y-2">
            <Label htmlFor="qb-password">Password</Label>
            <PasswordInput
              value={config.password === '***REDACTED***' ? '' : config.password}
              onChange={(e) => updateConfig('password', e.target.value)}
              placeholder={config.password === '***REDACTED***' ? 'Current password is set' : 'Enter password'}
              disabled={isSaving || !config.enabled}
              autoComplete="current-password"
            />
          </div>
        </div>

        <div className="flex gap-2 pt-4">
          <Button onClick={handleSave} disabled={isSaving}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Changes
          </Button>

          {config.enabled && (
            <TestConnectionButton
              service="qbittorrent"
              config={config}
              disabled={isSaving || !config.url || !config.username || (!config.password && config.password !== '***REDACTED***')}
              useExisting={config.password === '***REDACTED***'}
            />
          )}
        </div>
      </CardContent>
    </Card>
  );
};

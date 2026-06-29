import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle, Info } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { PasswordInput } from './PasswordInput';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

interface UnraidConfig {
  enabled: boolean;
  url: string;
  api_key: string;
  verify_ssl: boolean;
  poll_interval_seconds: number;
  throttle_on_parity_check: boolean;
  throttle_on_mover: boolean;
  throttle_on_array_degraded: boolean;
  download_limit_mbps: number;
  upload_limit_mbps: number;
}

export const UnraidSettings: React.FC = () => {
  const [config, setConfig] = useState<UnraidConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<UnraidConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  useEffect(() => {
    registerTab(
      'unraid',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('unraid');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => { loadConfig(); }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('unraid');
      setConfig(response.config);
      resetOriginal(response.config);
      setError('');
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    if (!config) return;
    setIsSaving(true); setError(''); setSuccess('');
    try {
      await apiClient.updateSettingsSection('unraid', config);
      resetOriginal(config);
      setSuccess('Unraid settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (err: unknown) {
      setError(getErrorMessage(err));
    } finally {
      setIsSaving(false);
    }
  };

  const updateConfig = (field: keyof UnraidConfig, value: unknown) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  const handleTest = async () => {
    if (!config) return;
    setIsTesting(true); setTestResult(null);
    try {
      const response = await apiClient.testConnection('unraid', config);
      setTestResult({ success: response.success, message: response.message });
      if (response.success) setTimeout(() => setTestResult(null), 5000);
    } catch (err: unknown) {
      setTestResult({ success: false, message: getErrorMessage(err) });
    } finally {
      setIsTesting(false);
    }
  };

  if (isLoading) {
    return (
      <Card><CardContent className="flex justify-center items-center p-8">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </CardContent></Card>
    );
  }
  if (!config) {
    return (
      <Card><CardContent className="p-8">
        <Alert variant="destructive"><AlertCircle className="h-4 w-4" />
          <AlertDescription>Failed to load Unraid configuration</AlertDescription>
        </Alert>
      </CardContent></Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Unraid</CardTitle>
        <CardDescription>
          Throttle downloads while Unraid runs a parity check, the mover, or has a degraded array.
          Requires the Unraid Connect/API plugin and a read-only API key.
        </CardDescription>
      </CardHeader>
      <CardContent className="space-y-6">
        {error && (<Alert variant="destructive"><AlertCircle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>)}
        {success && (<Alert><CheckCircle className="h-4 w-4" /><AlertDescription>{success}</AlertDescription></Alert>)}

        <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
          <div className="space-y-0.5">
            <Label htmlFor="unraid-enabled">Enable Unraid Monitoring</Label>
            <p className="text-sm text-muted-foreground">Poll the Unraid API and throttle on the conditions below</p>
          </div>
          <Switch id="unraid-enabled" checked={config.enabled}
            onCheckedChange={(c) => updateConfig('enabled', c)} disabled={isSaving} />
        </div>

        {config.enabled && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="unraid-url">Unraid URL</Label>
                <Input id="unraid-url" value={config.url}
                  onChange={(e) => updateConfig('url', e.target.value)}
                  placeholder="http://192.168.1.10" disabled={isSaving} maxLength={255} />
                <p className="text-sm text-muted-foreground">Base URL; /graphql is appended automatically</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="unraid-interval">Poll Interval (seconds)</Label>
                <Input id="unraid-interval" type="number" min="10" max="300"
                  value={config.poll_interval_seconds}
                  onChange={(e) => updateConfig('poll_interval_seconds', parseInt(e.target.value, 10))}
                  disabled={isSaving} />
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="unraid-key">API Key</Label>
              <PasswordInput
                value={config.api_key === '***REDACTED***' ? '' : config.api_key}
                onChange={(e) => updateConfig('api_key', e.target.value)}
                placeholder={config.api_key === '***REDACTED***' ? 'Current API key is set' : 'x-api-key from unraid-api'}
                disabled={isSaving} maxLength={255} />
            </div>

            <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
              <div className="space-y-0.5">
                <Label htmlFor="unraid-ssl">Verify TLS certificate</Label>
                <p className="text-sm text-muted-foreground">Leave off for self-signed certs (default)</p>
              </div>
              <Switch id="unraid-ssl" checked={config.verify_ssl}
                onCheckedChange={(c) => updateConfig('verify_ssl', c)} disabled={isSaving} />
            </div>

            <div className="space-y-2">
              <Label>Throttle when…</Label>
              <div className="flex items-center justify-between rounded-lg border p-3">
                <span className="text-sm">Parity check is running</span>
                <Switch checked={config.throttle_on_parity_check}
                  onCheckedChange={(c) => updateConfig('throttle_on_parity_check', c)} disabled={isSaving} />
              </div>
              <div className="flex items-center justify-between rounded-lg border p-3">
                <span className="text-sm">Mover is running</span>
                <Switch checked={config.throttle_on_mover}
                  onCheckedChange={(c) => updateConfig('throttle_on_mover', c)} disabled={isSaving} />
              </div>
              <div className="flex items-center justify-between rounded-lg border p-3">
                <span className="text-sm">Array is degraded / a disk is disabled</span>
                <Switch checked={config.throttle_on_array_degraded}
                  onCheckedChange={(c) => updateConfig('throttle_on_array_degraded', c)} disabled={isSaving} />
              </div>
            </div>

            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="unraid-dl">Download limit (Mbps)</Label>
                <Input id="unraid-dl" type="number" min="0" step="0.1"
                  value={config.download_limit_mbps}
                  onChange={(e) => updateConfig('download_limit_mbps', parseFloat(e.target.value))}
                  disabled={isSaving} />
                <p className="text-sm text-muted-foreground">0 throttles to a minimum trickle (never unlimited)</p>
              </div>
              <div className="space-y-2">
                <Label htmlFor="unraid-ul">Upload limit (Mbps)</Label>
                <Input id="unraid-ul" type="number" min="0" step="0.1"
                  value={config.upload_limit_mbps}
                  onChange={(e) => updateConfig('upload_limit_mbps', parseFloat(e.target.value))}
                  disabled={isSaving} />
                <p className="text-sm text-muted-foreground">0 throttles to a minimum trickle (never unlimited)</p>
              </div>
            </div>

            <div className="flex gap-2 items-center">
              <Button onClick={handleTest} disabled={isTesting || isSaving || !config.url} variant="outline" type="button">
                {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Test Connection
              </Button>
            </div>
            {testResult && (
              <Alert variant={testResult.success ? 'default' : 'destructive'}>
                {testResult.success ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                <AlertDescription>{testResult.message}</AlertDescription>
              </Alert>
            )}

            <Alert>
              <Info className="h-4 w-4" />
              <AlertDescription>
                <strong>Note:</strong> The built-in mover flag is used; the CA Mover Tuning plugin may not report through it.
                If the Unraid API becomes unreachable while throttling, the last-known throttle is held until it recovers
                or you disable this integration.
              </AlertDescription>
            </Alert>
          </>
        )}

        <div className="flex gap-2 pt-4">
          <Button ref={saveButtonRef} onClick={handleSave} disabled={isSaving}
            className={isDirty ? 'ring-2 ring-orange-500 ring-offset-2' : ''}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save Changes
          </Button>
        </div>
      </CardContent>
    </Card>
  );
};

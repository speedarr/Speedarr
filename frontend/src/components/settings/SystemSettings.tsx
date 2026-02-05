import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle, Download } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

interface SystemConfig {
  update_frequency: number;
  log_level: string;
  speedarr_url: string;
}

export const SystemSettings: React.FC = () => {
  const [config, setConfig] = useState<SystemConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isDownloadingLogs, setIsDownloadingLogs] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<SystemConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'general',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('general');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('system');
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
      await apiClient.updateSettingsSection('system', config);
      resetOriginal(config);
      setSuccess('System settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateConfig = (field: keyof SystemConfig, value: any) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  const handleDownloadLogs = async () => {
    setIsDownloadingLogs(true);
    setError('');
    try {
      const response = await apiClient.gatherLogs();
      // Create a blob from the log content and trigger download
      const blob = new Blob([response.logs], { type: 'text/plain' });
      const url = window.URL.createObjectURL(blob);
      const a = document.createElement('a');
      a.href = url;
      a.download = `speedarr-logs-${new Date().toISOString().split('T')[0]}.txt`;
      document.body.appendChild(a);
      a.click();
      window.URL.revokeObjectURL(url);
      document.body.removeChild(a);
      setSuccess('Logs downloaded successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsDownloadingLogs(false);
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
            <AlertDescription>Failed to load system configuration</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>System Configuration</CardTitle>
        <CardDescription>
          Core system settings and behavior
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
            <Label htmlFor="update-frequency">Polling Interval (seconds)</Label>
            <Input
              id="update-frequency"
              type="number"
              min="5"
              max="300"
              value={config.update_frequency}
              onChange={(e) => updateConfig('update_frequency', parseInt(e.target.value))}
              placeholder="5"
              disabled={isSaving}
            />
            <p className="text-sm text-muted-foreground">
              How often to poll Plex, download clients, and SNMP (5-300 seconds, default: 5)
            </p>
          </div>

          <div className="space-y-2">
            <Label htmlFor="log-level">Log Level</Label>
            <Select
              value={config.log_level}
              onValueChange={(value) => updateConfig('log_level', value)}
              disabled={isSaving}
            >
              <SelectTrigger id="log-level">
                <SelectValue placeholder="Select log level" />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="DEBUG">Debug</SelectItem>
                <SelectItem value="INFO">Info</SelectItem>
                <SelectItem value="WARNING">Warning</SelectItem>
                <SelectItem value="ERROR">Error</SelectItem>
                <SelectItem value="CRITICAL">Critical</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">
              Logging verbosity level (default: INFO)
            </p>
          </div>

          <div className="space-y-2 pt-4 border-t">
            <Label>Logs</Label>
            <div className="flex items-center gap-4">
              <Button
                variant="outline"
                onClick={handleDownloadLogs}
                disabled={isDownloadingLogs}
              >
                {isDownloadingLogs ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Download className="mr-2 h-4 w-4" />
                )}
                Download Logs
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              Download application logs with sensitive data (passwords, API keys) redacted
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

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle, Download, Info, ExternalLink, RefreshCw, Bug, Lightbulb } from 'lucide-react';
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
import type { VersionCheckResponse } from '@/types';

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
  const [versionInfo, setVersionInfo] = useState<VersionCheckResponse | null>(null);
  const [isCheckingVersion, setIsCheckingVersion] = useState(false);

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

  const versionDisplay = __APP_VERSION__ === 'develop'
    ? `develop (${__APP_COMMIT__})`
    : __APP_VERSION__;

  const checkForUpdates = useCallback(async (forceRefresh = false) => {
    setIsCheckingVersion(true);
    try {
      const result = await apiClient.checkVersion(forceRefresh);
      setVersionInfo(result);
    } catch {
      setVersionInfo(null);
    } finally {
      setIsCheckingVersion(false);
    }
  }, []);

  useEffect(() => {
    checkForUpdates();
  }, [checkForUpdates]);

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
    <>
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

      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <Info className="h-5 w-5" />
            About
          </CardTitle>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
            <span className="text-muted-foreground">Version</span>
            <span>{versionDisplay}</span>
            <span className="text-muted-foreground">Commit</span>
            <span className="font-mono">{__APP_COMMIT__}</span>
            <span className="text-muted-foreground">Branch</span>
            <span>{__APP_BRANCH__}</span>
            <span className="text-muted-foreground">Updates</span>
            <span className="flex items-center gap-2">
              {isCheckingVersion ? (
                <Loader2 className="h-3.5 w-3.5 animate-spin text-muted-foreground" />
              ) : versionInfo?.update_available ? (
                <span className="text-orange-500">
                  {versionInfo.latest_commit ? (
                    <>
                      Newer build available{' '}
                      {versionInfo.release_url ? (
                        <a
                          href={versionInfo.release_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline hover:text-orange-400 font-mono"
                        >
                          {versionInfo.latest_commit}
                        </a>
                      ) : (
                        <span className="font-mono">{versionInfo.latest_commit}</span>
                      )}
                    </>
                  ) : (
                    <>
                      Update available{' '}
                      {versionInfo.release_url ? (
                        <a
                          href={versionInfo.release_url}
                          target="_blank"
                          rel="noopener noreferrer"
                          className="underline hover:text-orange-400"
                        >
                          v{versionInfo.latest_version}
                        </a>
                      ) : (
                        <>v{versionInfo.latest_version}</>
                      )}
                    </>
                  )}
                </span>
              ) : versionInfo?.error ? (
                <span className="text-muted-foreground">{versionInfo.error}</span>
              ) : versionInfo ? (
                <span className="text-green-500">Up to date</span>
              ) : (
                <span className="text-muted-foreground">Could not check</span>
              )}
              <button
                onClick={() => checkForUpdates(true)}
                disabled={isCheckingVersion}
                className="text-muted-foreground hover:text-foreground transition-colors"
                title="Check for updates"
              >
                <RefreshCw className={`h-3.5 w-3.5 ${isCheckingVersion ? 'animate-spin' : ''}`} />
              </button>
            </span>
          </div>

          <div className="border-t pt-4 space-y-3">
            <div className="grid grid-cols-[auto_1fr] gap-x-4 gap-y-2 text-sm">
              <span className="text-muted-foreground">GitHub</span>
              <a
                href="https://github.com/speedarr/Speedarr"
                target="_blank"
                rel="noopener noreferrer"
                className="inline-flex items-center gap-1 text-blue-500 hover:text-blue-400 hover:underline"
              >
                speedarr/Speedarr
                <ExternalLink className="h-3 w-3" />
              </a>
            </div>
            <div className="flex gap-2">
              <a
                href="https://github.com/speedarr/Speedarr/issues/new?template=bug_report.md"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button variant="outline" size="sm">
                  <Bug className="mr-1.5 h-3.5 w-3.5" />
                  Report a Bug
                </Button>
              </a>
              <a
                href="https://github.com/speedarr/Speedarr/issues/new?template=feature_request.md"
                target="_blank"
                rel="noopener noreferrer"
              >
                <Button variant="outline" size="sm">
                  <Lightbulb className="mr-1.5 h-3.5 w-3.5" />
                  Request a Feature
                </Button>
              </a>
            </div>
          </div>
        </CardContent>
      </Card>
    </>
  );
};

/**
 * PlexStep - Configure Plex Media Server connection
 */

import React, { useState, useEffect, useMemo } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, CheckCircle, XCircle, ExternalLink, AlertTriangle } from 'lucide-react';
import { PasswordInput } from '@/components/settings/PasswordInput';
import { apiClient } from '@/api/client';
import { WizardStepProps, PlexConfig } from '../types';

// Validate URL format
const isValidUrl = (url: string): boolean => {
  if (!url) return false;
  try {
    new URL(url);
    return true;
  } catch {
    return false;
  }
};

export const PlexStep: React.FC<WizardStepProps> = ({
  data,
  onDataChange,
  showValidation,
  isLoading,
  readOnly,
}) => {
  const [config, setConfig] = useState<PlexConfig>(() => data || {
    url: '',
    token: '',
  });

  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);

  // Check if URL is valid (for showing Open Settings link and warning)
  const urlIsValid = useMemo(() => isValidUrl(config.url), [config.url]);
  const showUrlWarning = config.url && !urlIsValid;

  // Update parent when config changes
  useEffect(() => {
    onDataChange(config);
  }, [config, onDataChange]);

  const updateConfig = (field: keyof PlexConfig, value: any) => {
    setConfig(prev => ({ ...prev, [field]: value }));
    // Clear test result when config changes
    setTestResult(null);
  };

  const handleTest = async () => {
    setIsTesting(true);
    setTestResult(null);

    try {
      const response = await apiClient.testConnection('plex', config, false);
      setTestResult({
        success: response.success,
        message: response.message,
      });
    } catch (error: any) {
      setTestResult({
        success: false,
        message: error.response?.data?.detail || 'Connection test failed',
      });
    } finally {
      setIsTesting(false);
    }
  };

  if (readOnly) {
    return (
      <div className="space-y-4">
        <h3 className="font-medium">Plex Configuration</h3>
        <div className="grid gap-2 text-sm">
          <div className="flex justify-between py-2 border-b">
            <span className="text-muted-foreground">Server URL</span>
            <span>{config.url || 'Not set'}</span>
          </div>
          <div className="flex justify-between py-2 border-b">
            <span className="text-muted-foreground">Token</span>
            <span>{config.token ? '********' : 'Not set'}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-xl font-semibold">Connect to Plex</h2>
        <p className="text-sm text-muted-foreground">
          Plex provides stream information directly to Speedarr for bandwidth management.
        </p>
      </div>

      <div className="space-y-4">
        <div className="space-y-2">
          <Label htmlFor="plex-url">Server URL</Label>
          <Input
            id="plex-url"
            type="url"
            value={config.url}
            onChange={(e) => updateConfig('url', e.target.value)}
            placeholder="http://192.168.1.100:32400"
            disabled={isLoading}
            className={`${showValidation && !config.url ? 'border-destructive' : ''} ${showUrlWarning ? 'border-yellow-500' : ''}`}
            maxLength={512}
          />
          <p className="text-xs text-muted-foreground">
            The URL of your Plex Media Server (e.g., http://192.168.1.100:32400)
          </p>
          {showUrlWarning && (
            <p className="text-xs text-yellow-600 dark:text-yellow-400 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              Invalid URL format - please include protocol (http:// or https://)
            </p>
          )}
        </div>

        <div className="space-y-2">
          <Label htmlFor="plex-token">X-Plex-Token</Label>
          <PasswordInput
            value={config.token}
            onChange={(e) => updateConfig('token', e.target.value)}
            placeholder="Enter your Plex token"
            disabled={isLoading}
            className={showValidation && !config.token ? 'border-destructive' : ''}
            maxLength={128}
          />
          <p className="text-xs text-muted-foreground flex items-center gap-1">
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

        {/* Test Connection */}
        <div className="pt-4">
          <Button
            type="button"
            variant="outline"
            onClick={handleTest}
            disabled={isLoading || isTesting || !config.url || !config.token}
            className="w-full sm:w-auto"
          >
            {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Test Connection
          </Button>

          {testResult && (
            <Alert
              variant={testResult.success ? 'default' : 'destructive'}
              className={`mt-3 ${testResult.success ? 'border-green-500 text-green-600 dark:text-green-400 [&>svg]:text-green-600 dark:[&>svg]:text-green-400' : ''}`}
            >
              {testResult.success ? (
                <CheckCircle className="h-4 w-4" />
              ) : (
                <XCircle className="h-4 w-4" />
              )}
              <AlertDescription className={testResult.success ? 'text-green-600 dark:text-green-400' : ''}>
                {testResult.message}
              </AlertDescription>
            </Alert>
          )}
        </div>
      </div>
    </div>
  );
};

import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { SplitSlider } from '@/components/ui/split-slider';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

interface FailsafeConfig {
  plex_timeout: number;
  shutdown_download_speed: number | null;
  shutdown_upload_speed: number | null;
}

interface DownloadClient {
  id: string;
  type: string;
  name: string;
  enabled: boolean;
  color: string;
  supports_upload: boolean;
}

interface BandwidthLimits {
  download_total: number;
  upload_total: number;
}

export const FailsafeSettings: React.FC = () => {
  const [config, setConfig] = useState<FailsafeConfig | null>(null);
  const [clients, setClients] = useState<DownloadClient[]>([]);
  const [bandwidthLimits, setBandwidthLimits] = useState<BandwidthLimits>({ download_total: 100, upload_total: 20 });
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [downloadSplit, setDownloadSplit] = useState(50);
  const [uploadSplit, setUploadSplit] = useState(50);
  const [downloadClientPercents, setDownloadClientPercents] = useState<Record<string, number>>({});
  const [uploadClientPercents, setUploadClientPercents] = useState<Record<string, number>>({});

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<FailsafeConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'failsafe',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('failsafe');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadData();
  }, []);

  const loadData = async () => {
    try {
      const [failsafeResponse, clientsResponse, bandwidthResponse] = await Promise.all([
        apiClient.getSettingsSection('failsafe'),
        apiClient.getDownloadClients(),
        apiClient.getSettingsSection('bandwidth'),
      ]);
      setConfig(failsafeResponse.config);
      resetOriginal(failsafeResponse.config);
      setClients(clientsResponse.clients || []);
      // Extract bandwidth limits for calculating 10% defaults
      const bwConfig = bandwidthResponse.config;
      setBandwidthLimits({
        download_total: bwConfig?.download?.total_limit || 100,
        upload_total: bwConfig?.upload?.total_limit || 20,
      });
      setError('');
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  // Calculate 10% of bandwidth limit (default failsafe value)
  const getDefaultDownloadSpeed = () => Math.round(bandwidthLimits.download_total * 0.1 * 10) / 10;
  const getDefaultUploadSpeed = () => Math.round(bandwidthLimits.upload_total * 0.1 * 10) / 10;

  const handleSave = async () => {
    if (!config) return;

    setIsSaving(true);
    setError('');
    setSuccess('');

    try {
      await apiClient.updateSettingsSection('failsafe', config);
      resetOriginal(config);
      setSuccess('Failsafe settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateConfig = (field: keyof FailsafeConfig, value: any) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  const enabledClients = clients.filter(c => c.enabled);
  const downloadClients = enabledClients;
  const uploadClients = enabledClients.filter(c => c.supports_upload);
  const hasTwoDownloadClients = downloadClients.length === 2;
  const hasTwoUploadClients = uploadClients.length === 2;
  const hasThreeOrMoreDownloadClients = downloadClients.length >= 3;
  const hasThreeOrMoreUploadClients = uploadClients.length >= 3;

  // Get first two clients for the split sliders
  const firstDownloadClient = downloadClients[0];
  const secondDownloadClient = downloadClients[1];
  const firstUploadClient = uploadClients[0];
  const secondUploadClient = uploadClients[1];

  // Default equal split percentage
  const defaultDownloadPercent = downloadClients.length > 0 ? Math.round(100 / downloadClients.length) : 50;
  const defaultUploadPercent = uploadClients.length > 0 ? Math.round(100 / uploadClients.length) : 50;

  // Get client percentage for 3+ clients mode
  const getDownloadClientPercent = (clientType: string): number => {
    const value = downloadClientPercents[clientType];
    return value !== undefined ? value : defaultDownloadPercent;
  };

  const getUploadClientPercent = (clientType: string): number => {
    const value = uploadClientPercents[clientType];
    return value !== undefined ? value : defaultUploadPercent;
  };

  // Update client percentage for 3+ clients mode
  const updateDownloadClientPercent = (clientType: string, value: number) => {
    setDownloadClientPercents(prev => ({ ...prev, [clientType]: value }));
  };

  const updateUploadClientPercent = (clientType: string, value: number) => {
    setUploadClientPercents(prev => ({ ...prev, [clientType]: value }));
  };

  // Calculate total percentages for validation
  const downloadTotal = downloadClients.reduce((sum, c) => sum + getDownloadClientPercent(c.type), 0);
  const uploadTotal = uploadClients.reduce((sum, c) => sum + getUploadClientPercent(c.type), 0);

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
            <AlertDescription>Failed to load failsafe configuration</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>Failsafe Configuration</CardTitle>
        <CardDescription>
          Configure safety timeouts and shutdown behavior
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
            <Label htmlFor="plex-timeout">Plex Timeout (seconds)</Label>
            <Input
              id="plex-timeout"
              type="number"
              min="30"
              step="1"
              value={config.plex_timeout}
              onChange={(e) => updateConfig('plex_timeout', parseInt(e.target.value))}
              disabled={isSaving}
              className="w-24"
            />
            <p className="text-sm text-muted-foreground">
              Assume no active streams after this many seconds without Plex response
            </p>
          </div>
        </div>

        <div className="rounded-lg border p-4 space-y-6">
          <div>
            <Label className="text-base">Shutdown Behavior</Label>
            <p className="text-sm text-muted-foreground">
              Configure download client speeds when Speedarr shuts down
            </p>
          </div>

          {/* Download Speed on Shutdown */}
          <div className="space-y-4">
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="shutdown-download-enabled">Download Speed on Shutdown</Label>
                <p className="text-sm text-muted-foreground">
                  Set download clients to a specific speed when shutting down
                </p>
              </div>
              <Switch
                id="shutdown-download-enabled"
                checked={config.shutdown_download_speed !== null}
                onCheckedChange={(checked) => updateConfig('shutdown_download_speed', checked ? getDefaultDownloadSpeed() : null)}
                disabled={isSaving}
              />
            </div>

            {config.shutdown_download_speed !== null && (
              <div className="space-y-4 pl-4 border-l-2 border-muted">
                <div className="space-y-2">
                  <Label>Total Download Speed</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      min="0"
                      step="0.1"
                      className="w-24"
                      value={config.shutdown_download_speed}
                      onChange={(e) => updateConfig('shutdown_download_speed', parseFloat(e.target.value))}
                      disabled={isSaving}
                    />
                    <span className="text-sm text-muted-foreground">Mbps</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Default: 10% of bandwidth limit ({getDefaultDownloadSpeed()} Mbps)
                  </p>
                </div>

                {/* 2 clients: Split Slider */}
                {hasTwoDownloadClients && firstDownloadClient && secondDownloadClient && (
                  <div className="space-y-2">
                    <Label>Client Split</Label>
                    <SplitSlider
                      value={downloadSplit}
                      onChange={setDownloadSplit}
                      leftLabel={firstDownloadClient.name}
                      rightLabel={secondDownloadClient.name}
                      leftColor={firstDownloadClient.color}
                      rightColor={secondDownloadClient.color}
                      disabled={isSaving}
                    />
                    <p className="text-sm text-muted-foreground">
                      {firstDownloadClient.name}: {((config.shutdown_download_speed * downloadSplit) / 100).toFixed(1)} Mbps |{' '}
                      {secondDownloadClient.name}: {((config.shutdown_download_speed * (100 - downloadSplit)) / 100).toFixed(1)} Mbps
                    </p>
                  </div>
                )}

                {/* 3+ clients: Percentage Inputs */}
                {hasThreeOrMoreDownloadClients && config.shutdown_download_speed !== null && (
                  <div className="space-y-3">
                    <Label>Client Split</Label>
                    <p className="text-xs text-muted-foreground">
                      Set percentage for each client (should total 100%)
                    </p>
                    <div className="grid gap-2">
                      {downloadClients.map((client) => {
                        const percent = getDownloadClientPercent(client.type);
                        const mbps = ((config.shutdown_download_speed! * percent) / 100).toFixed(1);
                        return (
                          <div key={client.id} className="flex items-center gap-3">
                            <div
                              className="w-3 h-3 rounded-full flex-shrink-0"
                              style={{ backgroundColor: client.color }}
                            />
                            <span className="w-28 text-sm">{client.name}</span>
                            <Input
                              type="number"
                              min="0"
                              max="100"
                              className="w-20"
                              value={percent}
                              onChange={(e) => updateDownloadClientPercent(client.type, parseInt(e.target.value) || 0)}
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">%</span>
                            <span className="text-sm text-muted-foreground">= {mbps} Mbps</span>
                          </div>
                        );
                      })}
                    </div>
                    {downloadTotal !== 100 && (
                      <p className="text-sm text-amber-500">
                        Total: {downloadTotal}% (should be 100%)
                      </p>
                    )}
                  </div>
                )}

                {/* 1 client: Show badge */}
                {downloadClients.length === 1 && (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Applies to:</p>
                    <div className="flex flex-wrap gap-2">
                      {downloadClients.map(client => (
                        <div
                          key={client.id}
                          className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-sm"
                        >
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: client.color }}
                          />
                          {client.name}
                        </div>
                      ))}
                    </div>
                  </div>
                )}
              </div>
            )}
          </div>

          {/* Upload Speed on Shutdown */}
          <div className="space-y-4 pt-4 border-t">
            <div className="flex items-center justify-between">
              <div>
                <Label htmlFor="shutdown-upload-enabled">Upload Speed on Shutdown</Label>
                <p className="text-sm text-muted-foreground">
                  Set torrent clients to a specific upload speed when shutting down
                </p>
              </div>
              <Switch
                id="shutdown-upload-enabled"
                checked={config.shutdown_upload_speed !== null}
                onCheckedChange={(checked) => updateConfig('shutdown_upload_speed', checked ? getDefaultUploadSpeed() : null)}
                disabled={isSaving}
              />
            </div>

            {config.shutdown_upload_speed !== null && (
              <div className="space-y-4 pl-4 border-l-2 border-muted">
                <div className="space-y-2">
                  <Label>Total Upload Speed</Label>
                  <div className="flex items-center gap-2">
                    <Input
                      type="number"
                      min="0"
                      step="0.1"
                      className="w-24"
                      value={config.shutdown_upload_speed}
                      onChange={(e) => updateConfig('shutdown_upload_speed', parseFloat(e.target.value))}
                      disabled={isSaving}
                    />
                    <span className="text-sm text-muted-foreground">Mbps</span>
                  </div>
                  <p className="text-xs text-muted-foreground">
                    Default: 10% of bandwidth limit ({getDefaultUploadSpeed()} Mbps)
                  </p>
                </div>

                {/* 2 clients: Split Slider */}
                {hasTwoUploadClients && firstUploadClient && secondUploadClient && (
                  <div className="space-y-2">
                    <Label>Client Split</Label>
                    <SplitSlider
                      value={uploadSplit}
                      onChange={setUploadSplit}
                      leftLabel={firstUploadClient.name}
                      rightLabel={secondUploadClient.name}
                      leftColor={firstUploadClient.color}
                      rightColor={secondUploadClient.color}
                      disabled={isSaving}
                    />
                    <p className="text-sm text-muted-foreground">
                      {firstUploadClient.name}: {((config.shutdown_upload_speed * uploadSplit) / 100).toFixed(1)} Mbps |{' '}
                      {secondUploadClient.name}: {((config.shutdown_upload_speed * (100 - uploadSplit)) / 100).toFixed(1)} Mbps
                    </p>
                  </div>
                )}

                {/* 3+ clients: Percentage Inputs */}
                {hasThreeOrMoreUploadClients && config.shutdown_upload_speed !== null && (
                  <div className="space-y-3">
                    <Label>Client Split</Label>
                    <p className="text-xs text-muted-foreground">
                      Set percentage for each client (should total 100%)
                    </p>
                    <div className="grid gap-2">
                      {uploadClients.map((client) => {
                        const percent = getUploadClientPercent(client.type);
                        const mbps = ((config.shutdown_upload_speed! * percent) / 100).toFixed(1);
                        return (
                          <div key={client.id} className="flex items-center gap-3">
                            <div
                              className="w-3 h-3 rounded-full flex-shrink-0"
                              style={{ backgroundColor: client.color }}
                            />
                            <span className="w-28 text-sm">{client.name}</span>
                            <Input
                              type="number"
                              min="0"
                              max="100"
                              className="w-20"
                              value={percent}
                              onChange={(e) => updateUploadClientPercent(client.type, parseInt(e.target.value) || 0)}
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">%</span>
                            <span className="text-sm text-muted-foreground">= {mbps} Mbps</span>
                          </div>
                        );
                      })}
                    </div>
                    {uploadTotal !== 100 && (
                      <p className="text-sm text-amber-500">
                        Total: {uploadTotal}% (should be 100%)
                      </p>
                    )}
                  </div>
                )}

                {/* 1 client: Show badge */}
                {uploadClients.length === 1 && (
                  <div className="space-y-2">
                    <p className="text-sm text-muted-foreground">Applies to:</p>
                    <div className="flex flex-wrap gap-2">
                      {uploadClients.map(client => (
                        <div
                          key={client.id}
                          className="flex items-center gap-1.5 px-2 py-1 rounded-md bg-muted text-sm"
                        >
                          <div
                            className="w-2 h-2 rounded-full"
                            style={{ backgroundColor: client.color }}
                          />
                          {client.name}
                        </div>
                      ))}
                    </div>
                  </div>
                )}

                {uploadClients.length === 0 && (
                  <Alert>
                    <AlertCircle className="h-4 w-4" />
                    <AlertDescription>
                      No torrent clients configured. Upload speed settings apply to torrent clients only.
                    </AlertDescription>
                  </Alert>
                )}
              </div>
            )}
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

import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle, ChevronDown, ChevronUp, Clock } from 'lucide-react';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Switch } from '@/components/ui/switch';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { SplitSlider } from '@/components/ui/split-slider';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

// Convert "HH:mm" local time to UTC "HH:mm"
const localTimeToUtc = (localTime: string): string => {
  const [hours, minutes] = localTime.split(':').map(Number);
  const date = new Date();
  date.setHours(hours, minutes, 0, 0);
  return `${String(date.getUTCHours()).padStart(2, '0')}:${String(date.getUTCMinutes()).padStart(2, '0')}`;
};

// Convert "HH:mm" UTC time to local "HH:mm"
const utcTimeToLocal = (utcTime: string): string => {
  const [hours, minutes] = utcTime.split(':').map(Number);
  const date = new Date();
  date.setUTCHours(hours, minutes, 0, 0);
  return `${String(date.getHours()).padStart(2, '0')}:${String(date.getMinutes()).padStart(2, '0')}`;
};

interface DownloadClient {
  id: string;
  type: string;
  name: string;
  enabled: boolean;
  color: string;
  supports_upload: boolean;
}

interface TimeBasedSchedule {
  enabled: boolean;
  start_time: string;
  end_time: string;
  total_limit: number;
  client_percents: Record<string, number>;
}

interface BandwidthConfig {
  download: {
    total_limit: number;
    inactive_safety_net_percent: number;
    client_percents: Record<string, number>;
    scheduled?: TimeBasedSchedule;
  };
  upload: {
    total_limit: number;
    upload_client_percents: Record<string, number>;
    scheduled?: TimeBasedSchedule;
  };
  streams: {
    bandwidth_calculation: string;
    manual_per_stream: number;
    overhead_percent: number;
  };
}

export const BandwidthSettings: React.FC = () => {
  const [config, setConfig] = useState<BandwidthConfig | null>(null);
  const [clients, setClients] = useState<DownloadClient[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [downloadScheduleOpen, setDownloadScheduleOpen] = useState(false);
  const [uploadScheduleOpen, setUploadScheduleOpen] = useState(false);

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<BandwidthConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'bandwidth',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('bandwidth');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadData();
  }, []);

  const defaultSchedule: TimeBasedSchedule = {
    enabled: false,
    start_time: '22:00',
    end_time: '06:00',
    total_limit: 0,
    client_percents: {},
  };

  const loadData = async () => {
    try {
      const [bandwidthResponse, clientsResponse] = await Promise.all([
        apiClient.getSettingsSection('bandwidth'),
        apiClient.getDownloadClients(),
      ]);
      // Ensure dict fields are initialized
      const loadedConfig = bandwidthResponse.config;
      if (!loadedConfig.download.client_percents) {
        loadedConfig.download.client_percents = {};
      }
      if (!loadedConfig.upload.upload_client_percents) {
        loadedConfig.upload.upload_client_percents = {};
      }
      // Initialize scheduled configs if not present
      if (!loadedConfig.download.scheduled) {
        loadedConfig.download.scheduled = { ...defaultSchedule };
      } else {
        // Convert stored UTC times to local for display
        loadedConfig.download.scheduled.start_time = utcTimeToLocal(loadedConfig.download.scheduled.start_time);
        loadedConfig.download.scheduled.end_time = utcTimeToLocal(loadedConfig.download.scheduled.end_time);
      }
      if (!loadedConfig.upload.scheduled) {
        loadedConfig.upload.scheduled = { ...defaultSchedule };
      } else {
        // Convert stored UTC times to local for display
        loadedConfig.upload.scheduled.start_time = utcTimeToLocal(loadedConfig.upload.scheduled.start_time);
        loadedConfig.upload.scheduled.end_time = utcTimeToLocal(loadedConfig.upload.scheduled.end_time);
      }
      setConfig(loadedConfig);
      resetOriginal(loadedConfig);
      setClients(clientsResponse.clients || []);
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
      // Deep clone and convert schedule times from local to UTC for storage
      const saveConfig: BandwidthConfig = JSON.parse(JSON.stringify(config));
      if (saveConfig.download.scheduled) {
        saveConfig.download.scheduled.start_time = localTimeToUtc(saveConfig.download.scheduled.start_time);
        saveConfig.download.scheduled.end_time = localTimeToUtc(saveConfig.download.scheduled.end_time);
      }
      if (saveConfig.upload.scheduled) {
        saveConfig.upload.scheduled.start_time = localTimeToUtc(saveConfig.upload.scheduled.start_time);
        saveConfig.upload.scheduled.end_time = localTimeToUtc(saveConfig.upload.scheduled.end_time);
      }

      await apiClient.updateSettingsSection('bandwidth', saveConfig);
      resetOriginal(config);

      // Auto-update failsafe to 10% of bandwidth limits (only if failsafe is enabled)
      try {
        const failsafeResponse = await apiClient.getSettingsSection('failsafe');
        const currentFailsafe = failsafeResponse.config;
        const newDownloadFailsafe = Math.round(config.download.total_limit * 0.10 * 10) / 10;
        const newUploadFailsafe = Math.round(config.upload.total_limit * 0.10 * 10) / 10;

        // Only update failsafe speeds if they are currently enabled (not null)
        const downloadEnabled = currentFailsafe.shutdown_download_speed !== null;
        const uploadEnabled = currentFailsafe.shutdown_upload_speed !== null;

        if (downloadEnabled || uploadEnabled) {
          await apiClient.updateSettingsSection('failsafe', {
            ...currentFailsafe,
            shutdown_download_speed: downloadEnabled ? newDownloadFailsafe : null,
            shutdown_upload_speed: uploadEnabled ? newUploadFailsafe : null,
          });

          const updatedParts = [];
          if (downloadEnabled) updatedParts.push(`download: ${newDownloadFailsafe} Mbps`);
          if (uploadEnabled) updatedParts.push(`upload: ${newUploadFailsafe} Mbps`);
          setSuccess(`Bandwidth settings saved. Failsafe speeds updated to 10% (${updatedParts.join(', ')}).`);
        } else {
          setSuccess('Bandwidth settings saved successfully');
        }
      } catch (failsafeErr) {
        // Don't fail the whole save if failsafe update fails
        console.error('Failed to auto-update failsafe:', failsafeErr);
        setSuccess('Bandwidth settings saved successfully');
      }

      setTimeout(() => setSuccess(''), 5000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateDownloadConfig = useCallback((field: string, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev;
      return { ...prev, download: { ...prev.download, [field]: value } };
    });
  }, []);

  const updateUploadConfig = useCallback((field: string, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev;
      return { ...prev, upload: { ...prev.upload, [field]: value } };
    });
  }, []);

  const updateStreamsConfig = useCallback((field: string, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev;
      return { ...prev, streams: { ...prev.streams, [field]: value } };
    });
  }, []);

  const updateDownloadSchedule = useCallback((field: string, value: unknown) => {
    setConfig(prev => {
      if (!prev?.download.scheduled) return prev;
      return {
        ...prev,
        download: {
          ...prev.download,
          scheduled: { ...prev.download.scheduled, [field]: value },
        },
      };
    });
  }, []);

  const updateUploadSchedule = useCallback((field: string, value: unknown) => {
    setConfig(prev => {
      if (!prev?.upload.scheduled) return prev;
      return {
        ...prev,
        upload: {
          ...prev.upload,
          scheduled: { ...prev.upload.scheduled, [field]: value },
        },
      };
    });
  }, []);

  const updateDownloadSchedulePercent = useCallback((clientType: string, value: number) => {
    setConfig(prev => {
      if (!prev?.download.scheduled) return prev;
      const newPercents = { ...prev.download.scheduled.client_percents, [clientType]: value };
      return {
        ...prev,
        download: {
          ...prev.download,
          scheduled: { ...prev.download.scheduled, client_percents: newPercents },
        },
      };
    });
  }, []);

  // Update scheduled download percentage for slider mode (2 clients)
  const updateDownloadSchedulePercentSlider = useCallback((clientType: string, value: number, otherClientType: string) => {
    const otherValue = Math.max(0, 100 - value);
    setConfig(prev => {
      if (!prev?.download.scheduled) return prev;
      return {
        ...prev,
        download: {
          ...prev.download,
          scheduled: {
            ...prev.download.scheduled,
            client_percents: {
              [clientType]: value,
              [otherClientType]: otherValue,
            },
          },
        },
      };
    });
  }, []);

  const updateUploadSchedulePercent = useCallback((clientType: string, value: number) => {
    setConfig(prev => {
      if (!prev?.upload.scheduled) return prev;
      const newPercents = { ...prev.upload.scheduled.client_percents, [clientType]: value };
      return {
        ...prev,
        upload: {
          ...prev.upload,
          scheduled: { ...prev.upload.scheduled, client_percents: newPercents },
        },
      };
    });
  }, []);

  // Update scheduled upload percentage for slider mode (2 clients)
  const updateUploadSchedulePercentSlider = useCallback((clientType: string, value: number, otherClientType: string) => {
    const otherValue = Math.max(0, 100 - value);
    setConfig(prev => {
      if (!prev?.upload.scheduled) return prev;
      return {
        ...prev,
        upload: {
          ...prev.upload,
          scheduled: {
            ...prev.upload.scheduled,
            client_percents: {
              [clientType]: value,
              [otherClientType]: otherValue,
            },
          },
        },
      };
    });
  }, []);

  // Get scheduled percent for a client type
  // Normalizes stored percentages to account for enabled/disabled client changes
  const getDownloadScheduledPercent = (clientType: string): number => {
    const storedPercents = config?.download.scheduled?.client_percents || {};

    // Calculate total of stored percentages for enabled clients only
    const enabledTotal = enabledClients.reduce((sum, c) => {
      return sum + (storedPercents[c.type] ?? 0);
    }, 0);

    const value = storedPercents[clientType];
    if (value !== undefined && enabledTotal > 0) {
      return Math.round((value / enabledTotal) * 100);
    }
    return defaultPercent;
  };

  const getUploadScheduledPercent = (clientType: string): number => {
    const storedPercents = config?.upload.scheduled?.client_percents || {};
    const defaultUploadPercent = enabledUploadClients.length > 0 ? Math.round(100 / enabledUploadClients.length) : 0;

    // Calculate total of stored percentages for enabled upload clients only
    const enabledTotal = enabledUploadClients.reduce((sum, c) => {
      return sum + (storedPercents[c.type] ?? 0);
    }, 0);

    const value = storedPercents[clientType];
    if (value !== undefined && enabledTotal > 0) {
      return Math.round((value / enabledTotal) * 100);
    }
    return defaultUploadPercent;
  };

  const enabledClients = clients.filter(c => c.enabled);
  const hasMultipleClients = enabledClients.length >= 2;
  const hasThreeOrMoreClients = enabledClients.length >= 3;

  // Upload clients (clients that support upload, e.g., torrent clients)
  const enabledUploadClients = enabledClients.filter(c => c.supports_upload);
  const hasMultipleUploadClients = enabledUploadClients.length >= 2;
  const hasThreeOrMoreUploadClients = enabledUploadClients.length >= 3;

  // Default equal split percentage
  const defaultPercent = enabledClients.length > 0 ? Math.round(100 / enabledClients.length) : 50;

  // Get client allocation percentage (used when multiple clients are downloading)
  // Normalizes stored percentages to account for enabled/disabled client changes
  const getClientPercent = (clientType: string): number => {
    const storedPercents = config?.download.client_percents || {};

    // Calculate total of stored percentages for enabled clients only
    const enabledTotal = enabledClients.reduce((sum, c) => {
      return sum + (storedPercents[c.type] ?? 0);
    }, 0);

    const value = storedPercents[clientType];
    if (value !== undefined && enabledTotal > 0) {
      // Normalize: stored value / total of enabled * 100
      return Math.round((value / enabledTotal) * 100);
    }
    return defaultPercent;
  };

  // Update client percentage for slider mode (2 clients)
  const updateClientPercentSlider = (clientType: string, value: number) => {
    if (!config || enabledClients.length !== 2) return;
    const otherClient = enabledClients.find(c => c.type !== clientType);
    if (!otherClient) return;
    const otherValue = Math.max(0, 100 - value);

    setConfig({
      ...config,
      download: {
        ...config.download,
        client_percents: {
          [clientType]: value,
          [otherClient.type]: otherValue,
        },
      },
    });
  };

  // Update client percentage for input mode (3+ clients)
  const updateClientPercent = (clientType: string, value: number) => {
    if (!config) return;
    const newPercents = { ...config.download.client_percents, [clientType]: value };
    setConfig({
      ...config,
      download: { ...config.download, client_percents: newPercents },
    });
  };

  // Calculate total percentage
  const clientTotal = enabledClients.reduce((sum, c) => sum + getClientPercent(c.type), 0);

  // Get upload percentage for a client type
  // Normalizes stored percentages to account for enabled/disabled client changes
  const getUploadPercent = (clientType: string): number => {
    const storedPercents = config?.upload.upload_client_percents || {};

    // Calculate total of stored percentages for enabled upload clients only
    const enabledTotal = enabledUploadClients.reduce((sum, c) => {
      return sum + (storedPercents[c.type] ?? 0);
    }, 0);

    const value = storedPercents[clientType];
    if (value !== undefined && enabledTotal > 0) {
      // Normalize: stored value / total of enabled * 100
      return Math.round((value / enabledTotal) * 100);
    }
    // Default equal split for unlisted clients
    return enabledUploadClients.length > 0 ? Math.round(100 / enabledUploadClients.length) : 0;
  };

  // Update upload percentage for a client (slider mode - 2 clients)
  const updateUploadPercentSlider = (clientType: string, value: number) => {
    if (!config || enabledUploadClients.length !== 2) return;
    const otherClient = enabledUploadClients.find(c => c.type !== clientType);
    if (!otherClient) return;
    const otherValue = Math.max(0, 100 - value);

    setConfig({
      ...config,
      upload: {
        ...config.upload,
        upload_client_percents: {
          ...config.upload.upload_client_percents,
          [clientType]: value,
          [otherClient.type]: otherValue,
        },
      },
    });
  };

  // Update upload percentage for a client (input mode - 3+ clients)
  const updateUploadClientPercent = (clientType: string, value: number) => {
    if (!config) return;
    const newPercents = { ...config.upload.upload_client_percents, [clientType]: value };
    setConfig({
      ...config,
      upload: { ...config.upload, upload_client_percents: newPercents },
    });
  };

  // Calculate upload total percentage
  const uploadTotal = enabledUploadClients.reduce((sum, c) => sum + getUploadPercent(c.type), 0);

  if (isLoading) {
    return (
      <div className="space-y-4">
        <Card>
          <CardContent className="flex justify-center items-center p-8">
            <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
          </CardContent>
        </Card>
      </div>
    );
  }

  if (!config) {
    return (
      <Card>
        <CardContent className="p-8">
          <Alert variant="destructive">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription>Failed to load bandwidth configuration</AlertDescription>
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

      {/* Download Bandwidth */}
      <Card>
        <CardHeader>
          <CardTitle>Download Bandwidth</CardTitle>
          <CardDescription>
            Configure download limits and allocation between clients
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-6">
          <div className="space-y-2">
            <Label htmlFor="download-total-limit">Total Download Limit (Mbps)</Label>
            <Input
              id="download-total-limit"
              type="number"
              min="1"
              step="0.1"
              value={config.download.total_limit}
              onChange={(e) => {
                const value = parseFloat(e.target.value);
                if (!isNaN(value)) {
                  updateDownloadConfig('total_limit', value);
                }
              }}
              disabled={isSaving}
            />
            <p className="text-sm text-muted-foreground">
              Total available download bandwidth in Mbps
            </p>
          </div>

          {/* Client Allocation - 2 clients: Split Slider */}
          {hasMultipleClients && !hasThreeOrMoreClients && (
            <div className="space-y-4 pt-4 border-t">
              <div>
                <Label className="text-base font-medium">Active Downloads Allocation</Label>
                <p className="text-sm text-muted-foreground">
                  How to split bandwidth when multiple clients are actively downloading.
                  When idle, bandwidth is split equally.
                </p>
              </div>

              <SplitSlider
                value={getClientPercent(enabledClients[0].type)}
                onChange={(value) => updateClientPercentSlider(enabledClients[0].type, value)}
                leftLabel={enabledClients[0].name}
                rightLabel={enabledClients[1].name}
                leftColor={enabledClients[0].color}
                rightColor={enabledClients[1].color}
                disabled={isSaving}
              />
              <div className="flex justify-between text-sm text-muted-foreground">
                <span>{(config.download.total_limit * getClientPercent(enabledClients[0].type) / 100).toFixed(1)} Mbps</span>
                <span>{(config.download.total_limit * getClientPercent(enabledClients[1].type) / 100).toFixed(1)} Mbps</span>
              </div>

              {/* Safety Net */}
              <div className="space-y-2 pt-4 border-t">
                <Label htmlFor="safety-net">Inactive Safety Net %</Label>
                <Input
                  id="safety-net"
                  type="number"
                  min="0"
                  max="20"
                  value={config.download.inactive_safety_net_percent}
                  onChange={(e) => updateDownloadConfig('inactive_safety_net_percent', parseFloat(e.target.value))}
                  disabled={isSaving}
                  className="w-24"
                />
                <p className="text-sm text-muted-foreground">
                  Minimum % for inactive client (allows activity detection)
                </p>
              </div>
            </div>
          )}

          {/* Client Allocation - 3+ clients: Percentage Inputs */}
          {hasThreeOrMoreClients && (
            <div className="space-y-4 pt-4 border-t">
              <div>
                <Label className="text-base font-medium">Active Downloads Allocation</Label>
                <p className="text-sm text-muted-foreground">
                  How to split bandwidth when multiple clients are actively downloading (should total 100%).
                  When idle, bandwidth is split equally.
                </p>
              </div>

              <div className="grid gap-3">
                {enabledClients.map((client) => {
                  const percent = getClientPercent(client.type);
                  const mbps = (config.download.total_limit * percent / 100).toFixed(1);
                  return (
                    <div key={client.id} className="flex items-center gap-3">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: client.color }}
                      />
                      <span className="w-32 text-sm font-medium">{client.name}</span>
                      <Input
                        type="number"
                        min="0"
                        max="100"
                        className="w-20"
                        value={percent}
                        onChange={(e) => {
                          const value = parseInt(e.target.value) || 0;
                          updateClientPercent(client.type, value);
                        }}
                        disabled={isSaving}
                      />
                      <span className="text-sm text-muted-foreground">%</span>
                      <span className="text-sm text-muted-foreground">= {mbps} Mbps</span>
                    </div>
                  );
                })}
              </div>

              {clientTotal !== 100 && (
                <p className="text-sm text-amber-500">
                  Total: {clientTotal}% (should be 100%)
                </p>
              )}

              {/* Safety Net */}
              <div className="space-y-2 pt-4 border-t">
                <Label htmlFor="safety-net">Inactive Safety Net %</Label>
                <Input
                  id="safety-net"
                  type="number"
                  min="0"
                  max="20"
                  value={config.download.inactive_safety_net_percent}
                  onChange={(e) => updateDownloadConfig('inactive_safety_net_percent', parseFloat(e.target.value))}
                  disabled={isSaving}
                  className="w-24"
                />
                <p className="text-sm text-muted-foreground">
                  Minimum % for inactive clients (allows activity detection)
                </p>
              </div>
            </div>
          )}

        </CardContent>
      </Card>

      {/* Scheduled Download Settings */}
      <Card>
        <Collapsible open={downloadScheduleOpen} onOpenChange={setDownloadScheduleOpen}>
          <CardHeader className="py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <div className="flex flex-col">
                  <CardTitle className="text-lg leading-none">Scheduled Download Settings</CardTitle>
                  <CardDescription className="leading-tight">Use different download limits during specific hours</CardDescription>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <Switch
                  checked={config.download.scheduled?.enabled || false}
                  onCheckedChange={(checked) => updateDownloadSchedule('enabled', checked)}
                  disabled={isSaving}
                />
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="sm">
                    {downloadScheduleOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </Button>
                </CollapsibleTrigger>
              </div>
            </div>
          </CardHeader>
          <CollapsibleContent>
            <CardContent className="space-y-4 pt-0">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="dl-schedule-start">Start Time</Label>
                  <Input
                    id="dl-schedule-start"
                    type="time"
                    value={config.download.scheduled?.start_time || '22:00'}
                    onChange={(e) => updateDownloadSchedule('start_time', e.target.value)}
                    disabled={isSaving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="dl-schedule-end">End Time</Label>
                  <Input
                    id="dl-schedule-end"
                    type="time"
                    value={config.download.scheduled?.end_time || '06:00'}
                    onChange={(e) => updateDownloadSchedule('end_time', e.target.value)}
                    disabled={isSaving}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="dl-schedule-limit">Total Download Limit During Schedule (Mbps)</Label>
                <Input
                  id="dl-schedule-limit"
                  type="number"
                  min="1"
                  step="0.1"
                  value={config.download.scheduled?.total_limit || 0}
                  onChange={(e) => updateDownloadSchedule('total_limit', parseFloat(e.target.value) || 0)}
                  disabled={isSaving}
                />
              </div>
              {/* 2 clients: SplitSlider */}
              {hasMultipleClients && !hasThreeOrMoreClients && (
                <div className="space-y-3">
                  <Label className="text-sm font-medium">Client Allocation During Schedule</Label>
                  <SplitSlider
                    value={getDownloadScheduledPercent(enabledClients[0].type)}
                    onChange={(value) => updateDownloadSchedulePercentSlider(enabledClients[0].type, value, enabledClients[1].type)}
                    leftLabel={enabledClients[0].name}
                    rightLabel={enabledClients[1].name}
                    leftColor={enabledClients[0].color}
                    rightColor={enabledClients[1].color}
                    disabled={isSaving}
                  />
                  <div className="flex justify-between text-sm text-muted-foreground">
                    <span>{((config.download.scheduled?.total_limit || 0) * getDownloadScheduledPercent(enabledClients[0].type) / 100).toFixed(1)} Mbps</span>
                    <span>{((config.download.scheduled?.total_limit || 0) * getDownloadScheduledPercent(enabledClients[1].type) / 100).toFixed(1)} Mbps</span>
                  </div>
                </div>
              )}

              {/* 3+ clients: Input fields */}
              {hasThreeOrMoreClients && (
                <div className="space-y-3">
                  <Label className="text-sm font-medium">Client Allocation During Schedule</Label>
                  {enabledClients.map((client) => {
                    const percent = getDownloadScheduledPercent(client.type);
                    const scheduledLimit = config.download.scheduled?.total_limit || 0;
                    const mbps = (scheduledLimit * percent / 100).toFixed(1);
                    return (
                      <div key={client.id} className="flex items-center gap-3">
                        <div
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: client.color }}
                        />
                        <span className="w-32 text-sm">{client.name}</span>
                        <Input
                          type="number"
                          min="0"
                          max="100"
                          className="w-20"
                          value={percent}
                          onChange={(e) => updateDownloadSchedulePercent(client.type, parseInt(e.target.value) || 0)}
                          disabled={isSaving}
                        />
                        <span className="text-sm text-muted-foreground">%</span>
                        <span className="text-sm text-muted-foreground">= {mbps} Mbps</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>

      {/* Upload Bandwidth */}
      <Card>
        <CardHeader>
          <CardTitle>Upload Bandwidth</CardTitle>
          <CardDescription>
            Configure upload limits{hasMultipleUploadClients && ' and allocation between clients'}
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="upload-total-limit">Total Upload Limit (Mbps)</Label>
            <Input
              id="upload-total-limit"
              type="number"
              min="1"
              step="0.1"
              value={config.upload.total_limit}
              onChange={(e) => {
                const value = parseFloat(e.target.value);
                if (!isNaN(value)) {
                  updateUploadConfig('total_limit', value);
                }
              }}
              disabled={isSaving}
            />
            <p className="text-sm text-muted-foreground">
              Total available upload bandwidth in Mbps
            </p>
          </div>

          {/* Upload Allocation - 2 clients: Split Slider */}
          {hasMultipleUploadClients && !hasThreeOrMoreUploadClients && (
            <div className="space-y-4 pt-4 border-t">
              <div>
                <Label className="text-base font-medium">Upload Allocation</Label>
                <p className="text-sm text-muted-foreground">
                  How to split upload bandwidth between clients
                </p>
              </div>

              <SplitSlider
                value={getUploadPercent(enabledUploadClients[0].type)}
                onChange={(value) => updateUploadPercentSlider(enabledUploadClients[0].type, value)}
                leftLabel={enabledUploadClients[0].name}
                rightLabel={enabledUploadClients[1].name}
                leftColor={enabledUploadClients[0].color}
                rightColor={enabledUploadClients[1].color}
                disabled={isSaving}
              />
              <div className="flex justify-between text-sm text-muted-foreground">
                <span>{(config.upload.total_limit * getUploadPercent(enabledUploadClients[0].type) / 100).toFixed(1)} Mbps</span>
                <span>{(config.upload.total_limit * getUploadPercent(enabledUploadClients[1].type) / 100).toFixed(1)} Mbps</span>
              </div>
            </div>
          )}

          {/* Upload Allocation - 3+ clients: Percentage Inputs */}
          {hasThreeOrMoreUploadClients && (
            <div className="space-y-4 pt-4 border-t">
              <div>
                <Label className="text-base font-medium">Upload Allocation</Label>
                <p className="text-sm text-muted-foreground">
                  How to split upload bandwidth between clients (should total 100%)
                </p>
              </div>

              <div className="grid gap-3">
                {enabledUploadClients.map((client) => {
                  const percent = getUploadPercent(client.type);
                  const mbps = (config.upload.total_limit * percent / 100).toFixed(1);
                  return (
                    <div key={client.id} className="flex items-center gap-3">
                      <div
                        className="w-3 h-3 rounded-full flex-shrink-0"
                        style={{ backgroundColor: client.color }}
                      />
                      <span className="w-32 text-sm font-medium">{client.name}</span>
                      <Input
                        type="number"
                        min="0"
                        max="100"
                        className="w-20"
                        value={percent}
                        onChange={(e) => {
                          const value = parseInt(e.target.value) || 0;
                          updateUploadClientPercent(client.type, value);
                        }}
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

        </CardContent>
      </Card>

      {/* Scheduled Upload Settings */}
      <Card>
        <Collapsible open={uploadScheduleOpen} onOpenChange={setUploadScheduleOpen}>
          <CardHeader className="py-3">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-3">
                <Clock className="h-4 w-4 text-muted-foreground" />
                <div className="flex flex-col">
                  <CardTitle className="text-lg leading-none">Scheduled Upload Settings</CardTitle>
                  <CardDescription className="leading-tight">Use different upload limits during specific hours</CardDescription>
                </div>
              </div>
              <div className="flex items-center gap-4">
                <Switch
                  checked={config.upload.scheduled?.enabled || false}
                  onCheckedChange={(checked) => updateUploadSchedule('enabled', checked)}
                  disabled={isSaving}
                />
                <CollapsibleTrigger asChild>
                  <Button variant="ghost" size="sm">
                    {uploadScheduleOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                  </Button>
                </CollapsibleTrigger>
              </div>
            </div>
          </CardHeader>
          <CollapsibleContent>
            <CardContent className="space-y-4 pt-0">
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="ul-schedule-start">Start Time</Label>
                  <Input
                    id="ul-schedule-start"
                    type="time"
                    value={config.upload.scheduled?.start_time || '22:00'}
                    onChange={(e) => updateUploadSchedule('start_time', e.target.value)}
                    disabled={isSaving}
                  />
                </div>
                <div className="space-y-2">
                  <Label htmlFor="ul-schedule-end">End Time</Label>
                  <Input
                    id="ul-schedule-end"
                    type="time"
                    value={config.upload.scheduled?.end_time || '06:00'}
                    onChange={(e) => updateUploadSchedule('end_time', e.target.value)}
                    disabled={isSaving}
                  />
                </div>
              </div>
              <div className="space-y-2">
                <Label htmlFor="ul-schedule-limit">Total Upload Limit During Schedule (Mbps)</Label>
                <Input
                  id="ul-schedule-limit"
                  type="number"
                  min="1"
                  step="0.1"
                  value={config.upload.scheduled?.total_limit || 0}
                  onChange={(e) => updateUploadSchedule('total_limit', parseFloat(e.target.value) || 0)}
                  disabled={isSaving}
                />
              </div>
              {/* 2 clients: SplitSlider */}
              {hasMultipleUploadClients && !hasThreeOrMoreUploadClients && (
                <div className="space-y-3">
                  <Label className="text-sm font-medium">Client Allocation During Schedule</Label>
                  <SplitSlider
                    value={getUploadScheduledPercent(enabledUploadClients[0].type)}
                    onChange={(value) => updateUploadSchedulePercentSlider(enabledUploadClients[0].type, value, enabledUploadClients[1].type)}
                    leftLabel={enabledUploadClients[0].name}
                    rightLabel={enabledUploadClients[1].name}
                    leftColor={enabledUploadClients[0].color}
                    rightColor={enabledUploadClients[1].color}
                    disabled={isSaving}
                  />
                  <div className="flex justify-between text-sm text-muted-foreground">
                    <span>{((config.upload.scheduled?.total_limit || 0) * getUploadScheduledPercent(enabledUploadClients[0].type) / 100).toFixed(1)} Mbps</span>
                    <span>{((config.upload.scheduled?.total_limit || 0) * getUploadScheduledPercent(enabledUploadClients[1].type) / 100).toFixed(1)} Mbps</span>
                  </div>
                </div>
              )}

              {/* 3+ clients: Input fields */}
              {hasThreeOrMoreUploadClients && (
                <div className="space-y-3">
                  <Label className="text-sm font-medium">Client Allocation During Schedule</Label>
                  {enabledUploadClients.map((client) => {
                    const percent = getUploadScheduledPercent(client.type);
                    const scheduledLimit = config.upload.scheduled?.total_limit || 0;
                    const mbps = (scheduledLimit * percent / 100).toFixed(1);
                    return (
                      <div key={client.id} className="flex items-center gap-3">
                        <div
                          className="w-3 h-3 rounded-full flex-shrink-0"
                          style={{ backgroundColor: client.color }}
                        />
                        <span className="w-32 text-sm">{client.name}</span>
                        <Input
                          type="number"
                          min="0"
                          max="100"
                          className="w-20"
                          value={percent}
                          onChange={(e) => updateUploadSchedulePercent(client.type, parseInt(e.target.value) || 0)}
                          disabled={isSaving}
                        />
                        <span className="text-sm text-muted-foreground">%</span>
                        <span className="text-sm text-muted-foreground">= {mbps} Mbps</span>
                      </div>
                    );
                  })}
                </div>
              )}
            </CardContent>
          </CollapsibleContent>
        </Collapsible>
      </Card>

      {/* Stream Bandwidth */}
      <Card>
        <CardHeader>
          <CardTitle>Stream Bandwidth Calculation</CardTitle>
          <CardDescription>
            Configure how stream bandwidth is calculated
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <Label htmlFor="bandwidth-calculation">Calculation Method</Label>
            <Select
              value={config.streams.bandwidth_calculation}
              onValueChange={(value) => updateStreamsConfig('bandwidth_calculation', value)}
              disabled={isSaving}
            >
              <SelectTrigger id="bandwidth-calculation">
                <SelectValue />
              </SelectTrigger>
              <SelectContent>
                <SelectItem value="auto">Auto (from Plex)</SelectItem>
                <SelectItem value="manual">Manual (fixed per stream)</SelectItem>
              </SelectContent>
            </Select>
            <p className="text-sm text-muted-foreground">
              Auto reads from Plex, Manual uses fixed value
            </p>
          </div>

          {config.streams.bandwidth_calculation === 'manual' && (
            <div className="space-y-2">
              <Label htmlFor="manual-per-stream">Bandwidth Per Stream (Mbps)</Label>
              <Input
                id="manual-per-stream"
                type="number"
                min="1"
                step="0.1"
                value={config.streams.manual_per_stream}
                onChange={(e) => updateStreamsConfig('manual_per_stream', parseFloat(e.target.value))}
                disabled={isSaving}
              />
              <p className="text-sm text-muted-foreground">
                Fixed bandwidth allocation per active stream
              </p>
            </div>
          )}

          <div className="space-y-2">
            <Label htmlFor="overhead-percent">Protocol Overhead %</Label>
            <Input
              id="overhead-percent"
              type="number"
              min="0"
              max="300"
              value={config.streams.overhead_percent}
              onChange={(e) => updateStreamsConfig('overhead_percent', parseFloat(e.target.value))}
              disabled={isSaving}
              className="w-24"
            />
            <p className="text-sm text-muted-foreground">
              Extra bandwidth to account for protocol overhead.
              {' '}Example: An 8 Mbps stream with {config.streams.overhead_percent}% overhead = {(8 * (1 + config.streams.overhead_percent / 100)).toFixed(1)} Mbps reserved.
            </p>
          </div>
        </CardContent>
      </Card>

      <div className="flex gap-2">
        <Button
          ref={saveButtonRef}
          onClick={handleSave}
          disabled={isSaving}
          className={isDirty ? 'ring-2 ring-orange-500 ring-offset-2' : ''}
        >
          {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
          Save All Bandwidth Settings
        </Button>
      </div>
    </div>
  );
};

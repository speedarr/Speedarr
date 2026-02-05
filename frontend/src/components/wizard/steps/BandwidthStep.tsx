/**
 * BandwidthStep - Configure basic bandwidth limits and client splits
 */

import React, { useState, useEffect, useMemo } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { SplitSlider } from '@/components/ui/split-slider';
import { WizardStepProps, BandwidthConfig, DownloadClientConfig } from '../types';
import { useWizard } from '../WizardContext';

interface ExtendedBandwidthConfig extends BandwidthConfig {
  download: {
    total_limit: number;
    client_percents?: Record<string, number>;
  };
  upload: {
    total_limit: number;
    upload_client_percents?: Record<string, number>;
  };
}

export const BandwidthStep: React.FC<WizardStepProps> = ({
  data,
  onDataChange,
  showValidation,
  isLoading,
  readOnly,
}) => {
  const { state } = useWizard();

  const [config, setConfig] = useState<ExtendedBandwidthConfig>(() => data || {
    download: {
      total_limit: 100,
      client_percents: {},
    },
    upload: {
      total_limit: 20,
      upload_client_percents: {},
    },
  });

  // Get enabled download clients
  const enabledClients = useMemo(() => {
    return (state.downloadClients || []).filter((c: DownloadClientConfig) => c.enabled);
  }, [state.downloadClients]);

  const uploadCapableClients = useMemo(() => {
    return enabledClients.filter((c: DownloadClientConfig) => c.supports_upload);
  }, [enabledClients]);

  // Initialize default splits when clients change
  // Uses client.type as key to match backend config structure
  useEffect(() => {
    if (enabledClients.length >= 2) {
      const equalPercent = Math.floor(100 / enabledClients.length);
      const newPercents: Record<string, number> = {};

      enabledClients.forEach((client: DownloadClientConfig, index: number) => {
        const existing = config.download.client_percents?.[client.type];
        if (existing !== undefined) {
          newPercents[client.type] = existing;
        } else {
          const remaining = 100 - equalPercent * index;
          newPercents[client.type] = index === enabledClients.length - 1 ? remaining : equalPercent;
        }
      });

      setConfig(prev => ({
        ...prev,
        download: {
          ...prev.download,
          client_percents: newPercents,
        }
      }));
    }
  }, [enabledClients.length]);

  // Initialize upload splits
  // Uses client.type as key to match backend config structure
  useEffect(() => {
    if (uploadCapableClients.length >= 2) {
      const equalPercent = Math.floor(100 / uploadCapableClients.length);
      const newUploadPercents: Record<string, number> = {};

      uploadCapableClients.forEach((client: DownloadClientConfig, index: number) => {
        const existing = config.upload.upload_client_percents?.[client.type];
        if (existing !== undefined) {
          newUploadPercents[client.type] = existing;
        } else {
          const remaining = 100 - equalPercent * index;
          newUploadPercents[client.type] = index === uploadCapableClients.length - 1 ? remaining : equalPercent;
        }
      });

      setConfig(prev => ({
        ...prev,
        upload: {
          ...prev.upload,
          upload_client_percents: newUploadPercents,
        }
      }));
    }
  }, [uploadCapableClients.length]);

  // Update parent when config changes
  useEffect(() => {
    onDataChange(config);
  }, [config, onDataChange]);

  const updateDownloadLimit = (value: number) => {
    setConfig(prev => ({
      ...prev,
      download: { ...prev.download, total_limit: value },
    }));
  };

  const updateUploadLimit = (value: number) => {
    setConfig(prev => ({
      ...prev,
      upload: { ...prev.upload, total_limit: value },
    }));
  };

  // Update download split for 2 clients (slider)
  // Uses client.type as key to match backend config structure
  const updateDownloadSplit = (firstClientPercent: number) => {
    if (enabledClients.length !== 2) return;
    // Clamp to 5-95 range to ensure both clients get some bandwidth
    const clamped = Math.max(5, Math.min(95, firstClientPercent));
    const [first, second] = enabledClients;
    setConfig(prev => ({
      ...prev,
      download: {
        ...prev.download,
        client_percents: {
          [first.type]: clamped,
          [second.type]: 100 - clamped,
        },
      }
    }));
  };

  // Update download percent for individual client (3+ clients)
  // Uses client.type as key to match backend config structure
  const updateClientPercent = (clientType: string, percent: number) => {
    setConfig(prev => ({
      ...prev,
      download: {
        ...prev.download,
        client_percents: {
          ...prev.download.client_percents,
          [clientType]: percent,
        },
      }
    }));
  };

  // Update upload split for 2 clients
  // Uses client.type as key to match backend config structure
  const updateUploadSplit = (firstClientPercent: number) => {
    if (uploadCapableClients.length !== 2) return;
    // Clamp to 5-95 range to ensure both clients get some bandwidth
    const clamped = Math.max(5, Math.min(95, firstClientPercent));
    const [first, second] = uploadCapableClients;
    setConfig(prev => ({
      ...prev,
      upload: {
        ...prev.upload,
        upload_client_percents: {
          [first.type]: clamped,
          [second.type]: 100 - clamped,
        },
      }
    }));
  };

  // Update upload percent for individual client
  // Uses client.type as key to match backend config structure
  const updateUploadClientPercent = (clientType: string, percent: number) => {
    setConfig(prev => ({
      ...prev,
      upload: {
        ...prev.upload,
        upload_client_percents: {
          ...prev.upload.upload_client_percents,
          [clientType]: percent,
        },
      }
    }));
  };

  const downloadValid = config.download.total_limit > 0;
  const uploadValid = config.upload.total_limit > 0;

  // Calculate total percentages
  const downloadTotalPercent = Object.values(config.download.client_percents || {}).reduce((a, b) => a + b, 0);
  const uploadTotalPercent = Object.values(config.upload.upload_client_percents || {}).reduce((a, b) => a + b, 0);

  if (readOnly) {
    return (
      <div className="space-y-4">
        <h3 className="font-medium">Bandwidth Limits</h3>
        <div className="grid gap-2 text-sm">
          <div className="flex justify-between py-2 border-b">
            <span className="text-muted-foreground">Download Limit</span>
            <span>{config.download.total_limit} Mbps</span>
          </div>
          <div className="flex justify-between py-2 border-b">
            <span className="text-muted-foreground">Upload Limit</span>
            <span>{config.upload.total_limit} Mbps</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-xl font-semibold">Set Bandwidth Limits</h2>
        <p className="text-sm text-muted-foreground">
          Enter your total available bandwidth.
        </p>
      </div>

      <div className="space-y-6 max-w-md mx-auto">
        {/* Download limit */}
        <div className="space-y-2">
          <Label htmlFor="download-limit" className="text-base font-medium">
            Total Download Bandwidth (Mbps)
          </Label>
          <Input
            id="download-limit"
            type="number"
            min="1"
            step="1"
            value={config.download.total_limit}
            onChange={(e) => updateDownloadLimit(parseFloat(e.target.value) || 0)}
            disabled={isLoading}
            className={showValidation && !downloadValid ? 'border-destructive' : ''}
          />
          <p className="text-xs text-muted-foreground">
            Your allocated download speed (10-20% less than your actual is recommended)
          </p>
          {showValidation && !downloadValid && (
            <p className="text-xs text-destructive">Download limit must be greater than 0</p>
          )}
        </div>

        {/* Bandwidth allocation explanation - only show when 2+ clients */}
        {enabledClients.length >= 2 && (
          <div className="text-sm text-muted-foreground space-y-1 p-3 rounded-lg bg-blue-50 dark:bg-blue-950/30 border border-blue-200 dark:border-blue-800">
            <p className="font-medium text-foreground">How bandwidth is allocated:</p>
            <ul className="list-disc list-inside space-y-0.5 text-xs">
              <li><strong>No active downloads:</strong> Bandwidth split evenly between clients</li>
              <li><strong>One client downloading:</strong> 95% allocated to the active client</li>
              <li><strong>Multiple clients active:</strong> Follows your configured ratios below</li>
            </ul>
          </div>
        )}

        {/* Download client split - 2 clients: slider */}
        {enabledClients.length === 2 && (
          <div className="space-y-3 p-4 border rounded-lg bg-muted/30">
            <Label className="text-sm font-medium">Download Bandwidth Split</Label>
            <SplitSlider
              value={config.download.client_percents?.[enabledClients[0].type] || 50}
              onChange={(value) => updateDownloadSplit(value)}
              leftLabel={enabledClients[0].name}
              rightLabel={enabledClients[1].name}
              leftColor={enabledClients[0].color}
              rightColor={enabledClients[1].color}
              disabled={isLoading}
            />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>{(config.download.total_limit * (config.download.client_percents?.[enabledClients[0].type] || 50) / 100).toFixed(1)} Mbps</span>
              <span>{(config.download.total_limit * (config.download.client_percents?.[enabledClients[1].type] || 50) / 100).toFixed(1)} Mbps</span>
            </div>
          </div>
        )}

        {/* Download client split - 3+ clients: manual entry */}
        {enabledClients.length >= 3 && (
          <div className="space-y-3 p-4 border rounded-lg bg-muted/30">
            <Label className="text-sm font-medium">Download Bandwidth Split</Label>
            <p className="text-xs text-muted-foreground">
              Set the percentage of download bandwidth for each client (should total 100%)
            </p>
            <div className="space-y-2">
              {enabledClients.map((client: DownloadClientConfig) => (
                <div key={client.id} className="flex items-center gap-3">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: client.color }}
                  />
                  <span className="text-sm flex-1">{client.name}</span>
                  <Input
                    type="number"
                    min="0"
                    max="100"
                    value={config.download.client_percents?.[client.type] || 0}
                    onChange={(e) => updateClientPercent(client.type, parseInt(e.target.value) || 0)}
                    className="w-20 text-right"
                  />
                  <span className="text-sm text-muted-foreground">%</span>
                </div>
              ))}
              <div className={`text-xs ${downloadTotalPercent === 100 ? 'text-green-600' : 'text-destructive'}`}>
                Total: {downloadTotalPercent}% {downloadTotalPercent !== 100 && '(should be 100%)'}
              </div>
            </div>
          </div>
        )}

        {/* Upload limit */}
        <div className="space-y-2">
          <Label htmlFor="upload-limit" className="text-base font-medium">
            Total Upload Bandwidth (Mbps)
          </Label>
          <Input
            id="upload-limit"
            type="number"
            min="1"
            step="1"
            value={config.upload.total_limit}
            onChange={(e) => updateUploadLimit(parseFloat(e.target.value) || 0)}
            disabled={isLoading}
            className={showValidation && !uploadValid ? 'border-destructive' : ''}
          />
          <p className="text-xs text-muted-foreground">
            Your allocated upload speed (10-20% less than your actual is recommended)
          </p>
          {showValidation && !uploadValid && (
            <p className="text-xs text-destructive">Upload limit must be greater than 0</p>
          )}
        </div>

        {/* Upload client split - 2 clients: slider */}
        {uploadCapableClients.length === 2 && (
          <div className="space-y-3 p-4 border rounded-lg bg-muted/30">
            <Label className="text-sm font-medium">Upload Bandwidth Split</Label>
            <SplitSlider
              value={config.upload.upload_client_percents?.[uploadCapableClients[0].type] || 50}
              onChange={(value) => updateUploadSplit(value)}
              leftLabel={uploadCapableClients[0].name}
              rightLabel={uploadCapableClients[1].name}
              leftColor={uploadCapableClients[0].color}
              rightColor={uploadCapableClients[1].color}
              disabled={isLoading}
            />
            <div className="flex justify-between text-sm text-muted-foreground">
              <span>{(config.upload.total_limit * (config.upload.upload_client_percents?.[uploadCapableClients[0].type] || 50) / 100).toFixed(1)} Mbps</span>
              <span>{(config.upload.total_limit * (config.upload.upload_client_percents?.[uploadCapableClients[1].type] || 50) / 100).toFixed(1)} Mbps</span>
            </div>
          </div>
        )}

        {/* Upload client split - 3+ clients: manual entry */}
        {uploadCapableClients.length >= 3 && (
          <div className="space-y-3 p-4 border rounded-lg bg-muted/30">
            <Label className="text-sm font-medium">Upload Bandwidth Split</Label>
            <p className="text-xs text-muted-foreground">
              Set the percentage of upload bandwidth for each client (should total 100%)
            </p>
            <div className="space-y-2">
              {uploadCapableClients.map((client: DownloadClientConfig) => (
                <div key={client.id} className="flex items-center gap-3">
                  <div
                    className="w-3 h-3 rounded-full flex-shrink-0"
                    style={{ backgroundColor: client.color }}
                  />
                  <span className="text-sm flex-1">{client.name}</span>
                  <Input
                    type="number"
                    min="0"
                    max="100"
                    value={config.upload.upload_client_percents?.[client.type] || 0}
                    onChange={(e) => updateUploadClientPercent(client.type, parseInt(e.target.value) || 0)}
                    className="w-20 text-right"
                  />
                  <span className="text-sm text-muted-foreground">%</span>
                </div>
              ))}
              <div className={`text-xs ${uploadTotalPercent === 100 ? 'text-green-600' : 'text-destructive'}`}>
                Total: {uploadTotalPercent}% {uploadTotalPercent !== 100 && '(should be 100%)'}
              </div>
            </div>
          </div>
        )}

        {/* Help text */}
        <div className="bg-muted/50 rounded-lg p-4 text-sm">
          <p className="font-medium mb-2">How to find your bandwidth:</p>
          <ul className="list-disc list-inside space-y-1 text-muted-foreground">
            <li>Check your ISP plan or bill</li>
            <li>Run a speed test at fast.com or speedtest.net</li>
          </ul>
        </div>
      </div>
    </div>
  );
};

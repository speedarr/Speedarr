import React, { useState, useEffect, useRef, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { PasswordInput } from './PasswordInput';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';
import type { SNMPInterface } from '@/types';

interface SNMPConfig {
  enabled: boolean;
  host: string;
  port: number;
  version: string;
  community: string;
  interface: string;
}

export const SNMPSettings: React.FC = () => {
  const [config, setConfig] = useState<SNMPConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryCountdown, setDiscoveryCountdown] = useState<number>(0);
  const [discoveryTotal, setDiscoveryTotal] = useState<number>(0);
  const [interfaces, setInterfaces] = useState<SNMPInterface[]>([]);
  const [selectedInterface, setSelectedInterface] = useState<string>('');

  // Live polling state
  const [isLivePolling, setIsLivePolling] = useState(false);
  const [livePollingCountdown, setLivePollingCountdown] = useState(0);
  const livePollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<SNMPConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'snmp',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('snmp');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('snmp');
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
      await apiClient.updateSettingsSection('snmp', config);
      resetOriginal(config);
      setSuccess('SNMP settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const updateConfig = (field: keyof SNMPConfig, value: any) => {
    if (!config) return;
    setConfig({ ...config, [field]: value });
  };

  const handleTestConnection = async () => {
    if (!config) return;

    setIsTesting(true);
    setTestResult(null);

    try {
      const response = await apiClient.testSNMPConnection(config);
      setTestResult({ success: response.success, message: response.message });
      if (response.success) {
        setTimeout(() => setTestResult(null), 3000);
      }
    } catch (error: unknown) {
      setTestResult({
        success: false,
        message: getErrorMessage(error),
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleDiscoverInterfaces = async () => {
    if (!config) return;

    setIsDiscovering(true);
    setError('');
    setInterfaces([]);

    // Estimate time: ~1 second per interface, typical device has 20-50 interfaces
    // Start with estimated 30 seconds for initial discovery
    const estimatedSeconds = 45;
    setDiscoveryTotal(estimatedSeconds);
    setDiscoveryCountdown(estimatedSeconds);

    // Start countdown timer
    const countdownInterval = setInterval(() => {
      setDiscoveryCountdown((prev) => {
        if (prev <= 1) {
          return 0;
        }
        return prev - 1;
      });
    }, 1000);

    try {
      const response = await apiClient.discoverSNMPInterfaces(config);

      if (response.success && response.interfaces) {
        // Filter out interfaces with zero combined traffic, then sort by traffic descending
        const filteredAndSorted = [...response.interfaces]
          .filter((iface) => {
            const total = (iface.in_gb || 0) + (iface.out_gb || 0);
            return total > 0;
          })
          .sort((a, b) => {
            // Sort by Total In (download) descending
            return (b.in_gb || 0) - (a.in_gb || 0);
          });

        setInterfaces(filteredAndSorted);

        // Auto-select suggested WAN interface if available
        if (response.suggested_wan) {
          setSelectedInterface(response.suggested_wan);
          updateConfig('interface', response.suggested_wan);
        }

        // Start live polling for 15 seconds
        if (filteredAndSorted.length > 0) {
          startLivePolling(filteredAndSorted);
        }
      } else {
        setError(response.message || 'Failed to discover interfaces');
      }
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      clearInterval(countdownInterval);
      setIsDiscovering(false);
      setDiscoveryCountdown(0);
      setDiscoveryTotal(0);
    }
  };

  const selectInterface = (index: number) => {
    const indexStr = index.toString();
    setSelectedInterface(indexStr);
    updateConfig('interface', indexStr);
  };

  // Start live polling for 15 seconds
  const startLivePolling = useCallback(
    (discoveredInterfaces: SNMPInterface[]) => {
      if (!config) return;

      setIsLivePolling(true);
      setLivePollingCountdown(30);

      // Start countdown
      const countdownInterval = setInterval(() => {
        setLivePollingCountdown((prev) => {
          if (prev <= 1) {
            clearInterval(countdownInterval);
            return 0;
          }
          return prev - 1;
        });
      }, 1000);

      // Poll every 2 seconds (backend takes ~1s for measurement)
      const pollSpeeds = async () => {
        if (!config) return;

        try {
          const interfaceIndices = discoveredInterfaces.map((i) => i.index);
          const response = await apiClient.pollSNMPSpeeds(config, interfaceIndices);

          if (response.success && response.speeds) {
            const speedsData = response.speeds;
            // Update interface speeds
            setInterfaces((prevInterfaces) =>
              prevInterfaces.map((iface) => {
                const speeds = speedsData[iface.index.toString()];
                if (speeds) {
                  return {
                    ...iface,
                    current_in_mbps: speeds.current_in_mbps,
                    current_out_mbps: speeds.current_out_mbps,
                  };
                }
                return iface;
              })
            );
          }
        } catch (err) {
          console.error('Failed to poll speeds:', err);
        }
      };

      // Add initial delay to let SNMP cache clear after discovery, then poll on interval
      // The first poll right after discovery often gets stale data
      setTimeout(() => {
        pollSpeeds();
        livePollingIntervalRef.current = setInterval(pollSpeeds, 7000);
      }, 4000);

      // Stop after 30 seconds
      setTimeout(() => {
        if (livePollingIntervalRef.current) {
          clearInterval(livePollingIntervalRef.current);
          livePollingIntervalRef.current = null;
        }
        clearInterval(countdownInterval);
        setIsLivePolling(false);
        setLivePollingCountdown(0);
      }, 30000);
    },
    [config]
  );

  // Cleanup on unmount
  useEffect(() => {
    return () => {
      if (livePollingIntervalRef.current) {
        clearInterval(livePollingIntervalRef.current);
      }
    };
  }, []);

  // Format GB with appropriate units
  const formatTraffic = (gb: number): string => {
    if (gb >= 1000) {
      return `${(gb / 1000).toFixed(1)} TB`;
    }
    return `${gb.toFixed(1)} GB`;
  };

  // Format Mbps with appropriate units
  const formatSpeed = (mbps: number): string => {
    if (mbps >= 1000) {
      return `${(mbps / 1000).toFixed(2)} Gbps`;
    }
    if (mbps >= 1) {
      return `${mbps.toFixed(1)} Mbps`;
    }
    if (mbps >= 0.001) {
      return `${(mbps * 1000).toFixed(0)} Kbps`;
    }
    return '0';
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
            <AlertDescription>Failed to load SNMP configuration</AlertDescription>
          </Alert>
        </CardContent>
      </Card>
    );
  }

  return (
    <Card>
      <CardHeader>
        <CardTitle>SNMP Network Monitoring</CardTitle>
        <CardDescription>
          Monitor network bandwidth usage via SNMP (optional feature)
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
          <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="snmp-enabled">Enable SNMP Monitoring</Label>
              <p className="text-sm text-muted-foreground">
                Query network device for bandwidth usage data
              </p>
            </div>
            <Switch
              id="snmp-enabled"
              checked={config.enabled}
              onCheckedChange={(checked) => updateConfig('enabled', checked)}
              disabled={isSaving}
            />
          </div>

          {config.enabled && (
            <>
              <div className="grid grid-cols-2 gap-4">
                <div className="space-y-2">
                  <Label htmlFor="snmp-host">SNMP Host</Label>
                  <Input
                    id="snmp-host"
                    value={config.host}
                    onChange={(e) => updateConfig('host', e.target.value)}
                    placeholder="192.168.1.1"
                    disabled={isSaving}
                    maxLength={255}
                  />
                  <p className="text-sm text-muted-foreground">
                    IP address or hostname of network device
                  </p>
                </div>

                <div className="space-y-2">
                  <Label htmlFor="snmp-port">Port</Label>
                  <Input
                    id="snmp-port"
                    type="number"
                    min="1"
                    max="65535"
                    value={config.port}
                    onChange={(e) => updateConfig('port', parseInt(e.target.value))}
                    disabled={isSaving}
                  />
                  <p className="text-sm text-muted-foreground">
                    SNMP port (default: 161)
                  </p>
                </div>
              </div>

              <div className="space-y-2">
                <Label htmlFor="snmp-community">Community String</Label>
                <PasswordInput
                  value={config.community === '***REDACTED***' ? '' : config.community}
                  onChange={(e) => updateConfig('community', e.target.value)}
                  placeholder={config.community === '***REDACTED***' ? 'Current community string is set' : 'public'}
                  disabled={isSaving}
                  maxLength={64}
                />
                <p className="text-sm text-muted-foreground">
                  SNMP v2c community string (default: public)
                </p>
              </div>

              {/* Test Connection and Interface Discovery */}
              <div className="space-y-4">
                <div className="flex gap-2 items-center">
                  <Button
                    onClick={handleTestConnection}
                    disabled={isTesting || isSaving || !config.host}
                    variant="outline"
                    type="button"
                  >
                    {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Test Connection
                  </Button>

                  <Button
                    onClick={handleDiscoverInterfaces}
                    disabled={isDiscovering || isSaving || !config.host || isLivePolling}
                    variant="outline"
                    type="button"
                  >
                    {isDiscovering && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    {isDiscovering
                      ? `Discovering... ${discoveryCountdown}s remaining`
                      : 'Discover Interfaces'
                    }
                  </Button>
                </div>

                {isDiscovering && discoveryTotal > 0 && (
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm text-muted-foreground">
                      <span>Scanning network interfaces...</span>
                      <span>{discoveryCountdown}s / {discoveryTotal}s</span>
                    </div>
                    <div className="w-full bg-secondary rounded-full h-2">
                      <div
                        className="bg-primary h-2 rounded-full transition-all duration-1000"
                        style={{ width: `${((discoveryTotal - discoveryCountdown) / discoveryTotal) * 100}%` }}
                      />
                    </div>
                  </div>
                )}

                {testResult && !isDiscovering && !isLivePolling && (
                  <Alert variant={testResult.success ? 'default' : 'destructive'}>
                    {testResult.success ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                    <AlertDescription>{testResult.message}</AlertDescription>
                  </Alert>
                )}

                {isLivePolling && (
                  <div className="space-y-2">
                    <div className="flex justify-between text-sm">
                      <span className="flex items-center gap-2">
                        <span className="h-2 w-2 bg-green-500 rounded-full animate-pulse" />
                        <span className="text-green-600 font-medium">Live monitoring active</span>
                      </span>
                      <span className="text-muted-foreground">{livePollingCountdown}s remaining</span>
                    </div>
                    <p className="text-xs text-muted-foreground">
                      Speed data may take a few seconds to appear as measurements are collected over time.
                    </p>
                    <div className="w-full bg-secondary rounded-full h-1.5">
                      <div
                        className="bg-green-500 h-1.5 rounded-full transition-all duration-1000"
                        style={{ width: `${((30 - livePollingCountdown) / 30) * 100}%` }}
                      />
                    </div>
                  </div>
                )}
              </div>

              {/* Interface Selection */}
              {interfaces.length > 0 ? (
                <div className="space-y-2">
                  <Label>Select Network Interface</Label>
                  <p className="text-sm text-muted-foreground mb-2">
                    {isLivePolling
                      ? `Showing live speeds for ${interfaces.length} interfaces. Click to select.`
                      : `Sorted by Total In. Click to select. Found ${interfaces.length} active interfaces.`
                    }
                  </p>
                  <div className="border rounded-lg overflow-hidden">
                    <table className="w-full text-sm">
                      <thead>
                        <tr className="bg-muted text-xs font-medium text-muted-foreground border-b">
                          <th className="p-2 text-left">Interface</th>
                          <th className="p-2 text-right whitespace-nowrap">Current In</th>
                          <th className="p-2 text-right whitespace-nowrap">Current Out</th>
                          <th className="p-2 text-right whitespace-nowrap">Total In</th>
                          <th className="p-2 text-right whitespace-nowrap">Total Out</th>
                          <th className="p-2 text-right whitespace-nowrap">Combined</th>
                        </tr>
                      </thead>
                      <tbody className="divide-y">
                        {interfaces.map((iface) => {
                          const totalTraffic = (iface.in_gb || 0) + (iface.out_gb || 0);
                          const isSelected = selectedInterface === iface.index.toString();

                          return (
                            <tr
                              key={iface.index}
                              className={`cursor-pointer hover:bg-muted/50 transition-colors ${
                                isSelected ? 'bg-primary/10' : ''
                              }`}
                              onClick={() => selectInterface(iface.index)}
                            >
                              <td className={`p-2 ${isSelected ? 'border-l-4 border-primary' : ''}`}>
                                <div className="font-medium">{iface.name}</div>
                                {iface.is_wan_candidate && (
                                  <span className="inline-flex items-center rounded-md bg-green-50 px-1.5 py-0.5 text-xs font-medium text-green-700 ring-1 ring-inset ring-green-600/20">
                                    Likely WAN Interface
                                  </span>
                                )}
                              </td>
                              <td className="p-2 text-right whitespace-nowrap">
                                <span className={(iface.current_in_mbps ?? 0) > 0 ? 'text-green-600 font-medium' : 'text-muted-foreground'}>
                                  {formatSpeed(iface.current_in_mbps ?? 0)}
                                </span>
                              </td>
                              <td className="p-2 text-right whitespace-nowrap">
                                <span className={(iface.current_out_mbps ?? 0) > 0 ? 'text-blue-600 font-medium' : 'text-muted-foreground'}>
                                  {formatSpeed(iface.current_out_mbps ?? 0)}
                                </span>
                              </td>
                              <td className="p-2 text-right text-muted-foreground whitespace-nowrap">
                                {formatTraffic(iface.in_gb || 0)}
                              </td>
                              <td className="p-2 text-right text-muted-foreground whitespace-nowrap">
                                {formatTraffic(iface.out_gb || 0)}
                              </td>
                              <td className="p-2 text-right font-medium whitespace-nowrap">
                                {formatTraffic(totalTraffic)}
                              </td>
                            </tr>
                          );
                        })}
                      </tbody>
                    </table>
                  </div>
                  <p className="text-sm text-muted-foreground">
                    Selected interface: {selectedInterface ? `${selectedInterface} (${interfaces.find(i => i.index.toString() === selectedInterface)?.name || ''})` : 'None'}
                  </p>
                </div>
              ) : (
                <div className="space-y-2">
                  <Label htmlFor="snmp-interface">Network Interface</Label>
                  <Input
                    id="snmp-interface"
                    value={config.interface}
                    onChange={(e) => updateConfig('interface', e.target.value)}
                    placeholder="eth0 or 1"
                    disabled={isSaving}
                    maxLength={100}
                  />
                  <p className="text-sm text-muted-foreground">
                    Click &quot;Discover Interfaces&quot; above, or manually enter interface name/index
                  </p>
                </div>
              )}

              <Alert>
                <AlertDescription>
                  <strong>Note:</strong> SNMP monitoring is optional. Speedarr can function without it by relying on Plex stream data and configured bandwidth limits.
                </AlertDescription>
              </Alert>
            </>
          )}
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

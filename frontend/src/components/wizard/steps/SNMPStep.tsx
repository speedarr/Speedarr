/**
 * SNMP Step - Optional SNMP network monitoring configuration
 */

import React, { useState, useCallback, useEffect, useRef } from 'react';
import { WizardStepProps, SNMPConfig } from '../types';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import { PasswordInput } from '@/components/settings/PasswordInput';
import { Loader2, CheckCircle, AlertCircle, Activity, Info, Search } from 'lucide-react';
import { apiClient } from '@/api/client';
import { useWizard } from '../WizardContext';
import { getErrorMessage } from '@/lib/utils';
import type { SNMPInterface } from '@/types';

const DEFAULT_SNMP_CONFIG: SNMPConfig = {
  enabled: false,
  host: '',
  port: 161,
  version: 'v2c',
  community: 'public',
  interface: '',
};

export const SNMPStep: React.FC<WizardStepProps> = ({
  showValidation,
}) => {
  const { state, updateState } = useWizard();
  const config = state.snmp || DEFAULT_SNMP_CONFIG;

  const [isTesting, setIsTesting] = useState(false);
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [isDiscovering, setIsDiscovering] = useState(false);
  const [discoveryCountdown, setDiscoveryCountdown] = useState(0);
  const [interfaces, setInterfaces] = useState<SNMPInterface[]>([]);
  const [selectedInterface, setSelectedInterface] = useState<string>(config.interface || '');

  // Live polling state
  const [isLivePolling, setIsLivePolling] = useState(false);
  const [livePollingCountdown, setLivePollingCountdown] = useState(0);
  const livePollingIntervalRef = useRef<ReturnType<typeof setInterval> | null>(null);

  const updateConfig = (field: keyof SNMPConfig, value: any) => {
    updateState({
      snmp: { ...config, [field]: value },
    });
  };

  const handleTestConnection = async () => {
    setIsTesting(true);
    setTestResult(null);

    try {
      const response = await apiClient.testSNMPConnection(config);
      setTestResult({ success: response.success, message: response.message });
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
    setIsDiscovering(true);
    setTestResult(null);
    setInterfaces([]);

    const estimatedSeconds = 45;
    setDiscoveryCountdown(estimatedSeconds);

    const countdownInterval = setInterval(() => {
      setDiscoveryCountdown((prev) => {
        if (prev <= 1) return 0;
        return prev - 1;
      });
    }, 1000);

    try {
      const response = await apiClient.discoverSNMPInterfaces(config);

      if (response.success && response.interfaces) {
        // Filter and sort interfaces by traffic
        const filteredAndSorted = [...response.interfaces]
          .filter((iface: SNMPInterface) => {
            const total = (iface.in_gb || 0) + (iface.out_gb || 0);
            return total > 0;
          })
          .sort((a: SNMPInterface, b: SNMPInterface) => {
            return (b.in_gb || 0) - (a.in_gb || 0);
          });

        setInterfaces(filteredAndSorted);

        // Auto-select suggested WAN interface
        if (response.suggested_wan) {
          setSelectedInterface(response.suggested_wan);
          updateConfig('interface', response.suggested_wan);
        }

        // Start live polling to show real-time speeds
        if (filteredAndSorted.length > 0) {
          startLivePolling(filteredAndSorted);
        }
      } else {
        setTestResult({
          success: false,
          message: response.message || 'Failed to discover interfaces',
        });
      }
    } catch (error: unknown) {
      setTestResult({
        success: false,
        message: getErrorMessage(error),
      });
    } finally {
      clearInterval(countdownInterval);
      setIsDiscovering(false);
      setDiscoveryCountdown(0);
    }
  };

  const selectInterface = (index: number) => {
    const indexStr = index.toString();
    setSelectedInterface(indexStr);
    updateConfig('interface', indexStr);
  };

  // Start live polling for 30 seconds
  const startLivePolling = useCallback(
    (discoveredInterfaces: SNMPInterface[]) => {
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

      // Poll every 7 seconds (backend takes ~1s for measurement)
      const pollSpeeds = async () => {
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

      // Add initial delay to let SNMP cache clear after discovery
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

  const formatTraffic = (gb: number): string => {
    if (gb >= 1000) {
      return `${(gb / 1000).toFixed(1)} TB`;
    }
    return `${gb.toFixed(1)} GB`;
  };

  const formatSpeed = (mbps: number): string => {
    if (mbps >= 1000) {
      return `${(mbps / 1000).toFixed(2)} Gbps`;
    }
    if (mbps >= 1) {
      return `${mbps.toFixed(1)} Mbps`;
    }
    if (mbps > 0) {
      return `${(mbps * 1000).toFixed(0)} Kbps`;
    }
    return '0 Mbps';
  };

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <div className="flex justify-center">
          <div className="h-16 w-16 bg-purple-100 dark:bg-purple-900/20 rounded-full flex items-center justify-center">
            <Activity className="h-8 w-8 text-purple-600 dark:text-purple-400" />
          </div>
        </div>
        <h2 className="text-2xl font-bold">SNMP Network Monitoring</h2>
        <p className="text-muted-foreground">
          Optionally monitor your router/firewall bandwidth via SNMP
        </p>
      </div>

      <Alert>
        <Info className="h-4 w-4" />
        <AlertDescription>
          <strong>This step is optional.</strong> SNMP monitoring provides accurate WAN bandwidth data from your network device.
          Speedarr works without it by using configured bandwidth limits.
        </AlertDescription>
      </Alert>

      <div className="space-y-4">
        <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
          <div className="space-y-0.5">
            <Label htmlFor="snmp-enabled">Enable SNMP Monitoring</Label>
            <p className="text-sm text-muted-foreground">
              Query network device for real-time bandwidth data
            </p>
          </div>
          <Switch
            id="snmp-enabled"
            checked={config.enabled}
            onCheckedChange={(checked) => updateConfig('enabled', checked)}
          />
        </div>

        {config.enabled && (
          <>
            <div className="grid grid-cols-2 gap-4">
              <div className="space-y-2">
                <Label htmlFor="snmp-host">
                  SNMP Host <span className="text-destructive">*</span>
                </Label>
                <Input
                  id="snmp-host"
                  value={config.host}
                  onChange={(e) => updateConfig('host', e.target.value)}
                  placeholder="192.168.1.1"
                  className={showValidation && config.enabled && !config.host ? 'border-destructive' : ''}
                  maxLength={255}
                />
                <p className="text-sm text-muted-foreground">
                  Router/firewall IP address
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
                  onChange={(e) => updateConfig('port', parseInt(e.target.value) || 161)}
                />
                <p className="text-sm text-muted-foreground">
                  Default: 161
                </p>
              </div>
            </div>

            <div className="space-y-2">
              <Label htmlFor="snmp-community">Community String</Label>
              <PasswordInput
                value={config.community}
                onChange={(e) => updateConfig('community', e.target.value)}
                placeholder="public"
                maxLength={64}
              />
              <p className="text-sm text-muted-foreground">
                SNMP v2c community string (usually "public" for read-only)
              </p>
            </div>

            <div className="flex gap-2 items-center">
              <Button
                onClick={handleTestConnection}
                disabled={isTesting || isDiscovering || !config.host}
                variant="outline"
                type="button"
              >
                {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                Test Connection
              </Button>

              <Button
                onClick={handleDiscoverInterfaces}
                disabled={isDiscovering || isTesting || !config.host}
                variant="outline"
                type="button"
              >
                {isDiscovering ? (
                  <Loader2 className="mr-2 h-4 w-4 animate-spin" />
                ) : (
                  <Search className="mr-2 h-4 w-4" />
                )}
                {isDiscovering ? `Discovering... ${discoveryCountdown}s` : 'Discover Interfaces'}
              </Button>
            </div>

            {isDiscovering && (
              <div className="space-y-2">
                <div className="flex justify-between text-sm text-muted-foreground">
                  <span>Scanning network interfaces...</span>
                  <span>{discoveryCountdown}s remaining</span>
                </div>
                <div className="w-full bg-secondary rounded-full h-2">
                  <div
                    className="bg-primary h-2 rounded-full transition-all duration-1000"
                    style={{ width: `${((45 - discoveryCountdown) / 45) * 100}%` }}
                  />
                </div>
              </div>
            )}

            {testResult && !isDiscovering && (
              <Alert variant={testResult.success ? 'default' : 'destructive'}>
                {testResult.success ? (
                  <CheckCircle className="h-4 w-4" />
                ) : (
                  <AlertCircle className="h-4 w-4" />
                )}
                <AlertDescription>{testResult.message}</AlertDescription>
              </Alert>
            )}

            {/* Interface Selection Table */}
            {interfaces.length > 0 && (
              <div className="space-y-2">
                <div className="flex items-center justify-between">
                  <Label>Select Network Interface</Label>
                  {isLivePolling && (
                    <span className="text-sm text-muted-foreground flex items-center gap-2">
                      <Loader2 className="h-3 w-3 animate-spin" />
                      Monitoring speeds... {livePollingCountdown}s
                    </span>
                  )}
                </div>
                <p className="text-sm text-muted-foreground mb-2">
                  Showing {interfaces.length} active interfaces. Click to select your WAN interface.
                </p>
                <div className="border rounded-lg overflow-hidden max-h-64 overflow-y-auto">
                  <table className="w-full text-sm">
                    <thead className="sticky top-0">
                      <tr className="bg-muted text-xs font-medium text-muted-foreground border-b">
                        <th className="p-2 text-left">Interface</th>
                        <th className="p-2 text-right">Download</th>
                        <th className="p-2 text-right">Upload</th>
                        <th className="p-2 text-right">Total In</th>
                        <th className="p-2 text-right">Total Out</th>
                      </tr>
                    </thead>
                    <tbody className="divide-y">
                      {interfaces.map((iface) => {
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
                                <span className="inline-flex items-center rounded-md bg-green-50 dark:bg-green-900/20 px-1.5 py-0.5 text-xs font-medium text-green-700 dark:text-green-400 ring-1 ring-inset ring-green-600/20">
                                  Likely WAN
                                </span>
                              )}
                            </td>
                            <td className="p-2 text-right whitespace-nowrap">
                              <span className={(iface.current_in_mbps || 0) > 0 ? 'text-green-600 font-medium' : 'text-muted-foreground'}>
                                {formatSpeed(iface.current_in_mbps || 0)}
                              </span>
                            </td>
                            <td className="p-2 text-right whitespace-nowrap">
                              <span className={(iface.current_out_mbps || 0) > 0 ? 'text-blue-600 font-medium' : 'text-muted-foreground'}>
                                {formatSpeed(iface.current_out_mbps || 0)}
                              </span>
                            </td>
                            <td className="p-2 text-right text-muted-foreground">
                              {formatTraffic(iface.in_gb || 0)}
                            </td>
                            <td className="p-2 text-right text-muted-foreground">
                              {formatTraffic(iface.out_gb || 0)}
                            </td>
                          </tr>
                        );
                      })}
                    </tbody>
                  </table>
                </div>
                {isLivePolling && (
                  <p className="text-sm text-muted-foreground italic">
                    Speed data may take a few seconds to appear. Active interfaces will show current throughput.
                  </p>
                )}
                {selectedInterface && (
                  <p className="text-sm text-green-600 dark:text-green-400 flex items-center gap-1">
                    <CheckCircle className="h-4 w-4" />
                    Selected interface: {selectedInterface} ({interfaces.find(i => i.index.toString() === selectedInterface)?.name || ''})
                  </p>
                )}
              </div>
            )}

            {interfaces.length === 0 && !isDiscovering && (
              <div className="space-y-2">
                <Label htmlFor="snmp-interface">Interface (Manual Entry)</Label>
                <Input
                  id="snmp-interface"
                  value={config.interface}
                  onChange={(e) => updateConfig('interface', e.target.value)}
                  placeholder="Click 'Discover Interfaces' or enter manually"
                  maxLength={100}
                />
                <p className="text-sm text-muted-foreground">
                  Enter interface name or index number
                </p>
              </div>
            )}
          </>
        )}

        {!config.enabled && (
          <div className="text-center py-6 text-muted-foreground">
            <p>SNMP monitoring is disabled. You can enable it later in Settings.</p>
          </div>
        )}
      </div>
    </div>
  );
};

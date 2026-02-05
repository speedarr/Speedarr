/**
 * SummaryStep - Review configuration and complete setup
 */

import React from 'react';
import { Button } from '@/components/ui/button';
import { CheckCircle, Server, Download, Gauge, Activity, Bell, Edit2 } from 'lucide-react';
import { WizardStepProps, WizardState } from '../types';
import { useWizard } from '../WizardContext';
import { getStepIndex } from '../wizardConfig';

export const SummaryStep: React.FC<WizardStepProps> = ({
  data,
}) => {
  const { goToStep } = useWizard();
  const state = data as WizardState;

  const editStep = (stepId: string) => {
    const index = getStepIndex(stepId);
    if (index >= 0) {
      goToStep(index);
    }
  };

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <div className="flex justify-center">
          <div className="h-16 w-16 rounded-full bg-green-100 dark:bg-green-900/30 flex items-center justify-center">
            <CheckCircle className="h-8 w-8 text-green-600 dark:text-green-400" />
          </div>
        </div>
        <h2 className="text-xl font-semibold">Ready to Go!</h2>
        <p className="text-sm text-muted-foreground">
          Review your configuration below, then click "Complete Setup" to start Speedarr.
        </p>
      </div>

      <div className="space-y-4 max-w-lg mx-auto">
        {/* Plex */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Server className="h-4 w-4 text-primary" />
              <h3 className="font-medium">Plex</h3>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => editStep('plex')}
              className="h-8 px-2"
            >
              <Edit2 className="h-3 w-3 mr-1" />
              Edit
            </Button>
          </div>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Server URL</span>
              <span className="font-mono text-xs">{state.plex?.url || 'Not set'}</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Token</span>
              <span>{state.plex?.token ? '••••••••' : 'Not set'}</span>
            </div>
          </div>
        </div>

        {/* Download Clients */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Download className="h-4 w-4 text-primary" />
              <h3 className="font-medium">Download Clients</h3>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => editStep('download-clients')}
              className="h-8 px-2"
            >
              <Edit2 className="h-3 w-3 mr-1" />
              Edit
            </Button>
          </div>
          <div className="space-y-2">
            {state.downloadClients && state.downloadClients.length > 0 ? (
              state.downloadClients.map(client => (
                <div key={client.id} className="flex items-center gap-2 text-sm">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: client.color }}
                  />
                  <span>{client.name}</span>
                  <span className={`text-xs ml-auto ${client.enabled ? 'text-green-600' : 'text-muted-foreground'}`}>
                    {client.enabled ? 'Enabled' : 'Disabled'}
                  </span>
                </div>
              ))
            ) : (
              <p className="text-sm text-muted-foreground">No clients configured</p>
            )}
          </div>
        </div>

        {/* Bandwidth */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Gauge className="h-4 w-4 text-primary" />
              <h3 className="font-medium">Bandwidth Limits</h3>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => editStep('bandwidth')}
              className="h-8 px-2"
            >
              <Edit2 className="h-3 w-3 mr-1" />
              Edit
            </Button>
          </div>
          <div className="space-y-1 text-sm">
            <div className="flex justify-between">
              <span className="text-muted-foreground">Download Limit</span>
              <span>{state.bandwidth?.download.total_limit || 0} Mbps</span>
            </div>
            <div className="flex justify-between">
              <span className="text-muted-foreground">Upload Limit</span>
              <span>{state.bandwidth?.upload.total_limit || 0} Mbps</span>
            </div>
          </div>
        </div>

        {/* SNMP */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Activity className="h-4 w-4 text-primary" />
              <h3 className="font-medium">SNMP Monitoring</h3>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => editStep('snmp')}
              className="h-8 px-2"
            >
              <Edit2 className="h-3 w-3 mr-1" />
              Edit
            </Button>
          </div>
          <div className="text-sm">
            {state.snmp?.enabled ? (
              <div className="space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Status</span>
                  <span className="text-green-600">Enabled</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Host</span>
                  <span className="font-mono text-xs">{state.snmp.host || 'Not set'}</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Version</span>
                  <span>{state.snmp.version || 'v2c'}</span>
                </div>
              </div>
            ) : (
              <p className="text-muted-foreground">SNMP monitoring disabled</p>
            )}
          </div>
        </div>

        {/* Notifications */}
        <div className="border rounded-lg p-4">
          <div className="flex items-center justify-between mb-3">
            <div className="flex items-center gap-2">
              <Bell className="h-4 w-4 text-primary" />
              <h3 className="font-medium">Notifications</h3>
            </div>
            <Button
              variant="ghost"
              size="sm"
              onClick={() => editStep('notifications')}
              className="h-8 px-2"
            >
              <Edit2 className="h-3 w-3 mr-1" />
              Edit
            </Button>
          </div>
          <div className="text-sm">
            {state.notifications?.discord?.enabled ? (
              <div className="space-y-1">
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Discord</span>
                  <span className="text-green-600">Enabled</span>
                </div>
                <div className="flex justify-between">
                  <span className="text-muted-foreground">Webhook</span>
                  <span>{state.notifications.discord.webhook_url ? 'Configured' : 'Not set'}</span>
                </div>
              </div>
            ) : (
              <p className="text-muted-foreground">Notifications disabled</p>
            )}
          </div>
        </div>
      </div>

      <div className="text-center pt-4">
        <p className="text-sm text-muted-foreground">
          Click <strong>Complete Setup</strong> below to save your configuration and start monitoring.
        </p>
      </div>
    </div>
  );
};

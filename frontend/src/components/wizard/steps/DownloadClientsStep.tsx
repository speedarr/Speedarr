/**
 * DownloadClientsStep - Configure at least one download client
 */

import React, { useState, useEffect } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, CheckCircle, XCircle, Trash2 } from 'lucide-react';
import { PasswordInput } from '@/components/settings/PasswordInput';
import { apiClient } from '@/api/client';
import { WizardStepProps, DownloadClientConfig } from '../types';

// Client type definitions
const CLIENT_TYPES = {
  qbittorrent: {
    name: 'qBittorrent',
    color: '#3b82f6',
    supportsUpload: true,
    authType: 'username_password',
    defaultUrl: 'http://qbittorrent:8080',
    apiKeyLocation: null,
  },
  sabnzbd: {
    name: 'SABnzbd',
    color: '#facc15',
    supportsUpload: false,
    authType: 'api_key',
    defaultUrl: 'http://sabnzbd:8080',
    apiKeyLocation: 'Config → General → Security → API Key',
  },
  nzbget: {
    name: 'NZBGet',
    color: '#22c55e',
    supportsUpload: false,
    authType: 'username_password',
    defaultUrl: 'http://nzbget:6789',
    apiKeyLocation: null,
  },
  transmission: {
    name: 'Transmission',
    color: '#ef4444',
    supportsUpload: true,
    authType: 'username_password',
    defaultUrl: 'http://transmission:9091',
    apiKeyLocation: null,
  },
  deluge: {
    name: 'Deluge',
    color: '#8b5cf6',
    supportsUpload: true,
    authType: 'password',
    defaultUrl: 'http://deluge:8112',
    apiKeyLocation: null,
  },
} as const;

type ClientType = keyof typeof CLIENT_TYPES;

export const DownloadClientsStep: React.FC<WizardStepProps> = ({
  data,
  onDataChange,
  showValidation,
  isLoading,
  readOnly,
}) => {
  const [clients, setClients] = useState<DownloadClientConfig[]>(() => data || []);
  const [testResults, setTestResults] = useState<Record<string, boolean | null>>({});
  const [testingClient, setTestingClient] = useState<string | null>(null);

  // Update parent when clients change
  useEffect(() => {
    onDataChange(clients);
  }, [clients, onDataChange]);

  const addClient = (type: ClientType) => {
    const typeInfo = CLIENT_TYPES[type];
    const newClient: DownloadClientConfig = {
      id: `${type}_${Date.now()}`,
      type,
      name: typeInfo.name,
      enabled: true,
      url: typeInfo.defaultUrl,
      username: '',
      password: '',
      api_key: '',
      color: typeInfo.color,
      supports_upload: typeInfo.supportsUpload,
    };
    setClients(prev => [...prev, newClient]);
  };

  const updateClient = (clientId: string, field: keyof DownloadClientConfig, value: any) => {
    setClients(prev => prev.map(c =>
      c.id === clientId ? { ...c, [field]: value } : c
    ));
    // Clear test result when config changes
    setTestResults(prev => ({ ...prev, [clientId]: null }));
  };

  const removeClient = (clientId: string) => {
    setClients(prev => prev.filter(c => c.id !== clientId));
    setTestResults(prev => {
      const newResults = { ...prev };
      delete newResults[clientId];
      return newResults;
    });
  };

  const testConnection = async (client: DownloadClientConfig) => {
    setTestingClient(client.id);
    try {
      const typeInfo = CLIENT_TYPES[client.type as ClientType];
      const config = typeInfo.authType === 'api_key'
        ? { url: client.url, api_key: client.api_key }
        : typeInfo.authType === 'password'
        ? { url: client.url, password: client.password }
        : { url: client.url, username: client.username, password: client.password };

      const response = await apiClient.testConnection(client.type, config, false);
      setTestResults(prev => ({ ...prev, [client.id]: response.success }));
    } catch {
      setTestResults(prev => ({ ...prev, [client.id]: false }));
    } finally {
      setTestingClient(null);
    }
  };

  const enabledClients = clients.filter(c => c.enabled);
  const hasValidClient = enabledClients.length > 0;

  if (readOnly) {
    return (
      <div className="space-y-4">
        <h3 className="font-medium">Download Clients</h3>
        {clients.length === 0 ? (
          <p className="text-sm text-muted-foreground">No clients configured</p>
        ) : (
          <div className="space-y-2">
            {clients.map(client => (
              <div key={client.id} className="flex items-center gap-3 py-2 border-b">
                <div
                  className="w-3 h-3 rounded-full"
                  style={{ backgroundColor: client.color }}
                />
                <span className="flex-1">{client.name}</span>
                <span className={client.enabled ? 'text-green-600' : 'text-muted-foreground'}>
                  {client.enabled ? 'Enabled' : 'Disabled'}
                </span>
              </div>
            ))}
          </div>
        )}
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-xl font-semibold">Add Download Client</h2>
        <p className="text-sm text-muted-foreground">
          Add at least one download client for Speedarr to manage bandwidth.
        </p>
      </div>

      {/* Validation warning */}
      {showValidation && !hasValidClient && (
        <Alert variant="destructive">
          <AlertDescription>
            At least one download client must be configured and enabled.
          </AlertDescription>
        </Alert>
      )}

      {/* Client list */}
      <div className="space-y-4">
        {clients.map(client => {
          const typeInfo = CLIENT_TYPES[client.type as ClientType];
          const testResult = testResults[client.id];
          const isTesting = testingClient === client.id;

          return (
            <div key={client.id} className="border rounded-lg p-4 space-y-4">
              {/* Header */}
              <div className="flex items-center justify-between">
                <div className="flex items-center gap-3">
                  <div
                    className="w-3 h-3 rounded-full"
                    style={{ backgroundColor: client.color }}
                  />
                  <span className="font-medium">{typeInfo.name}</span>
                  {testResult === true && (
                    <span className="flex items-center">
                      <CheckCircle className="h-4 w-4 text-green-500" aria-hidden="true" />
                      <span className="sr-only">Connection successful</span>
                    </span>
                  )}
                  {testResult === false && (
                    <span className="flex items-center">
                      <XCircle className="h-4 w-4 text-red-500" aria-hidden="true" />
                      <span className="sr-only">Connection failed</span>
                    </span>
                  )}
                </div>
                <div className="flex items-center gap-3">
                  <Switch
                    checked={client.enabled}
                    onCheckedChange={(checked) => updateClient(client.id, 'enabled', checked)}
                    disabled={isLoading}
                  />
                  <Button
                    variant="ghost"
                    size="sm"
                    onClick={() => removeClient(client.id)}
                    disabled={isLoading}
                  >
                    <Trash2 className="h-4 w-4 text-destructive" />
                  </Button>
                </div>
              </div>

              {/* Fields */}
              <div className="grid gap-3">
                <div className="space-y-1">
                  <Label className="text-sm">Server URL</Label>
                  <Input
                    value={client.url}
                    onChange={(e) => updateClient(client.id, 'url', e.target.value)}
                    placeholder={typeInfo.defaultUrl}
                    disabled={isLoading}
                    maxLength={512}
                  />
                </div>

                {typeInfo.authType === 'api_key' ? (
                  <div className="space-y-1">
                    <Label className="text-sm">API Key</Label>
                    <PasswordInput
                      value={client.api_key || ''}
                      onChange={(e) => updateClient(client.id, 'api_key', e.target.value)}
                      placeholder="Enter API key"
                      disabled={isLoading}
                      maxLength={128}
                    />
                    {typeInfo.apiKeyLocation && (
                      <p className="text-xs text-muted-foreground">
                        Find at: {typeInfo.apiKeyLocation}
                      </p>
                    )}
                  </div>
                ) : typeInfo.authType === 'password' ? (
                  <div className="space-y-1">
                    <Label className="text-sm">Password</Label>
                    <PasswordInput
                      value={client.password || ''}
                      onChange={(e) => updateClient(client.id, 'password', e.target.value)}
                      placeholder="Enter password"
                      disabled={isLoading}
                      maxLength={128}
                    />
                  </div>
                ) : (
                  <>
                    <div className="space-y-1">
                      <Label className="text-sm">Username</Label>
                      <Input
                        value={client.username || ''}
                        onChange={(e) => updateClient(client.id, 'username', e.target.value)}
                        placeholder="Enter username"
                        disabled={isLoading}
                        maxLength={50}
                      />
                    </div>
                    <div className="space-y-1">
                      <Label className="text-sm">Password</Label>
                      <PasswordInput
                        value={client.password || ''}
                        onChange={(e) => updateClient(client.id, 'password', e.target.value)}
                        placeholder="Enter password"
                        disabled={isLoading}
                        maxLength={128}
                      />
                    </div>
                  </>
                )}

                {/* Test button */}
                <Button
                  type="button"
                  variant="outline"
                  size="sm"
                  onClick={() => testConnection(client)}
                  disabled={isLoading || isTesting || !client.url}
                  className="w-fit"
                >
                  {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Test Connection
                </Button>
              </div>
            </div>
          );
        })}
      </div>

      {/* Add client dropdown */}
      <div className="flex items-center gap-2">
        <Select onValueChange={(value) => addClient(value as ClientType)}>
          <SelectTrigger className="w-full sm:w-64">
            <SelectValue placeholder="Add download client..." />
          </SelectTrigger>
          <SelectContent>
            {(Object.entries(CLIENT_TYPES) as [ClientType, typeof CLIENT_TYPES[ClientType]][]).map(([type, info]) => (
              <SelectItem key={type} value={type}>
                <div className="flex items-center gap-2">
                  <div
                    className="w-2 h-2 rounded-full"
                    style={{ backgroundColor: info.color }}
                  />
                  {info.name}
                </div>
              </SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {clients.length === 0 && (
        <p className="text-sm text-muted-foreground text-center">
          Select a download client from the dropdown above to get started.
        </p>
      )}
    </div>
  );
};

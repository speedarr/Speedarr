import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle, ChevronDown, ChevronUp, Plus, Trash2, XCircle } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { PasswordInput } from './PasswordInput';
import { TestConnectionButton } from './TestConnectionButton';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

// Client type definitions
const CLIENT_TYPES = {
  qbittorrent: {
    name: 'qBittorrent',
    color: '#3b82f6',
    supportsUpload: true,
    authType: 'username_password',
    fields: ['url', 'username', 'password'],
    defaultUrl: 'http://qbittorrent:8080',
    apiKeyLocation: null,
  },
  sabnzbd: {
    name: 'SABnzbd',
    color: '#facc15',
    supportsUpload: false,
    authType: 'api_key',
    fields: ['url', 'api_key'],
    defaultUrl: 'http://sabnzbd:8080',
    apiKeyLocation: 'Config → General → Security → API Key',
  },
  nzbget: {
    name: 'NZBGet',
    color: '#22c55e',
    supportsUpload: false,
    authType: 'username_password',
    fields: ['url', 'username', 'password'],
    defaultUrl: 'http://nzbget:6789',
    apiKeyLocation: null,
  },
  transmission: {
    name: 'Transmission',
    color: '#ef4444',
    supportsUpload: true,
    authType: 'username_password',
    fields: ['url', 'username', 'password'],
    defaultUrl: 'http://transmission:9091',
    apiKeyLocation: null,
  },
  deluge: {
    name: 'Deluge',
    color: '#8b5cf6',
    supportsUpload: true,
    authType: 'password',
    fields: ['url', 'password'],
    defaultUrl: 'http://deluge:8112',
    apiKeyLocation: null,
  },
};

interface DownloadClient {
  id: string;
  type: string;
  name: string;
  enabled: boolean;
  url: string;
  username?: string;
  password?: string;
  api_key?: string;
  color: string;
  supports_upload: boolean;
}

interface DownloadClientCardProps {
  client: DownloadClient;
  onUpdate: (client: DownloadClient) => void;
  onDelete: (clientId: string) => void;
  isSaving: boolean;
  connectionStatus?: boolean | null; // true = connected, false = failed, null = not tested
  defaultOpen?: boolean;
}

const DownloadClientCard: React.FC<DownloadClientCardProps> = ({
  client,
  onUpdate,
  onDelete,
  isSaving,
  connectionStatus,
  defaultOpen = false,
}) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const typeInfo = CLIENT_TYPES[client.type as keyof typeof CLIENT_TYPES];

  const updateField = (field: keyof DownloadClient, value: any) => {
    onUpdate({ ...client, [field]: value });
  };

  return (
    <Card>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CardHeader className="py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div
                className="w-3 h-3 rounded-full flex-shrink-0"
                style={{ backgroundColor: client.color || typeInfo?.color }}
              />
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-lg leading-none">{client.name}</CardTitle>
                  {connectionStatus === true && (
                    <span className="flex items-center gap-1">
                      <CheckCircle className="h-4 w-4 text-green-500" aria-hidden="true" />
                      <span className="sr-only">Connected</span>
                    </span>
                  )}
                  {connectionStatus === false && (
                    <XCircle className="h-4 w-4 text-red-500" aria-hidden="true" />
                  )}
                </div>
                <div className="flex items-center gap-2">
                  <CardDescription className="leading-tight">{typeInfo?.name || client.type}</CardDescription>
                  {connectionStatus === false && (
                    <span className="text-xs text-red-500">Connection failed</span>
                  )}
                </div>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Switch
                checked={client.enabled}
                onCheckedChange={(checked) => updateField('enabled', checked)}
                disabled={isSaving}
              />
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm">
                  {isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}
                </Button>
              </CollapsibleTrigger>
            </div>
          </div>
        </CardHeader>

        <CollapsibleContent>
          <CardContent className="space-y-4 pt-0">
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input
                value={client.name}
                onChange={(e) => updateField('name', e.target.value)}
                disabled={isSaving || !client.enabled}
                maxLength={100}
              />
            </div>

            <div className="space-y-2">
              <Label>Server URL</Label>
              <Input
                type="url"
                value={client.url}
                onChange={(e) => updateField('url', e.target.value)}
                placeholder={`http://${client.type}.local:8080`}
                disabled={isSaving || !client.enabled}
                maxLength={512}
              />
            </div>

            {/* Username/Password fields */}
            {typeInfo?.authType === 'username_password' && (
              <>
                <div className="space-y-2">
                  <Label>Username</Label>
                  <Input
                    value={client.username || ''}
                    onChange={(e) => updateField('username', e.target.value)}
                    disabled={isSaving || !client.enabled}
                    maxLength={50}
                  />
                </div>
                <div className="space-y-2">
                  <Label>Password</Label>
                  <PasswordInput
                    value={client.password === '***REDACTED***' ? '' : (client.password || '')}
                    onChange={(e) => updateField('password', e.target.value)}
                    placeholder={client.password === '***REDACTED***' ? 'Current password is set' : 'Enter password'}
                    disabled={isSaving || !client.enabled}
                    maxLength={128}
                  />
                </div>
              </>
            )}

            {/* API Key field */}
            {typeInfo?.authType === 'api_key' && (
              <div className="space-y-2">
                <div className="flex items-center gap-2">
                  <Label>API Key</Label>
                  {typeInfo?.apiKeyLocation && (
                    <span className="text-xs text-muted-foreground">
                      (Find at: {typeInfo.apiKeyLocation})
                    </span>
                  )}
                </div>
                <PasswordInput
                  value={client.api_key === '***REDACTED***' ? '' : (client.api_key || '')}
                  onChange={(e) => updateField('api_key', e.target.value)}
                  placeholder={client.api_key === '***REDACTED***' ? 'Current API key is set' : 'Enter API key'}
                  disabled={isSaving || !client.enabled}
                  maxLength={128}
                />
              </div>
            )}

            {/* Password only (Deluge) */}
            {typeInfo?.authType === 'password' && (
              <div className="space-y-2">
                <Label>Password</Label>
                <PasswordInput
                  value={client.password === '***REDACTED***' ? '' : (client.password || '')}
                  onChange={(e) => updateField('password', e.target.value)}
                  placeholder={client.password === '***REDACTED***' ? 'Current password is set' : 'Enter password'}
                  disabled={isSaving || !client.enabled}
                  maxLength={128}
                />
              </div>
            )}

            <div className="flex items-center justify-between pt-4">
              <Button
                variant="destructive"
                size="sm"
                onClick={() => onDelete(client.id)}
                disabled={isSaving}
              >
                <Trash2 className="h-4 w-4 mr-2" />
                Remove Client
              </Button>

              {client.enabled && (
                <TestConnectionButton
                  service={client.type}
                  config={client}
                  disabled={isSaving || !client.url}
                  useExisting={
                    (client.api_key === '***REDACTED***') ||
                    (client.password === '***REDACTED***')
                  }
                />
              )}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
};

export const DownloadClientsSettings: React.FC = () => {
  const [clients, setClients] = useState<DownloadClient[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [connectionResults, setConnectionResults] = useState<Record<string, boolean>>({});
  const [newlyAddedClientId, setNewlyAddedClientId] = useState<string | null>(null);
  const newClientRef = useRef<HTMLDivElement>(null);
  const saveButtonRef = useRef<HTMLButtonElement>(null);

  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<DownloadClient[]>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(clients);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'services-download',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setClients(original);
      }
    );
    return () => unregisterTab('services-download');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadClients();
  }, []);

  // Scroll to newly added client
  useEffect(() => {
    if (newlyAddedClientId && newClientRef.current) {
      newClientRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' });
    }
  }, [newlyAddedClientId]);

  const loadClients = async () => {
    try {
      const response = await apiClient.getDownloadClients();
      setClients(response.clients || []);
      resetOriginal(response.clients || []);
      setError('');
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsLoading(false);
    }
  };

  const handleSave = async () => {
    setIsSaving(true);
    setError('');
    setSuccess('');
    setConnectionResults({});

    try {
      const response = await apiClient.updateDownloadClients(clients);

      // Store connection results to display icons on cards
      const results = response.connection_results || {};
      setConnectionResults(results);

      const testedClients = Object.keys(results);
      if (testedClients.length > 0) {
        const passed = testedClients.filter(c => results[c]);
        const failed = testedClients.filter(c => !results[c]);

        if (failed.length === 0) {
          setSuccess(`Saved successfully. All ${passed.length} client(s) connected.`);
        } else if (passed.length === 0) {
          setError(`Saved, but all ${failed.length} client(s) failed to connect.`);
        } else {
          setSuccess(`Saved. ${passed.length} client(s) connected.`);
          setError(`${failed.length} client(s) failed to connect.`);
        }
      } else {
        setSuccess('Download clients saved successfully');
      }

      setTimeout(() => {
        setSuccess('');
        setError('');
      }, 5000);

      // Reload to get updated data
      await loadClients();
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const handleUpdateClient = (updatedClient: DownloadClient) => {
    setClients(clients.map(c => c.id === updatedClient.id ? updatedClient : c));
  };

  const handleDeleteClient = (clientId: string) => {
    setClients(clients.filter(c => c.id !== clientId));
  };

  const handleAddClient = (type: string) => {
    const typeInfo = CLIENT_TYPES[type as keyof typeof CLIENT_TYPES];
    const existingCount = clients.filter(c => c.type === type).length;
    const clientId = `${type}_${Date.now()}`;
    const newClient: DownloadClient = {
      id: clientId,
      type,
      name: existingCount > 0 ? `${typeInfo.name} ${existingCount + 1}` : typeInfo.name,
      enabled: true,
      url: typeInfo.defaultUrl,
      color: typeInfo.color,
      supports_upload: typeInfo.supportsUpload,
    };

    setClients([...clients, newClient]);
    setNewlyAddedClientId(clientId);
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

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Download Clients</CardTitle>
              <CardDescription>
                Configure your download clients for bandwidth management
              </CardDescription>
            </div>
            <Select onValueChange={handleAddClient}>
              <SelectTrigger className="w-[200px]">
                <Plus className="h-4 w-4 mr-2" />
                <SelectValue placeholder="Add Client" />
              </SelectTrigger>
              <SelectContent>
                {Object.entries(CLIENT_TYPES).map(([type, info]) => (
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
        </CardHeader>
        <CardContent>
          {error && (
            <Alert variant="destructive" className="mb-4">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>{error}</AlertDescription>
            </Alert>
          )}

          {success && (
            <Alert className="mb-4">
              <CheckCircle className="h-4 w-4" />
              <AlertDescription>{success}</AlertDescription>
            </Alert>
          )}

          {clients.length === 0 ? (
            <div className="text-center p-8 text-muted-foreground">
              No download clients configured. Click "Add Client" to add one.
            </div>
          ) : (
            <p className="text-sm text-muted-foreground">
              {clients.filter(c => c.enabled).length} of {clients.length} client(s) enabled
            </p>
          )}
        </CardContent>
      </Card>

      {clients.map((client) => (
        <div
          key={client.id}
          ref={client.id === newlyAddedClientId ? newClientRef : null}
        >
          <DownloadClientCard
            client={client}
            onUpdate={handleUpdateClient}
            onDelete={handleDeleteClient}
            isSaving={isSaving}
            connectionStatus={
              client.enabled && client.type in connectionResults
                ? connectionResults[client.type]
                : null
            }
            defaultOpen={client.id === newlyAddedClientId}
          />
        </div>
      ))}

      {clients.length > 0 && (
        <div className="flex justify-end">
          <Button
            ref={saveButtonRef}
            onClick={handleSave}
            disabled={isSaving}
            className={isDirty ? 'ring-2 ring-orange-500 ring-offset-2' : ''}
          >
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
            Save All Changes
          </Button>
        </div>
      )}
    </div>
  );
};

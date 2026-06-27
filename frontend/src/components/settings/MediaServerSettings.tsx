import React, { useState, useEffect, useRef } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, AlertCircle, CheckCircle, ChevronDown, ChevronUp, Plus, Trash2, XCircle, ExternalLink } from 'lucide-react';
import { Switch } from '@/components/ui/switch';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Collapsible, CollapsibleContent, CollapsibleTrigger } from '@/components/ui/collapsible';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import { PasswordInput } from './PasswordInput';
import { TestConnectionButton } from './TestConnectionButton';
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';
import { MediaServer } from '@/types';
import { Badge } from '@/components/ui/badge';
import { FEEDBACK_URL } from '@/lib/constants';

// Plex, Emby, and Jellyfin are user-selectable. Emby/Jellyfin are experimental.
// `help` is a link (Plex) OR plain instruction text (Emby/Jellyfin — no reliable doc URL).
type ServerTypeInfo = {
  name: string;
  color: string;
  auth: 'token' | 'api_key';
  defaultUrl: string;
  experimental?: boolean;
  help: { label: string; url: string } | { text: string };
};

const SERVER_TYPES: Record<'plex' | 'emby' | 'jellyfin', ServerTypeInfo> = {
  plex: {
    name: 'Plex',
    color: '#e5a00d',
    auth: 'token',
    defaultUrl: 'http://192.168.1.100:32400',
    help: { label: 'How to find your X-Plex-Token', url: 'https://support.plex.tv/articles/204059436-finding-an-authentication-token-x-plex-token/' },
  },
  emby: {
    name: 'Emby',
    color: '#52b54b',
    auth: 'api_key',
    defaultUrl: 'http://192.168.1.100:8096',
    experimental: true,
    help: { text: 'Create one in Emby: Dashboard → Advanced → API Keys' },
  },
  jellyfin: {
    name: 'Jellyfin',
    color: '#00A4DC',
    auth: 'api_key',
    defaultUrl: 'http://192.168.1.100:8096',
    experimental: true,
    help: { text: 'Create one in Jellyfin: Dashboard → Advanced → API Keys' },
  },
};

const MediaServerCard: React.FC<{
  server: MediaServer;
  onUpdate: (s: MediaServer) => void;
  onDelete: (id: string) => void;
  isSaving: boolean;
  connectionStatus?: boolean | null;
  defaultOpen?: boolean;
}> = ({ server, onUpdate, onDelete, isSaving, connectionStatus, defaultOpen = false }) => {
  const [isOpen, setIsOpen] = useState(defaultOpen);
  const typeInfo = SERVER_TYPES[server.type as keyof typeof SERVER_TYPES];
  const update = (field: keyof MediaServer, value: any) => onUpdate({ ...server, [field]: value });

  // Plex renders a clickable help link; Emby/Jellyfin render plain instruction text.
  const helpNode = typeInfo?.help ? (
    'url' in typeInfo.help ? (
      <p className="text-sm text-muted-foreground flex items-center gap-1">
        <a href={typeInfo.help.url} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline inline-flex items-center">
          {typeInfo.help.label} <ExternalLink className="h-3 w-3 ml-1" />
        </a>
      </p>
    ) : (
      <p className="text-sm text-muted-foreground">{typeInfo.help.text}</p>
    )
  ) : null;

  return (
    <Card>
      <Collapsible open={isOpen} onOpenChange={setIsOpen}>
        <CardHeader className="py-3">
          <div className="flex items-center justify-between">
            <div className="flex items-center gap-3">
              <div className="w-3 h-3 rounded-full flex-shrink-0" style={{ backgroundColor: typeInfo?.color }} />
              <div className="flex flex-col">
                <div className="flex items-center gap-2">
                  <CardTitle className="text-lg leading-none">{server.name}</CardTitle>
                  {typeInfo?.experimental && <Badge variant="outline">Experimental</Badge>}
                  {connectionStatus === true && <CheckCircle className="h-4 w-4 text-green-500" aria-hidden="true" />}
                  {connectionStatus === false && <XCircle className="h-4 w-4 text-red-500" aria-hidden="true" />}
                </div>
                <CardDescription className="leading-tight">{typeInfo?.name || server.type}</CardDescription>
              </div>
            </div>
            <div className="flex items-center gap-4">
              <Switch checked={server.enabled} onCheckedChange={(c) => update('enabled', c)} disabled={isSaving} />
              <CollapsibleTrigger asChild>
                <Button variant="ghost" size="sm">{isOpen ? <ChevronUp className="h-4 w-4" /> : <ChevronDown className="h-4 w-4" />}</Button>
              </CollapsibleTrigger>
            </div>
          </div>
        </CardHeader>
        <CollapsibleContent>
          <CardContent className="space-y-4 pt-0">
            <div className="space-y-2">
              <Label>Display Name</Label>
              <Input value={server.name} onChange={(e) => update('name', e.target.value)} disabled={isSaving || !server.enabled} maxLength={100} />
            </div>
            <div className="space-y-2">
              <Label>Server URL</Label>
              <Input type="url" value={server.url} onChange={(e) => update('url', e.target.value)} placeholder={typeInfo?.defaultUrl} disabled={isSaving || !server.enabled} maxLength={512} />
            </div>
            {typeInfo?.auth === 'token' && (
              <div className="space-y-2">
                <Label>X-Plex-Token</Label>
                <PasswordInput
                  value={server.token === '***REDACTED***' ? '' : (server.token || '')}
                  onChange={(e) => update('token', e.target.value)}
                  placeholder={server.token === '***REDACTED***' ? 'Current token is set' : 'Enter X-Plex-Token'}
                  disabled={isSaving || !server.enabled} maxLength={128}
                />
                {helpNode}
              </div>
            )}
            {typeInfo?.auth === 'api_key' && (
              <div className="space-y-2">
                <Label>API Key</Label>
                <PasswordInput
                  value={server.api_key === '***REDACTED***' ? '' : (server.api_key || '')}
                  onChange={(e) => update('api_key', e.target.value)}
                  placeholder={server.api_key === '***REDACTED***' ? 'Current API key is set' : 'Enter API key'}
                  disabled={isSaving || !server.enabled} maxLength={128}
                />
                {helpNode}
              </div>
            )}
            {typeInfo?.experimental && (
              <p className="text-sm text-muted-foreground flex items-center gap-1">
                {typeInfo.name} support is experimental —{' '}
                <a href={FEEDBACK_URL} target="_blank" rel="noopener noreferrer" className="text-primary hover:underline inline-flex items-center">
                  we'd love your feedback <ExternalLink className="h-3 w-3 ml-1" />
                </a>
              </p>
            )}
            <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
              <div className="space-y-0.5">
                <Label>Include LAN Streams in Bandwidth</Label>
                <p className="text-sm text-muted-foreground">Count this server's LAN streams in bandwidth calculations. When off, only its WAN streams affect limits.</p>
              </div>
              <Switch checked={server.include_lan_streams || false} onCheckedChange={(c) => update('include_lan_streams', c)} disabled={isSaving || !server.enabled} />
            </div>
            <div className="flex items-center justify-between pt-4">
              <Button variant="destructive" size="sm" onClick={() => onDelete(server.id)} disabled={isSaving}>
                <Trash2 className="h-4 w-4 mr-2" /> Remove Server
              </Button>
              {server.enabled && (
                <TestConnectionButton
                  service={server.type}
                  config={server}
                  disabled={isSaving || !server.url}
                  useExisting={(server.token === '***REDACTED***') || (server.api_key === '***REDACTED***')}
                />
              )}
            </div>
          </CardContent>
        </CollapsibleContent>
      </Collapsible>
    </Card>
  );
};

export const MediaServerSettings: React.FC = () => {
  const [servers, setServers] = useState<MediaServer[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [connectionResults, setConnectionResults] = useState<Record<string, boolean>>({});
  const [newlyAddedId, setNewlyAddedId] = useState<string | null>(null);
  const newRef = useRef<HTMLDivElement>(null);
  const saveButtonRef = useRef<HTMLButtonElement>(null);

  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<MediaServer[]>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();
  const isDirty = hasUnsavedChanges(servers);

  useEffect(() => {
    registerTab('services-media', isDirty, saveButtonRef,
      async () => { await handleSave(); },
      () => { const o = discardChanges(); if (o) setServers(o); });
    return () => unregisterTab('services-media');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => { load(); }, []);
  useEffect(() => { if (newlyAddedId && newRef.current) newRef.current.scrollIntoView({ behavior: 'smooth', block: 'center' }); }, [newlyAddedId]);

  const load = async () => {
    try {
      const res = await apiClient.getMediaServers();
      setServers(res.servers || []);
      resetOriginal(res.servers || []);
      setError('');
    } catch (e: unknown) { setError(getErrorMessage(e)); }
    finally { setIsLoading(false); }
  };

  const handleSave = async () => {
    setIsSaving(true); setError(''); setSuccess(''); setConnectionResults({});
    try {
      const res = await apiClient.updateMediaServers(servers);
      setConnectionResults(res.connection_results || {});
      setSuccess('Media servers saved successfully');
      setTimeout(() => { setSuccess(''); setError(''); }, 5000);
      await load();
    } catch (e: unknown) { setError(getErrorMessage(e)); }
    finally { setIsSaving(false); }
  };

  const handleAdd = (type: string) => {
    const info = SERVER_TYPES[type as keyof typeof SERVER_TYPES];
    const count = servers.filter(s => s.type === type).length;
    const id = `${type}_${Date.now()}`;
    setServers([...servers, {
      id, type: type as MediaServer['type'],
      name: count > 0 ? `${info.name} ${count + 1}` : info.name,
      enabled: true, url: info.defaultUrl, token: '', api_key: '', include_lan_streams: false,
    }]);
    setNewlyAddedId(id);
  };

  if (isLoading) {
    return <Card><CardContent className="flex justify-center items-center p-8"><Loader2 className="h-8 w-8 animate-spin text-muted-foreground" /></CardContent></Card>;
  }

  return (
    <div className="space-y-4">
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle>Media Servers</CardTitle>
              <CardDescription>Configure Plex, Emby, or Jellyfin servers for stream detection. All servers' streams combine into one bandwidth pool.</CardDescription>
            </div>
            <Select value="" onValueChange={handleAdd}>
              <SelectTrigger className="w-[200px]"><Plus className="h-4 w-4 mr-2" /><SelectValue placeholder="Add Media Server" /></SelectTrigger>
              <SelectContent>
                {Object.entries(SERVER_TYPES).map(([type, info]) => (
                  <SelectItem key={type} value={type}>
                    <div className="flex items-center gap-2"><div className="w-2 h-2 rounded-full" style={{ backgroundColor: info.color }} />{info.name}{info.experimental ? ' (Experimental)' : ''}</div>
                  </SelectItem>
                ))}
              </SelectContent>
            </Select>
          </div>
        </CardHeader>
        <CardContent>
          {error && <Alert variant="destructive" className="mb-4"><AlertCircle className="h-4 w-4" /><AlertDescription>{error}</AlertDescription></Alert>}
          {success && <Alert className="mb-4"><CheckCircle className="h-4 w-4" /><AlertDescription>{success}</AlertDescription></Alert>}
          {servers.length === 0 ? (
            <div className="text-center p-8 text-muted-foreground">No media servers configured. Click "Add Media Server" to add one.</div>
          ) : (
            <p className="text-sm text-muted-foreground">{servers.filter(s => s.enabled).length} of {servers.length} server(s) enabled</p>
          )}
        </CardContent>
      </Card>

      {servers.map((server) => (
        <div key={server.id} ref={server.id === newlyAddedId ? newRef : null}>
          <MediaServerCard
            server={server}
            onUpdate={(u) => setServers(servers.map(s => s.id === u.id ? u : s))}
            onDelete={(id) => setServers(servers.filter(s => s.id !== id))}
            isSaving={isSaving}
            connectionStatus={server.enabled && server.id in connectionResults ? connectionResults[server.id] : null}
            defaultOpen={server.id === newlyAddedId}
          />
        </div>
      ))}

      {servers.length > 0 && (
        <div className="flex justify-end">
          <Button ref={saveButtonRef} onClick={handleSave} disabled={isSaving} className={isDirty ? 'ring-2 ring-orange-500 ring-offset-2' : ''}>
            {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />} Save All Changes
          </Button>
        </div>
      )}
    </div>
  );
};

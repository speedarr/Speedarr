/**
 * MediaServerStep - Configure media server connections (Plex, Emby)
 *
 * Supports multiple servers; streams from all servers combine into one bandwidth pool.
 */

import React, { useState, useEffect } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Select, SelectContent, SelectItem, SelectTrigger, SelectValue } from '@/components/ui/select';
import { Loader2, CheckCircle, XCircle, Plus, Trash2 } from 'lucide-react';
import { PasswordInput } from '@/components/settings/PasswordInput';
import { apiClient } from '@/api/client';
import { WizardStepProps, MediaServerConfig } from '../types';

const TYPES = {
  plex: { name: 'Plex', authField: 'token' as const, authLabel: 'X-Plex-Token', defaultUrl: 'http://192.168.1.100:32400' },
  emby: { name: 'Emby', authField: 'api_key' as const, authLabel: 'API Key', defaultUrl: 'http://192.168.1.100:8096' },
  jellyfin: { name: 'Jellyfin', authField: 'api_key' as const, authLabel: 'API Key', defaultUrl: 'http://192.168.1.100:8096' },
};

export const MediaServerStep: React.FC<WizardStepProps> = ({ data, onDataChange, showValidation, isLoading }) => {
  const [servers, setServers] = useState<MediaServerConfig[]>(() => (data as MediaServerConfig[]) || []);
  const [tests, setTests] = useState<Record<string, { success: boolean; message: string } | 'loading'>>({});

  useEffect(() => { onDataChange(servers); }, [servers, onDataChange]);

  const add = (type: keyof typeof TYPES) => {
    const count = servers.filter(s => s.type === type).length;
    setServers(prev => [...prev, {
      id: `${type}_${Date.now()}`,
      type,
      name: count > 0 ? `${TYPES[type].name} ${count + 1}` : TYPES[type].name,
      enabled: true,
      url: TYPES[type].defaultUrl,
      token: '',
      api_key: '',
      include_lan_streams: false,
    }]);
  };

  const upd = (id: string, field: keyof MediaServerConfig, value: string | boolean) =>
    setServers(prev => prev.map(s => s.id === id ? { ...s, [field]: value } : s));

  const remove = (id: string) => {
    setServers(prev => prev.filter(s => s.id !== id));
    setTests(prev => {
      const next = { ...prev };
      delete next[id];
      return next;
    });
  };

  const test = async (s: MediaServerConfig) => {
    setTests(prev => ({ ...prev, [s.id]: 'loading' }));
    try {
      const r = await apiClient.testConnection(s.type, s, false);
      setTests(prev => ({ ...prev, [s.id]: { success: r.success, message: r.message } }));
    } catch (e: any) {
      setTests(prev => ({ ...prev, [s.id]: { success: false, message: e.response?.data?.detail || 'Connection test failed' } }));
    }
  };

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-xl font-semibold">Connect your media servers</h2>
        <p className="text-sm text-muted-foreground">
          Add one or more Plex or Emby servers. Their streams combine into one bandwidth pool.
        </p>
      </div>

      <div className="flex justify-center">
        <Select value="" onValueChange={(v) => add(v as keyof typeof TYPES)}>
          <SelectTrigger className="w-64">
            <div className="flex items-center">
              <Plus className="h-4 w-4 mr-2" />
              <SelectValue placeholder="Add media server" />
            </div>
          </SelectTrigger>
          <SelectContent>
            {Object.entries(TYPES).map(([t, i]) => (
              <SelectItem key={t} value={t}>{i.name}</SelectItem>
            ))}
          </SelectContent>
        </Select>
      </div>

      {showValidation && servers.length === 0 && (
        <Alert variant="destructive">
          <AlertDescription>Add at least one media server.</AlertDescription>
        </Alert>
      )}

      {servers.map(s => {
        const info = TYPES[s.type];
        const authValue = info.authField === 'token' ? s.token : s.api_key;
        const res = tests[s.id];

        return (
          <div key={s.id} className="space-y-3 rounded-lg border p-4">
            <div className="flex items-center justify-between">
              <div className="flex items-center gap-2">
                <span className="text-sm font-medium text-muted-foreground">{info.name}</span>
                <Input
                  value={s.name}
                  onChange={(e) => upd(s.id, 'name', e.target.value)}
                  className="max-w-[200px]"
                  maxLength={100}
                  disabled={isLoading}
                />
              </div>
              <Button
                variant="ghost"
                size="sm"
                onClick={() => remove(s.id)}
                disabled={isLoading}
              >
                <Trash2 className="h-4 w-4" />
              </Button>
            </div>

            <div className="space-y-2">
              <Label>Server URL</Label>
              <Input
                type="url"
                value={s.url}
                onChange={(e) => upd(s.id, 'url', e.target.value)}
                placeholder={info.defaultUrl}
                className={showValidation && !s.url ? 'border-destructive' : ''}
                disabled={isLoading}
                maxLength={512}
              />
            </div>

            <div className="space-y-2">
              <Label>{info.authLabel}</Label>
              <PasswordInput
                value={authValue || ''}
                onChange={(e) => upd(s.id, info.authField, e.target.value)}
                placeholder={`Enter ${info.authLabel}`}
                className={showValidation && !authValue ? 'border-destructive' : ''}
                disabled={isLoading}
                maxLength={128}
              />
            </div>

            <Button
              type="button"
              variant="outline"
              size="sm"
              onClick={() => test(s)}
              disabled={isLoading || res === 'loading' || !s.url || !authValue}
            >
              {res === 'loading' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Test Connection
            </Button>

            {res && res !== 'loading' && (
              <Alert
                variant={res.success ? 'default' : 'destructive'}
                className={res.success ? 'border-green-500' : ''}
              >
                {res.success ? (
                  <CheckCircle className="h-4 w-4 text-green-600" />
                ) : (
                  <XCircle className="h-4 w-4" />
                )}
                <AlertDescription className={res.success ? 'text-green-600 dark:text-green-400' : ''}>
                  {res.message}
                </AlertDescription>
              </Alert>
            )}
          </div>
        );
      })}
    </div>
  );
};

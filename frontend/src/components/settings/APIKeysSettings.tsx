import React, { useState, useEffect, useCallback } from 'react';
import { Card, CardContent, CardDescription, CardHeader, CardTitle } from '@/components/ui/card';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Badge } from '@/components/ui/badge';
import { Alert, AlertDescription } from '@/components/ui/alert';
import {
  Dialog,
  DialogContent,
  DialogDescription,
  DialogFooter,
  DialogHeader,
  DialogTitle,
} from '@/components/ui/dialog';
import {
  Table,
  TableBody,
  TableCell,
  TableHead,
  TableHeader,
  TableRow,
} from '@/components/ui/table';
import {
  Select,
  SelectContent,
  SelectItem,
  SelectTrigger,
  SelectValue,
} from '@/components/ui/select';
import { Loader2, AlertCircle, CheckCircle, Key, Plus, Trash2, Copy, Check, BookOpen } from 'lucide-react';
import { apiClient } from '@/api/client';
import { getErrorMessage } from '@/lib/utils';
import type { APIKeyInfo } from '@/types';

function copyToClipboard(text: string): void {
  if (navigator.clipboard?.writeText) {
    navigator.clipboard.writeText(text);
    return;
  }
  const textarea = document.createElement('textarea');
  textarea.value = text;
  textarea.style.position = 'fixed';
  textarea.style.opacity = '0';
  document.body.appendChild(textarea);
  textarea.select();
  document.execCommand('copy');
  document.body.removeChild(textarea);
}

const CopyableCode: React.FC<{ code: string }> = ({ code }) => {
  const [copied, setCopied] = useState(false);
  const handleCopy = () => {
    copyToClipboard(code);
    setCopied(true);
    setTimeout(() => setCopied(false), 2000);
  };
  return (
    <div className="relative group">
      <pre className="text-xs bg-muted p-3 rounded-md overflow-x-auto pr-10">{code}</pre>
      <Button
        variant="ghost"
        size="icon"
        className="absolute top-1.5 right-1.5 h-7 w-7 opacity-0 group-hover:opacity-100 transition-opacity"
        onClick={handleCopy}
      >
        {copied ? <Check className="h-3.5 w-3.5 text-green-600" /> : <Copy className="h-3.5 w-3.5" />}
      </Button>
    </div>
  );
};

export const APIKeysSettings: React.FC = () => {
  const [keys, setKeys] = useState<APIKeyInfo[]>([]);
  const [isLoading, setIsLoading] = useState(true);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');

  // Create dialog state
  const [isCreateOpen, setIsCreateOpen] = useState(false);
  const [newKeyName, setNewKeyName] = useState('');
  const [newKeyExpiry, setNewKeyExpiry] = useState<string>('never');
  const [isCreating, setIsCreating] = useState(false);

  // Token reveal dialog state
  const [revealedToken, setRevealedToken] = useState<string | null>(null);
  const [copied, setCopied] = useState(false);

  // Revoke state
  const [revokingId, setRevokingId] = useState<number | null>(null);

  // Per-row copy state
  const [copiedKeyId, setCopiedKeyId] = useState<number | null>(null);

  const fetchKeys = useCallback(async () => {
    try {
      const data = await apiClient.getAPIKeys();
      setKeys(data);
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsLoading(false);
    }
  }, []);

  useEffect(() => {
    fetchKeys();
  }, [fetchKeys]);

  const handleCreate = async () => {
    setIsCreating(true);
    setError('');
    try {
      const expiresInDays = newKeyExpiry === 'never' ? undefined : parseInt(newKeyExpiry, 10);
      const result = await apiClient.createAPIKey({
        name: newKeyName,
        expires_in_days: expiresInDays,
      });
      setRevealedToken(result.token);
      setIsCreateOpen(false);
      setNewKeyName('');
      setNewKeyExpiry('never');
      await fetchKeys();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setIsCreating(false);
    }
  };

  const handleRevoke = async (keyId: number) => {
    setRevokingId(keyId);
    setError('');
    try {
      await apiClient.revokeAPIKey(keyId);
      setSuccess('API key revoked');
      setTimeout(() => setSuccess(''), 3000);
      await fetchKeys();
    } catch (err) {
      setError(getErrorMessage(err));
    } finally {
      setRevokingId(null);
    }
  };

  const handleCopy = () => {
    if (revealedToken) {
      copyToClipboard(revealedToken);
      setCopied(true);
      setTimeout(() => setCopied(false), 2000);
    }
  };

  const speedarrUrl = window.location.origin;

  // Auto-fill API key when exactly one active key exists
  const activeKeys = keys.filter(k => k.is_active);
  const apiKeyValue = activeKeys.length === 1 ? activeKeys[0].token : 'YOUR_API_KEY';

  const restCommandYaml = `rest_command:
  speedarr_set_limits:
    url: "${speedarrUrl}/api/bandwidth/temporary-limits"
    method: POST
    headers:
      X-API-Key: "${apiKeyValue}"
    content_type: "application/json"
    payload: >
      {"download_mbps": {{ download_mbps | default('null') }},
       "upload_mbps": {{ upload_mbps | default('null') }},
       "duration_hours": {{ duration_hours }},
       "source": "{{ source }}"}
  speedarr_clear_limits:
    url: "${speedarrUrl}/api/bandwidth/temporary-limits"
    method: DELETE
    headers:
      X-API-Key: "${apiKeyValue}"`;

  const throttleAutomationYaml = `alias: "Throttle downloads for gaming"
trigger:
  - platform: state
    entity_id: binary_sensor.gaming_pc
    from: "off"
    to: "on"
action:
  - service: rest_command.speedarr_set_limits
    data:
      download_mbps: 50
      upload_mbps: 25
      duration_hours: 4
      source: "Home Assistant - Gaming PC"`;

  const restoreAutomationYaml = `alias: "Restore downloads after gaming"
trigger:
  - platform: state
    entity_id: binary_sensor.gaming_pc
    from: "on"
    to: "off"
action:
  - service: rest_command.speedarr_clear_limits`;

  const formatDate = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleDateString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
    });
  };

  const formatDateTime = (dateStr: string | null) => {
    if (!dateStr) return 'Never';
    return new Date(dateStr).toLocaleString(undefined, {
      year: 'numeric', month: 'short', day: 'numeric',
      hour: '2-digit', minute: '2-digit',
    });
  };

  return (
    <div className="space-y-6">
      {/* API Keys Management Card */}
      <Card>
        <CardHeader>
          <div className="flex items-center justify-between">
            <div>
              <CardTitle className="flex items-center gap-2">
                <Key className="h-5 w-5" />
                API Keys
              </CardTitle>
              <CardDescription>
                Manage API keys for programmatic access (e.g., Home Assistant)
              </CardDescription>
            </div>
            <Button size="sm" onClick={() => setIsCreateOpen(true)}>
              <Plus className="h-4 w-4 mr-1" />
              Generate Key
            </Button>
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

          {isLoading ? (
            <div className="flex justify-center py-8">
              <Loader2 className="h-6 w-6 animate-spin text-muted-foreground" />
            </div>
          ) : keys.length === 0 ? (
            <p className="text-sm text-muted-foreground text-center py-8">
              No API keys yet. Generate one to enable programmatic access.
            </p>
          ) : (
            <Table>
              <TableHeader>
                <TableRow>
                  <TableHead>Name</TableHead>
                  <TableHead>Key</TableHead>
                  <TableHead>Created</TableHead>
                  <TableHead>Expires</TableHead>
                  <TableHead>Last Used</TableHead>
                  <TableHead>Status</TableHead>
                  <TableHead className="w-[60px]"></TableHead>
                </TableRow>
              </TableHeader>
              <TableBody>
                {keys.map((key) => (
                  <TableRow key={key.id}>
                    <TableCell className="font-medium">{key.name}</TableCell>
                    <TableCell>
                      <div className="flex items-center gap-1.5">
                        <code className="text-xs bg-muted px-1.5 py-0.5 rounded">{key.token_preview}</code>
                        <Button
                          variant="ghost"
                          size="icon"
                          className="h-6 w-6"
                          onClick={() => {
                            copyToClipboard(key.token);
                            setCopiedKeyId(key.id);
                            setTimeout(() => setCopiedKeyId(null), 2000);
                          }}
                        >
                          {copiedKeyId === key.id ? (
                            <Check className="h-3 w-3 text-green-600" />
                          ) : (
                            <Copy className="h-3 w-3" />
                          )}
                        </Button>
                      </div>
                    </TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(key.created_at)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">{formatDate(key.expires_at)}</TableCell>
                    <TableCell className="text-sm text-muted-foreground">
                      {key.last_used ? formatDateTime(key.last_used) : 'Never'}
                    </TableCell>
                    <TableCell>
                      {key.is_active ? (
                        <Badge variant="default" className="bg-green-600">Active</Badge>
                      ) : (
                        <Badge variant="secondary">Revoked</Badge>
                      )}
                    </TableCell>
                    <TableCell>
                      {key.is_active && (
                        <Button
                          variant="ghost"
                          size="icon"
                          onClick={() => handleRevoke(key.id)}
                          disabled={revokingId === key.id}
                          className="h-8 w-8 text-destructive hover:text-destructive"
                        >
                          {revokingId === key.id ? (
                            <Loader2 className="h-4 w-4 animate-spin" />
                          ) : (
                            <Trash2 className="h-4 w-4" />
                          )}
                        </Button>
                      )}
                    </TableCell>
                  </TableRow>
                ))}
              </TableBody>
            </Table>
          )}
        </CardContent>
      </Card>

      {/* Create API Key Dialog */}
      <Dialog open={isCreateOpen} onOpenChange={setIsCreateOpen}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>Generate API Key</DialogTitle>
            <DialogDescription>
              Create a new API key for programmatic access.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-4 py-2">
            <div className="space-y-2">
              <Label htmlFor="key-name">Name</Label>
              <Input
                id="key-name"
                placeholder="e.g., Home Assistant"
                value={newKeyName}
                onChange={(e) => setNewKeyName(e.target.value)}
                maxLength={100}
              />
            </div>
            <div className="space-y-2">
              <Label htmlFor="key-expiry">Expiration</Label>
              <Select value={newKeyExpiry} onValueChange={setNewKeyExpiry}>
                <SelectTrigger id="key-expiry">
                  <SelectValue />
                </SelectTrigger>
                <SelectContent>
                  <SelectItem value="never">Never</SelectItem>
                  <SelectItem value="30">30 days</SelectItem>
                  <SelectItem value="90">90 days</SelectItem>
                  <SelectItem value="180">180 days</SelectItem>
                  <SelectItem value="365">1 year</SelectItem>
                </SelectContent>
              </Select>
            </div>
          </div>
          <DialogFooter>
            <Button variant="outline" onClick={() => setIsCreateOpen(false)}>
              Cancel
            </Button>
            <Button onClick={handleCreate} disabled={!newKeyName.trim() || isCreating}>
              {isCreating && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Generate
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Token Reveal Dialog */}
      <Dialog open={!!revealedToken} onOpenChange={() => { setRevealedToken(null); setCopied(false); }}>
        <DialogContent>
          <DialogHeader>
            <DialogTitle>API Key Created</DialogTitle>
            <DialogDescription>
              Your new API key is ready to use.
            </DialogDescription>
          </DialogHeader>
          <div className="space-y-3 py-2">
            <div className="flex items-center gap-2">
              <code className="flex-1 text-sm bg-muted p-3 rounded-md break-all font-mono select-all">
                {revealedToken}
              </code>
              <Button variant="outline" size="icon" onClick={handleCopy} className="shrink-0">
                {copied ? <Check className="h-4 w-4 text-green-600" /> : <Copy className="h-4 w-4" />}
              </Button>
            </div>
            <p className="text-sm text-muted-foreground">
              Use this key in the <code className="text-xs bg-muted px-1 py-0.5 rounded">X-API-Key</code> header for API requests.
            </p>
          </div>
          <DialogFooter>
            <Button onClick={() => { setRevealedToken(null); setCopied(false); }}>
              Done
            </Button>
          </DialogFooter>
        </DialogContent>
      </Dialog>

      {/* Home Assistant Integration Guide */}
      <Card>
        <CardHeader>
          <CardTitle className="flex items-center gap-2">
            <BookOpen className="h-5 w-5" />
            Home Assistant Integration
          </CardTitle>
          <CardDescription>
            Use API keys to control Speedarr from Home Assistant automations
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="space-y-2">
            <h4 className="text-sm font-medium">1. Add REST commands to <code className="text-xs bg-muted px-1 py-0.5 rounded">configuration.yaml</code></h4>
            <CopyableCode code={restCommandYaml} />
          </div>

          <div className="space-y-4">
            <h4 className="text-sm font-medium">2. Create automations</h4>
            <p className="text-xs text-muted-foreground">
              Create these automations in Home Assistant via <strong>Settings &gt; Automations &amp; Scenes &gt; Create Automation</strong>. Switch to YAML mode and paste the following:
            </p>

            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Throttle when gaming PC turns on</p>
              <CopyableCode code={throttleAutomationYaml} />
            </div>

            <div className="space-y-1">
              <p className="text-xs font-medium text-muted-foreground">Restore when gaming PC turns off</p>
              <CopyableCode code={restoreAutomationYaml} />
            </div>
          </div>
        </CardContent>
      </Card>
    </div>
  );
};

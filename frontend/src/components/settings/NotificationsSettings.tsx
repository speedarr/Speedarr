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
import { useUnsavedChanges } from '@/hooks/useUnsavedChanges';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';
import { getErrorMessage } from '@/lib/utils';

interface DiscordConfig {
  enabled: boolean;
  webhook_url: string;
  events: string[];
  rate_limit: number;
}

interface PushoverConfig {
  enabled: boolean;
  user_key: string;
  api_token: string;
  priority: number;
  events: string[];
}

interface TelegramConfig {
  enabled: boolean;
  bot_token: string;
  chat_id: string;
  events: string[];
}

interface GotifyConfig {
  enabled: boolean;
  server_url: string;
  app_token: string;
  priority: number;
  events: string[];
}

interface NtfyConfig {
  enabled: boolean;
  server_url: string;
  topic: string;
  priority: number;
  events: string[];
}

interface NotificationsConfig {
  discord: DiscordConfig;
  pushover: PushoverConfig;
  telegram: TelegramConfig;
  gotify: GotifyConfig;
  ntfy: NtfyConfig;
  stream_count_threshold: number | null;
  stream_bitrate_threshold: number | null;
}

export const NotificationsSettings: React.FC = () => {
  const [config, setConfig] = useState<NotificationsConfig | null>(null);
  const [isLoading, setIsLoading] = useState(true);
  const [isSaving, setIsSaving] = useState(false);
  const [isTesting, setIsTesting] = useState(false);
  const [error, setError] = useState('');
  const [success, setSuccess] = useState('');
  const [testResult, setTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [pushoverTestResult, setPushoverTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [telegramTestResult, setTelegramTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [gotifyTestResult, setGotifyTestResult] = useState<{ success: boolean; message: string } | null>(null);
  const [ntfyTestResult, setNtfyTestResult] = useState<{ success: boolean; message: string } | null>(null);

  const saveButtonRef = useRef<HTMLButtonElement>(null);
  const { hasUnsavedChanges, resetOriginal, discardChanges } = useUnsavedChanges<NotificationsConfig>();
  const { registerTab, unregisterTab } = useUnsavedChangesContext();

  const isDirty = hasUnsavedChanges(config);

  // Register dirty state with context
  useEffect(() => {
    registerTab(
      'notifications',
      isDirty,
      saveButtonRef,
      async () => { await handleSave(); },
      () => {
        const original = discardChanges();
        if (original) setConfig(original);
      }
    );
    return () => unregisterTab('notifications');
  }, [isDirty, registerTab, unregisterTab]);

  useEffect(() => {
    loadConfig();
  }, []);

  const loadConfig = async () => {
    try {
      const response = await apiClient.getSettingsSection('notifications');
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

    // Auto-test webhook if enabled and URL is set (not masked)
    if (config.discord.enabled && config.discord.webhook_url &&
        config.discord.webhook_url !== '***REDACTED***') {

      setSuccess('Testing webhook...');

      try {
        const testResult = await apiClient.testConnection('discord', {
          webhook_url: config.discord.webhook_url,
        });

        if (!testResult.success) {
          setError(`Webhook test failed: ${testResult.message}. Settings not saved.`);
          setSuccess('');
          setIsSaving(false);
          return; // Don't save if test fails
        }
      } catch (error: unknown) {
        setError(`Webhook test failed: ${getErrorMessage(error)}. Settings not saved.`);
        setSuccess('');
        setIsSaving(false);
        return;
      }
    }

    // Proceed with save after successful test (or if webhook disabled/unchanged)
    try {
      await apiClient.updateSettingsSection('notifications', config);
      resetOriginal(config);
      setSuccess('Notifications settings saved successfully');
      setTimeout(() => setSuccess(''), 3000);
    } catch (error: unknown) {
      setError(getErrorMessage(error));
    } finally {
      setIsSaving(false);
    }
  };

  const handleTestDiscord = async () => {
    if (!config) return;

    setIsTesting(true);
    setTestResult(null);

    try {
      // If webhook URL is masked, use the existing saved URL
      const useExisting = config.discord.webhook_url === '***REDACTED***';
      const response = await apiClient.testConnection('discord', {
        webhook_url: config.discord.webhook_url,
      }, useExisting);
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

  const handleTestPushover = async () => {
    if (!config) return;

    setIsTesting(true);
    setPushoverTestResult(null);

    try {
      const useExisting = config.pushover.user_key?.includes('***REDACTED***') ||
                          config.pushover.api_token?.includes('***REDACTED***');
      const response = await apiClient.testConnection('pushover', {
        user_key: config.pushover.user_key,
        api_token: config.pushover.api_token,
      }, useExisting);
      setPushoverTestResult({ success: response.success, message: response.message });
      if (response.success) {
        setTimeout(() => setPushoverTestResult(null), 3000);
      }
    } catch (error: unknown) {
      setPushoverTestResult({
        success: false,
        message: getErrorMessage(error),
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleTestTelegram = async () => {
    if (!config) return;

    setIsTesting(true);
    setTelegramTestResult(null);

    try {
      const useExisting = config.telegram.bot_token?.includes('***REDACTED***');
      const response = await apiClient.testConnection('telegram', {
        bot_token: config.telegram.bot_token,
        chat_id: config.telegram.chat_id,
      }, useExisting);
      setTelegramTestResult({ success: response.success, message: response.message });
      if (response.success) {
        setTimeout(() => setTelegramTestResult(null), 3000);
      }
    } catch (error: unknown) {
      setTelegramTestResult({
        success: false,
        message: getErrorMessage(error),
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleTestGotify = async () => {
    if (!config) return;

    setIsTesting(true);
    setGotifyTestResult(null);

    try {
      const useExisting = config.gotify.app_token?.includes('***REDACTED***');
      const response = await apiClient.testConnection('gotify', {
        server_url: config.gotify.server_url,
        app_token: config.gotify.app_token,
      }, useExisting);
      setGotifyTestResult({ success: response.success, message: response.message });
      if (response.success) {
        setTimeout(() => setGotifyTestResult(null), 3000);
      }
    } catch (error: unknown) {
      setGotifyTestResult({
        success: false,
        message: getErrorMessage(error),
      });
    } finally {
      setIsTesting(false);
    }
  };

  const handleTestNtfy = async () => {
    if (!config) return;

    setIsTesting(true);
    setNtfyTestResult(null);

    try {
      const response = await apiClient.testConnection('ntfy', {
        server_url: config.ntfy.server_url || 'https://ntfy.sh',
        topic: config.ntfy.topic,
      }, false);
      setNtfyTestResult({ success: response.success, message: response.message });
      if (response.success) {
        setTimeout(() => setNtfyTestResult(null), 3000);
      }
    } catch (error: unknown) {
      setNtfyTestResult({
        success: false,
        message: getErrorMessage(error),
      });
    } finally {
      setIsTesting(false);
    }
  };

  const updateDiscordConfig = useCallback((field: keyof DiscordConfig, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev;
      return { ...prev, discord: { ...prev.discord, [field]: value } };
    });
  }, []);

  const toggleDiscordEvent = useCallback((event: string) => {
    setConfig(prev => {
      if (!prev) return prev;
      const events = prev.discord.events.includes(event)
        ? prev.discord.events.filter((e) => e !== event)
        : [...prev.discord.events, event];
      return { ...prev, discord: { ...prev.discord, events } };
    });
  }, []);

  // Pushover helpers
  const updatePushoverConfig = useCallback((field: keyof PushoverConfig, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev;
      return { ...prev, pushover: { ...prev.pushover, [field]: value } };
    });
  }, []);

  const togglePushoverEvent = useCallback((event: string) => {
    setConfig(prev => {
      if (!prev) return prev;
      const events = prev.pushover.events.includes(event)
        ? prev.pushover.events.filter((e) => e !== event)
        : [...prev.pushover.events, event];
      return { ...prev, pushover: { ...prev.pushover, events } };
    });
  }, []);

  // Telegram helpers
  const updateTelegramConfig = useCallback((field: keyof TelegramConfig, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev;
      return { ...prev, telegram: { ...prev.telegram, [field]: value } };
    });
  }, []);

  const toggleTelegramEvent = useCallback((event: string) => {
    setConfig(prev => {
      if (!prev) return prev;
      const events = prev.telegram.events.includes(event)
        ? prev.telegram.events.filter((e) => e !== event)
        : [...prev.telegram.events, event];
      return { ...prev, telegram: { ...prev.telegram, events } };
    });
  }, []);

  // Gotify helpers
  const updateGotifyConfig = useCallback((field: keyof GotifyConfig, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev;
      return { ...prev, gotify: { ...prev.gotify, [field]: value } };
    });
  }, []);

  const toggleGotifyEvent = useCallback((event: string) => {
    setConfig(prev => {
      if (!prev) return prev;
      const events = prev.gotify.events.includes(event)
        ? prev.gotify.events.filter((e) => e !== event)
        : [...prev.gotify.events, event];
      return { ...prev, gotify: { ...prev.gotify, events } };
    });
  }, []);

  // ntfy helpers
  const updateNtfyConfig = useCallback((field: keyof NtfyConfig, value: unknown) => {
    setConfig(prev => {
      if (!prev) return prev;
      return { ...prev, ntfy: { ...prev.ntfy, [field]: value } };
    });
  }, []);

  const toggleNtfyEvent = (event: string) => {
    if (!config) return;
    const events = config.ntfy.events.includes(event)
      ? config.ntfy.events.filter((e) => e !== event)
      : [...config.ntfy.events, event];
    updateNtfyConfig('events', events);
  };

  const availableEvents = [
    { value: 'stream_started', label: 'Stream Started', description: 'Notify when a new Plex stream begins' },
    { value: 'stream_ended', label: 'Stream Ended', description: 'Notify when a Plex stream stops' },
    { value: 'stream_count_exceeded', label: 'Stream Count Exceeded', description: 'Notify when active streams exceed the threshold' },
    { value: 'stream_bitrate_exceeded', label: 'Stream Bitrate Exceeded', description: 'Notify when total stream bitrate exceeds the threshold' },
    { value: 'service_unreachable', label: 'Service Unreachable', description: 'Notify when a connected service becomes unreachable' },
  ];

  const updateStreamCountThreshold = (value: string) => {
    if (!config) return;
    const numValue = parseInt(value);
    setConfig({
      ...config,
      stream_count_threshold: isNaN(numValue) || numValue <= 0 ? null : numValue,
    });
  };

  const updateStreamBitrateThreshold = (value: string) => {
    if (!config) return;
    const numValue = parseFloat(value);
    setConfig({
      ...config,
      stream_bitrate_threshold: isNaN(numValue) || numValue <= 0 ? null : numValue,
    });
  };

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
            <AlertDescription>Failed to load notifications configuration</AlertDescription>
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

      {/* Webhook Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Webhook Notifications</CardTitle>
          <CardDescription>
            Send notifications to Discord or any webhook-compatible service
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="discord-enabled">Enable Webhook Notifications</Label>
              <p className="text-sm text-muted-foreground">
                Send events to a webhook URL
              </p>
            </div>
            <Switch
              id="discord-enabled"
              checked={config.discord.enabled}
              onCheckedChange={(checked) => updateDiscordConfig('enabled', checked)}
              disabled={isSaving}
            />
          </div>

          {config.discord.enabled && (
            <>
              <div className="space-y-2">
                <Label htmlFor="discord-webhook">Webhook URL</Label>
                <PasswordInput
                  value={config.discord.webhook_url === '***REDACTED***' ? '' : config.discord.webhook_url}
                  onChange={(e) => updateDiscordConfig('webhook_url', e.target.value)}
                  placeholder={config.discord.webhook_url === '***REDACTED***' ? 'Current webhook URL is set' : 'https://discord.com/api/webhooks/...'}
                  disabled={isSaving}
                  maxLength={512}
                />
                <p className="text-sm text-muted-foreground">
                  Works with Discord, Slack, and other webhook services
                </p>
              </div>

              <div className="space-y-2">
                <Label>Events to Send</Label>
                <div className="rounded-lg border p-4 space-y-3">
                  {availableEvents.map((event) => (
                    <div key={event.value} className="flex items-start space-x-2">
                      <Switch
                        className="mt-0.5"
                        checked={config.discord.events.includes(event.value)}
                        onCheckedChange={() => toggleDiscordEvent(event.value)}
                        disabled={isSaving}
                      />
                      <div className="flex-1">
                        <Label className="font-normal cursor-pointer" onClick={() => toggleDiscordEvent(event.value)}>
                          {event.label}
                        </Label>
                        <p className="text-sm text-muted-foreground">{event.description}</p>
                        {event.value === 'stream_count_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="stream-threshold-discord" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="stream-threshold-discord"
                              type="number"
                              min="1"
                              step="1"
                              className="w-20 h-8"
                              value={config.stream_count_threshold ?? ''}
                              onChange={(e) => updateStreamCountThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">streams</span>
                          </div>
                        )}
                        {event.value === 'stream_bitrate_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="bitrate-threshold-discord" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="bitrate-threshold-discord"
                              type="number"
                              min="1"
                              step="0.1"
                              className="w-20 h-8"
                              value={config.stream_bitrate_threshold ?? ''}
                              onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">Mbps</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={handleTestDiscord}
                  disabled={isTesting || !config.discord.webhook_url}
                  variant="outline"
                >
                  {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Test Webhook
                </Button>
              </div>

              {testResult && (
                <Alert variant={testResult.success ? 'default' : 'destructive'}>
                  {testResult.success ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  <AlertDescription>{testResult.message}</AlertDescription>
                </Alert>
              )}
            </>
          )}
        </CardContent>
      </Card>

      {/* Pushover Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Pushover Notifications</CardTitle>
          <CardDescription>
            Send notifications to Pushover mobile app
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="pushover-enabled">Enable Pushover</Label>
              <p className="text-sm text-muted-foreground">
                Send notifications via Pushover
              </p>
            </div>
            <Switch
              id="pushover-enabled"
              checked={config.pushover?.enabled || false}
              onCheckedChange={(checked) => updatePushoverConfig('enabled', checked)}
              disabled={isSaving}
            />
          </div>

          {config.pushover?.enabled && (
            <>
              <div className="space-y-2">
                <Label htmlFor="pushover-user-key">User Key</Label>
                <PasswordInput
                  value={config.pushover.user_key === '***REDACTED***' ? '' : config.pushover.user_key || ''}
                  onChange={(e) => updatePushoverConfig('user_key', e.target.value)}
                  placeholder={config.pushover.user_key === '***REDACTED***' ? 'User key is set' : 'Enter your Pushover user key'}
                  disabled={isSaving}
                  maxLength={128}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="pushover-api-token">API Token</Label>
                <PasswordInput
                  value={config.pushover.api_token === '***REDACTED***' ? '' : config.pushover.api_token || ''}
                  onChange={(e) => updatePushoverConfig('api_token', e.target.value)}
                  placeholder={config.pushover.api_token === '***REDACTED***' ? 'API token is set' : 'Enter your Pushover API token'}
                  disabled={isSaving}
                  maxLength={128}
                />
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={handleTestPushover}
                  disabled={isTesting || !config.pushover.user_key || !config.pushover.api_token}
                  variant="outline"
                >
                  {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Test Pushover
                </Button>
              </div>

              {pushoverTestResult && (
                <Alert variant={pushoverTestResult.success ? 'default' : 'destructive'}>
                  {pushoverTestResult.success ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  <AlertDescription>{pushoverTestResult.message}</AlertDescription>
                </Alert>
              )}

              <div className="space-y-2">
                <Label>Events to Send</Label>
                <div className="rounded-lg border p-4 space-y-3">
                  {availableEvents.map((event) => (
                    <div key={event.value} className="flex items-start space-x-2">
                      <Switch
                        className="mt-0.5"
                        checked={config.pushover.events?.includes(event.value) || false}
                        onCheckedChange={() => togglePushoverEvent(event.value)}
                        disabled={isSaving}
                      />
                      <div className="flex-1">
                        <Label className="font-normal cursor-pointer" onClick={() => togglePushoverEvent(event.value)}>
                          {event.label}
                        </Label>
                        <p className="text-sm text-muted-foreground">{event.description}</p>
                        {event.value === 'stream_count_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="stream-threshold-pushover" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="stream-threshold-pushover"
                              type="number"
                              min="1"
                              step="1"
                              className="w-20 h-8"
                              value={config.stream_count_threshold ?? ''}
                              onChange={(e) => updateStreamCountThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">streams</span>
                          </div>
                        )}
                        {event.value === 'stream_bitrate_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="bitrate-threshold-pushover" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="bitrate-threshold-pushover"
                              type="number"
                              min="1"
                              step="0.1"
                              className="w-20 h-8"
                              value={config.stream_bitrate_threshold ?? ''}
                              onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">Mbps</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Telegram Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Telegram Notifications</CardTitle>
          <CardDescription>
            Send notifications to Telegram via bot
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="telegram-enabled">Enable Telegram</Label>
              <p className="text-sm text-muted-foreground">
                Send notifications via Telegram Bot
              </p>
            </div>
            <Switch
              id="telegram-enabled"
              checked={config.telegram?.enabled || false}
              onCheckedChange={(checked) => updateTelegramConfig('enabled', checked)}
              disabled={isSaving}
            />
          </div>

          {config.telegram?.enabled && (
            <>
              <div className="space-y-2">
                <Label htmlFor="telegram-bot-token">Bot Token</Label>
                <PasswordInput
                  value={config.telegram.bot_token === '***REDACTED***' ? '' : config.telegram.bot_token || ''}
                  onChange={(e) => updateTelegramConfig('bot_token', e.target.value)}
                  placeholder={config.telegram.bot_token === '***REDACTED***' ? 'Bot token is set' : 'Enter your Telegram bot token'}
                  disabled={isSaving}
                  maxLength={128}
                />
                <p className="text-sm text-muted-foreground">
                  Get from @BotFather on Telegram
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="telegram-chat-id">Chat ID</Label>
                <Input
                  id="telegram-chat-id"
                  value={config.telegram.chat_id || ''}
                  onChange={(e) => updateTelegramConfig('chat_id', e.target.value)}
                  placeholder="Enter chat ID or username"
                  disabled={isSaving}
                  maxLength={100}
                />
                <p className="text-sm text-muted-foreground">
                  Use @userinfobot to get your chat ID
                </p>
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={handleTestTelegram}
                  disabled={isTesting || !config.telegram.bot_token || !config.telegram.chat_id}
                  variant="outline"
                >
                  {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Test Telegram
                </Button>
              </div>

              {telegramTestResult && (
                <Alert variant={telegramTestResult.success ? 'default' : 'destructive'}>
                  {telegramTestResult.success ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  <AlertDescription>{telegramTestResult.message}</AlertDescription>
                </Alert>
              )}

              <div className="space-y-2">
                <Label>Events to Send</Label>
                <div className="rounded-lg border p-4 space-y-3">
                  {availableEvents.map((event) => (
                    <div key={event.value} className="flex items-start space-x-2">
                      <Switch
                        className="mt-0.5"
                        checked={config.telegram.events?.includes(event.value) || false}
                        onCheckedChange={() => toggleTelegramEvent(event.value)}
                        disabled={isSaving}
                      />
                      <div className="flex-1">
                        <Label className="font-normal cursor-pointer" onClick={() => toggleTelegramEvent(event.value)}>
                          {event.label}
                        </Label>
                        <p className="text-sm text-muted-foreground">{event.description}</p>
                        {event.value === 'stream_count_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="stream-threshold-telegram" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="stream-threshold-telegram"
                              type="number"
                              min="1"
                              step="1"
                              className="w-20 h-8"
                              value={config.stream_count_threshold ?? ''}
                              onChange={(e) => updateStreamCountThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">streams</span>
                          </div>
                        )}
                        {event.value === 'stream_bitrate_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="bitrate-threshold-telegram" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="bitrate-threshold-telegram"
                              type="number"
                              min="1"
                              step="0.1"
                              className="w-20 h-8"
                              value={config.stream_bitrate_threshold ?? ''}
                              onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">Mbps</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* Gotify Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>Gotify Notifications</CardTitle>
          <CardDescription>
            Send notifications to your self-hosted Gotify server
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="gotify-enabled">Enable Gotify</Label>
              <p className="text-sm text-muted-foreground">
                Send notifications via Gotify
              </p>
            </div>
            <Switch
              id="gotify-enabled"
              checked={config.gotify?.enabled || false}
              onCheckedChange={(checked) => updateGotifyConfig('enabled', checked)}
              disabled={isSaving}
            />
          </div>

          {config.gotify?.enabled && (
            <>
              <div className="space-y-2">
                <Label htmlFor="gotify-server-url">Server URL</Label>
                <Input
                  id="gotify-server-url"
                  type="url"
                  value={config.gotify.server_url || ''}
                  onChange={(e) => updateGotifyConfig('server_url', e.target.value)}
                  placeholder="https://gotify.yourdomain.com"
                  disabled={isSaving}
                  maxLength={512}
                />
              </div>

              <div className="space-y-2">
                <Label htmlFor="gotify-app-token">Application Token</Label>
                <PasswordInput
                  value={config.gotify.app_token === '***REDACTED***' ? '' : config.gotify.app_token || ''}
                  onChange={(e) => updateGotifyConfig('app_token', e.target.value)}
                  placeholder={config.gotify.app_token === '***REDACTED***' ? 'App token is set' : 'Enter your Gotify app token'}
                  disabled={isSaving}
                  maxLength={128}
                />
                <p className="text-sm text-muted-foreground">
                  Create an application in Gotify to get the token
                </p>
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={handleTestGotify}
                  disabled={isTesting || !config.gotify.server_url || !config.gotify.app_token}
                  variant="outline"
                >
                  {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Test Gotify
                </Button>
              </div>

              {gotifyTestResult && (
                <Alert variant={gotifyTestResult.success ? 'default' : 'destructive'}>
                  {gotifyTestResult.success ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  <AlertDescription>{gotifyTestResult.message}</AlertDescription>
                </Alert>
              )}

              <div className="space-y-2">
                <Label>Events to Send</Label>
                <div className="rounded-lg border p-4 space-y-3">
                  {availableEvents.map((event) => (
                    <div key={event.value} className="flex items-start space-x-2">
                      <Switch
                        className="mt-0.5"
                        checked={config.gotify.events?.includes(event.value) || false}
                        onCheckedChange={() => toggleGotifyEvent(event.value)}
                        disabled={isSaving}
                      />
                      <div className="flex-1">
                        <Label className="font-normal cursor-pointer" onClick={() => toggleGotifyEvent(event.value)}>
                          {event.label}
                        </Label>
                        <p className="text-sm text-muted-foreground">{event.description}</p>
                        {event.value === 'stream_count_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="stream-threshold-gotify" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="stream-threshold-gotify"
                              type="number"
                              min="1"
                              step="1"
                              className="w-20 h-8"
                              value={config.stream_count_threshold ?? ''}
                              onChange={(e) => updateStreamCountThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">streams</span>
                          </div>
                        )}
                        {event.value === 'stream_bitrate_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="bitrate-threshold-gotify" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="bitrate-threshold-gotify"
                              type="number"
                              min="1"
                              step="0.1"
                              className="w-20 h-8"
                              value={config.stream_bitrate_threshold ?? ''}
                              onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">Mbps</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
        </CardContent>
      </Card>

      {/* ntfy Configuration */}
      <Card>
        <CardHeader>
          <CardTitle>ntfy Notifications</CardTitle>
          <CardDescription>
            Send notifications via ntfy (pub-sub)
          </CardDescription>
        </CardHeader>
        <CardContent className="space-y-4">
          <div className="flex items-center justify-between space-x-2 rounded-lg border p-4">
            <div className="space-y-0.5">
              <Label htmlFor="ntfy-enabled">Enable ntfy</Label>
              <p className="text-sm text-muted-foreground">
                Send notifications via ntfy
              </p>
            </div>
            <Switch
              id="ntfy-enabled"
              checked={config.ntfy?.enabled || false}
              onCheckedChange={(checked) => updateNtfyConfig('enabled', checked)}
              disabled={isSaving}
            />
          </div>

          {config.ntfy?.enabled && (
            <>
              <div className="space-y-2">
                <Label htmlFor="ntfy-server-url">Server URL</Label>
                <Input
                  id="ntfy-server-url"
                  type="url"
                  value={config.ntfy.server_url || 'https://ntfy.sh'}
                  onChange={(e) => updateNtfyConfig('server_url', e.target.value)}
                  placeholder="https://ntfy.sh"
                  disabled={isSaving}
                  maxLength={512}
                />
                <p className="text-sm text-muted-foreground">
                  Use ntfy.sh or your self-hosted instance
                </p>
              </div>

              <div className="space-y-2">
                <Label htmlFor="ntfy-topic">Topic</Label>
                <Input
                  id="ntfy-topic"
                  value={config.ntfy.topic || ''}
                  onChange={(e) => updateNtfyConfig('topic', e.target.value)}
                  placeholder="speedarr-notifications"
                  disabled={isSaving}
                  maxLength={100}
                />
                <p className="text-sm text-muted-foreground">
                  Subscribe to this topic in the ntfy app
                </p>
              </div>

              <div className="flex gap-2">
                <Button
                  onClick={handleTestNtfy}
                  disabled={isTesting || !config.ntfy.topic}
                  variant="outline"
                >
                  {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                  Test ntfy
                </Button>
              </div>

              {ntfyTestResult && (
                <Alert variant={ntfyTestResult.success ? 'default' : 'destructive'}>
                  {ntfyTestResult.success ? <CheckCircle className="h-4 w-4" /> : <AlertCircle className="h-4 w-4" />}
                  <AlertDescription>{ntfyTestResult.message}</AlertDescription>
                </Alert>
              )}

              <div className="space-y-2">
                <Label>Events to Send</Label>
                <div className="rounded-lg border p-4 space-y-3">
                  {availableEvents.map((event) => (
                    <div key={event.value} className="flex items-start space-x-2">
                      <Switch
                        className="mt-0.5"
                        checked={config.ntfy.events?.includes(event.value) || false}
                        onCheckedChange={() => toggleNtfyEvent(event.value)}
                        disabled={isSaving}
                      />
                      <div className="flex-1">
                        <Label className="font-normal cursor-pointer" onClick={() => toggleNtfyEvent(event.value)}>
                          {event.label}
                        </Label>
                        <p className="text-sm text-muted-foreground">{event.description}</p>
                        {event.value === 'stream_count_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="stream-threshold-ntfy" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="stream-threshold-ntfy"
                              type="number"
                              min="1"
                              step="1"
                              className="w-20 h-8"
                              value={config.stream_count_threshold ?? ''}
                              onChange={(e) => updateStreamCountThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">streams</span>
                          </div>
                        )}
                        {event.value === 'stream_bitrate_exceeded' && (
                          <div className="flex items-center gap-2 mt-2">
                            <Label htmlFor="bitrate-threshold-ntfy" className="text-sm text-muted-foreground whitespace-nowrap">
                              Threshold:
                            </Label>
                            <Input
                              id="bitrate-threshold-ntfy"
                              type="number"
                              min="1"
                              step="0.1"
                              className="w-20 h-8"
                              value={config.stream_bitrate_threshold ?? ''}
                              onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                              placeholder="0"
                              disabled={isSaving}
                            />
                            <span className="text-sm text-muted-foreground">Mbps</span>
                          </div>
                        )}
                      </div>
                    </div>
                  ))}
                </div>
              </div>
            </>
          )}
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
          Save All Notifications Settings
        </Button>
      </div>
    </div>
  );
};

/**
 * NotificationsStep - Configure all notification agents
 */

import React, { useState, useEffect } from 'react';
import { Label } from '@/components/ui/label';
import { Input } from '@/components/ui/input';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Switch } from '@/components/ui/switch';
import { Checkbox } from '@/components/ui/checkbox';
import {
  Collapsible,
  CollapsibleContent,
  CollapsibleTrigger,
} from '@/components/ui/collapsible';
import { Loader2, CheckCircle, XCircle, ChevronDown, MessageSquare, Bell, Send, Server, Radio } from 'lucide-react';
import { PasswordInput } from '@/components/settings/PasswordInput';
import { apiClient } from '@/api/client';
import { WizardStepProps, NotificationsConfig } from '../types';

const DEFAULT_EVENTS = [
  'stream_started', 'stream_ended', 'stream_count_exceeded',
  'stream_bitrate_exceeded', 'service_unreachable'
];

const AVAILABLE_EVENTS = [
  { value: 'stream_started', label: 'Stream Started', description: 'When a new Plex stream begins' },
  { value: 'stream_ended', label: 'Stream Ended', description: 'When a Plex stream stops' },
  { value: 'stream_count_exceeded', label: 'Stream Count Exceeded', description: 'When streams exceed threshold' },
  { value: 'stream_bitrate_exceeded', label: 'Stream Bitrate Exceeded', description: 'When bitrate exceeds threshold' },
  { value: 'service_unreachable', label: 'Service Unreachable', description: 'When a service becomes unreachable' },
];

const DEFAULT_CONFIG: NotificationsConfig = {
  discord: {
    enabled: false,
    webhook_url: '',
    events: DEFAULT_EVENTS,
  },
  pushover: {
    enabled: false,
    user_key: '',
    api_token: '',
    events: DEFAULT_EVENTS,
  },
  telegram: {
    enabled: false,
    bot_token: '',
    chat_id: '',
    events: DEFAULT_EVENTS,
  },
  gotify: {
    enabled: false,
    server_url: '',
    app_token: '',
    events: DEFAULT_EVENTS,
  },
  ntfy: {
    enabled: false,
    server_url: 'https://ntfy.sh',
    topic: '',
    events: DEFAULT_EVENTS,
  },
  stream_count_threshold: null,
  stream_bitrate_threshold: null,
};

export const NotificationsStep: React.FC<WizardStepProps> = ({
  data,
  onDataChange,
  isLoading,
  readOnly,
}) => {
  const [config, setConfig] = useState<NotificationsConfig>(() => {
    // Deep merge to handle partial data from localStorage
    return {
      discord: { ...DEFAULT_CONFIG.discord, ...data?.discord },
      pushover: { ...DEFAULT_CONFIG.pushover, ...data?.pushover },
      telegram: { ...DEFAULT_CONFIG.telegram, ...data?.telegram },
      gotify: { ...DEFAULT_CONFIG.gotify, ...data?.gotify },
      ntfy: { ...DEFAULT_CONFIG.ntfy, ...data?.ntfy },
    };
  });

  const [isTesting, setIsTesting] = useState<string | null>(null);
  const [testResult, setTestResult] = useState<{ agent: string; success: boolean; message: string } | null>(null);
  const [openSections, setOpenSections] = useState<string[]>(['discord']);

  // Update parent when config changes
  useEffect(() => {
    onDataChange(config);
  }, [config, onDataChange]);

  const toggleSection = (section: string) => {
    setOpenSections(prev =>
      prev.includes(section)
        ? prev.filter(s => s !== section)
        : [...prev, section]
    );
  };

  // Update functions for each agent
  const updateDiscord = (field: string, value: any) => {
    setConfig(prev => ({
      ...prev,
      discord: { ...prev.discord, [field]: value },
    }));
    setTestResult(null);
  };

  const updatePushover = (field: string, value: any) => {
    setConfig(prev => ({
      ...prev,
      pushover: { ...prev.pushover, [field]: value },
    }));
    setTestResult(null);
  };

  const updateTelegram = (field: string, value: any) => {
    setConfig(prev => ({
      ...prev,
      telegram: { ...prev.telegram, [field]: value },
    }));
    setTestResult(null);
  };

  const updateGotify = (field: string, value: any) => {
    setConfig(prev => ({
      ...prev,
      gotify: { ...prev.gotify, [field]: value },
    }));
    setTestResult(null);
  };

  const updateNtfy = (field: string, value: any) => {
    setConfig(prev => ({
      ...prev,
      ntfy: { ...prev.ntfy, [field]: value },
    }));
    setTestResult(null);
  };

  // Test webhook
  const testDiscord = async () => {
    setIsTesting('discord');
    setTestResult(null);
    try {
      const response = await apiClient.testConnection('discord', {
        webhook_url: config.discord.webhook_url,
      }, false);
      setTestResult({ agent: 'discord', success: response.success, message: response.message });
    } catch (error: any) {
      setTestResult({ agent: 'discord', success: false, message: error.response?.data?.detail || 'Test failed' });
    } finally {
      setIsTesting(null);
    }
  };

  // Event toggle helpers
  const toggleEvent = (agent: 'discord' | 'pushover' | 'telegram' | 'gotify' | 'ntfy', event: string) => {
    const agentConfig = config[agent];
    const currentEvents = agentConfig.events || DEFAULT_EVENTS;
    const newEvents = currentEvents.includes(event)
      ? currentEvents.filter(e => e !== event)
      : [...currentEvents, event];

    setConfig(prev => ({
      ...prev,
      [agent]: { ...prev[agent], events: newEvents },
    }));
  };

  // Threshold updates
  const updateStreamCountThreshold = (value: string) => {
    const numValue = parseInt(value);
    setConfig(prev => ({
      ...prev,
      stream_count_threshold: isNaN(numValue) || numValue <= 0 ? null : numValue,
    }));
  };

  const updateStreamBitrateThreshold = (value: string) => {
    const numValue = parseFloat(value);
    setConfig(prev => ({
      ...prev,
      stream_bitrate_threshold: isNaN(numValue) || numValue <= 0 ? null : numValue,
    }));
  };

  // Check if any notification is enabled
  const anyEnabled = config.discord.enabled || config.pushover.enabled ||
    config.telegram.enabled || config.gotify.enabled || config.ntfy.enabled;

  if (readOnly) {
    const enabledAgents: string[] = [];
    if (config.discord.enabled) enabledAgents.push('Webhook');
    if (config.pushover.enabled) enabledAgents.push('Pushover');
    if (config.telegram.enabled) enabledAgents.push('Telegram');
    if (config.gotify.enabled) enabledAgents.push('Gotify');
    if (config.ntfy.enabled) enabledAgents.push('ntfy');

    return (
      <div className="space-y-4">
        <h3 className="font-medium">Notifications</h3>
        <div className="grid gap-2 text-sm">
          <div className="flex justify-between py-2 border-b">
            <span className="text-muted-foreground">Enabled Agents</span>
            <span>{enabledAgents.length > 0 ? enabledAgents.join(', ') : 'None'}</span>
          </div>
        </div>
      </div>
    );
  }

  return (
    <div className="space-y-6">
      <div className="text-center space-y-2">
        <h2 className="text-xl font-semibold">Notifications (Optional)</h2>
        <p className="text-sm text-muted-foreground">
          Get notified when streams start, end, or when issues occur.
        </p>
      </div>

      <div className="space-y-3 max-w-lg mx-auto">
        {/* Discord/Webhook */}
        <Collapsible
          open={openSections.includes('discord')}
          onOpenChange={() => toggleSection('discord')}
        >
          <div className="border rounded-lg">
            <CollapsibleTrigger asChild>
              <button type="button" className="flex items-center justify-between w-full p-4 hover:bg-muted/50">
              <div className="flex items-center gap-3">
                <MessageSquare className={`h-5 w-5 ${config.discord.enabled ? 'text-primary' : 'text-muted-foreground'}`} />
                <div className="text-left">
                  <div className="font-medium">Webhook (Discord/Slack)</div>
                  <div className="text-sm text-muted-foreground">
                    {config.discord.enabled ? 'Enabled' : 'Disabled'}
                  </div>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 transition-transform ${openSections.includes('discord') ? 'rotate-180' : ''}`} />
            </button>
              </CollapsibleTrigger>
            <CollapsibleContent className="p-4 pt-0 space-y-4">
              <div className="flex items-center justify-between">
                <Label>Enable Webhook Notifications</Label>
                <Switch
                  checked={config.discord.enabled}
                  onCheckedChange={(v) => updateDiscord('enabled', v)}
                  disabled={isLoading}
                />
              </div>
              {config.discord.enabled && (
                <>
                  <div className="space-y-2">
                    <Label>Webhook URL</Label>
                    <PasswordInput
                      value={config.discord.webhook_url}
                      onChange={(e) => updateDiscord('webhook_url', e.target.value)}
                      placeholder="https://discord.com/api/webhooks/..."
                      disabled={isLoading}
                      maxLength={512}
                    />
                  </div>
                  <Button
                    type="button"
                    variant="outline"
                    size="sm"
                    onClick={testDiscord}
                    disabled={isLoading || isTesting === 'discord' || !config.discord.webhook_url}
                  >
                    {isTesting === 'discord' && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
                    Test Webhook
                  </Button>
                  {testResult?.agent === 'discord' && (
                    <Alert variant={testResult.success ? 'default' : 'destructive'} className={testResult.success ? 'border-green-500' : ''}>
                      {testResult.success ? <CheckCircle className="h-4 w-4 text-green-600" /> : <XCircle className="h-4 w-4" />}
                      <AlertDescription className={testResult.success ? 'text-green-600' : ''}>{testResult.message}</AlertDescription>
                    </Alert>
                  )}

                  {/* Event Selection */}
                  <div className="space-y-2 pt-2 border-t">
                    <Label className="text-sm">Notification Events</Label>
                    <div className="space-y-2">
                      {AVAILABLE_EVENTS.map(event => (
                        <div key={event.value} className="space-y-1">
                          <div className="flex items-start space-x-2">
                            <Checkbox
                              id={`discord-${event.value}`}
                              checked={(config.discord.events || DEFAULT_EVENTS).includes(event.value)}
                              onCheckedChange={() => toggleEvent('discord', event.value)}
                            />
                            <div className="flex-1">
                              <label
                                htmlFor={`discord-${event.value}`}
                                className="text-sm leading-none cursor-pointer"
                              >
                                {event.label}
                              </label>
                              <p className="text-xs text-muted-foreground">{event.description}</p>
                            </div>
                          </div>
                          {event.value === 'stream_count_exceeded' && (config.discord.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_count_threshold || ''}
                                onChange={(e) => updateStreamCountThreshold(e.target.value)}
                                placeholder="3"
                              />
                              <span className="text-xs text-muted-foreground">streams</span>
                            </div>
                          )}
                          {event.value === 'stream_bitrate_exceeded' && (config.discord.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                step="0.1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_bitrate_threshold || ''}
                                onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                                placeholder="50"
                              />
                              <span className="text-xs text-muted-foreground">Mbps</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CollapsibleContent>
          </div>
        </Collapsible>

        {/* Pushover */}
        <Collapsible
          open={openSections.includes('pushover')}
          onOpenChange={() => toggleSection('pushover')}
        >
          <div className="border rounded-lg">
            <CollapsibleTrigger asChild>
              <button type="button" className="flex items-center justify-between w-full p-4 hover:bg-muted/50">
              <div className="flex items-center gap-3">
                <Bell className={`h-5 w-5 ${config.pushover.enabled ? 'text-primary' : 'text-muted-foreground'}`} />
                <div className="text-left">
                  <div className="font-medium">Pushover</div>
                  <div className="text-sm text-muted-foreground">
                    {config.pushover.enabled ? 'Enabled' : 'Disabled'}
                  </div>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 transition-transform ${openSections.includes('pushover') ? 'rotate-180' : ''}`} />
            </button>
              </CollapsibleTrigger>
            <CollapsibleContent className="p-4 pt-0 space-y-4">
              <div className="flex items-center justify-between">
                <Label>Enable Pushover</Label>
                <Switch
                  checked={config.pushover.enabled}
                  onCheckedChange={(v) => updatePushover('enabled', v)}
                  disabled={isLoading}
                />
              </div>
              {config.pushover.enabled && (
                <>
                  <div className="space-y-2">
                    <Label>User Key</Label>
                    <PasswordInput
                      value={config.pushover.user_key}
                      onChange={(e) => updatePushover('user_key', e.target.value)}
                      placeholder="Your Pushover user key"
                      disabled={isLoading}
                      maxLength={128}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>API Token</Label>
                    <PasswordInput
                      value={config.pushover.api_token}
                      onChange={(e) => updatePushover('api_token', e.target.value)}
                      placeholder="Your Pushover API token"
                      disabled={isLoading}
                      maxLength={128}
                    />
                  </div>

                  {/* Event Selection */}
                  <div className="space-y-2 pt-2 border-t">
                    <Label className="text-sm">Notification Events</Label>
                    <div className="space-y-2">
                      {AVAILABLE_EVENTS.map(event => (
                        <div key={event.value} className="space-y-1">
                          <div className="flex items-start space-x-2">
                            <Checkbox
                              id={`pushover-${event.value}`}
                              checked={(config.pushover.events || DEFAULT_EVENTS).includes(event.value)}
                              onCheckedChange={() => toggleEvent('pushover', event.value)}
                            />
                            <div className="flex-1">
                              <label
                                htmlFor={`pushover-${event.value}`}
                                className="text-sm leading-none cursor-pointer"
                              >
                                {event.label}
                              </label>
                              <p className="text-xs text-muted-foreground">{event.description}</p>
                            </div>
                          </div>
                          {event.value === 'stream_count_exceeded' && (config.pushover.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_count_threshold || ''}
                                onChange={(e) => updateStreamCountThreshold(e.target.value)}
                                placeholder="3"
                              />
                              <span className="text-xs text-muted-foreground">streams</span>
                            </div>
                          )}
                          {event.value === 'stream_bitrate_exceeded' && (config.pushover.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                step="0.1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_bitrate_threshold || ''}
                                onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                                placeholder="50"
                              />
                              <span className="text-xs text-muted-foreground">Mbps</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CollapsibleContent>
          </div>
        </Collapsible>

        {/* Telegram */}
        <Collapsible
          open={openSections.includes('telegram')}
          onOpenChange={() => toggleSection('telegram')}
        >
          <div className="border rounded-lg">
            <CollapsibleTrigger asChild>
              <button type="button" className="flex items-center justify-between w-full p-4 hover:bg-muted/50">
              <div className="flex items-center gap-3">
                <Send className={`h-5 w-5 ${config.telegram.enabled ? 'text-primary' : 'text-muted-foreground'}`} />
                <div className="text-left">
                  <div className="font-medium">Telegram</div>
                  <div className="text-sm text-muted-foreground">
                    {config.telegram.enabled ? 'Enabled' : 'Disabled'}
                  </div>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 transition-transform ${openSections.includes('telegram') ? 'rotate-180' : ''}`} />
            </button>
              </CollapsibleTrigger>
            <CollapsibleContent className="p-4 pt-0 space-y-4">
              <div className="flex items-center justify-between">
                <Label>Enable Telegram</Label>
                <Switch
                  checked={config.telegram.enabled}
                  onCheckedChange={(v) => updateTelegram('enabled', v)}
                  disabled={isLoading}
                />
              </div>
              {config.telegram.enabled && (
                <>
                  <div className="space-y-2">
                    <Label>Bot Token</Label>
                    <PasswordInput
                      value={config.telegram.bot_token}
                      onChange={(e) => updateTelegram('bot_token', e.target.value)}
                      placeholder="Get from @BotFather"
                      disabled={isLoading}
                      maxLength={128}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Chat ID</Label>
                    <Input
                      value={config.telegram.chat_id}
                      onChange={(e) => updateTelegram('chat_id', e.target.value)}
                      placeholder="Use @userinfobot to get your chat ID"
                      disabled={isLoading}
                      maxLength={100}
                    />
                  </div>

                  {/* Event Selection */}
                  <div className="space-y-2 pt-2 border-t">
                    <Label className="text-sm">Notification Events</Label>
                    <div className="space-y-2">
                      {AVAILABLE_EVENTS.map(event => (
                        <div key={event.value} className="space-y-1">
                          <div className="flex items-start space-x-2">
                            <Checkbox
                              id={`telegram-${event.value}`}
                              checked={(config.telegram.events || DEFAULT_EVENTS).includes(event.value)}
                              onCheckedChange={() => toggleEvent('telegram', event.value)}
                            />
                            <div className="flex-1">
                              <label
                                htmlFor={`telegram-${event.value}`}
                                className="text-sm leading-none cursor-pointer"
                              >
                                {event.label}
                              </label>
                              <p className="text-xs text-muted-foreground">{event.description}</p>
                            </div>
                          </div>
                          {event.value === 'stream_count_exceeded' && (config.telegram.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_count_threshold || ''}
                                onChange={(e) => updateStreamCountThreshold(e.target.value)}
                                placeholder="3"
                              />
                              <span className="text-xs text-muted-foreground">streams</span>
                            </div>
                          )}
                          {event.value === 'stream_bitrate_exceeded' && (config.telegram.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                step="0.1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_bitrate_threshold || ''}
                                onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                                placeholder="50"
                              />
                              <span className="text-xs text-muted-foreground">Mbps</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CollapsibleContent>
          </div>
        </Collapsible>

        {/* Gotify */}
        <Collapsible
          open={openSections.includes('gotify')}
          onOpenChange={() => toggleSection('gotify')}
        >
          <div className="border rounded-lg">
            <CollapsibleTrigger asChild>
              <button type="button" className="flex items-center justify-between w-full p-4 hover:bg-muted/50">
              <div className="flex items-center gap-3">
                <Server className={`h-5 w-5 ${config.gotify.enabled ? 'text-primary' : 'text-muted-foreground'}`} />
                <div className="text-left">
                  <div className="font-medium">Gotify</div>
                  <div className="text-sm text-muted-foreground">
                    {config.gotify.enabled ? 'Enabled' : 'Disabled'}
                  </div>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 transition-transform ${openSections.includes('gotify') ? 'rotate-180' : ''}`} />
            </button>
              </CollapsibleTrigger>
            <CollapsibleContent className="p-4 pt-0 space-y-4">
              <div className="flex items-center justify-between">
                <Label>Enable Gotify</Label>
                <Switch
                  checked={config.gotify.enabled}
                  onCheckedChange={(v) => updateGotify('enabled', v)}
                  disabled={isLoading}
                />
              </div>
              {config.gotify.enabled && (
                <>
                  <div className="space-y-2">
                    <Label>Server URL</Label>
                    <Input
                      type="url"
                      value={config.gotify.server_url}
                      onChange={(e) => updateGotify('server_url', e.target.value)}
                      placeholder="https://gotify.yourdomain.com"
                      disabled={isLoading}
                      maxLength={512}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Application Token</Label>
                    <PasswordInput
                      value={config.gotify.app_token}
                      onChange={(e) => updateGotify('app_token', e.target.value)}
                      placeholder="Your Gotify app token"
                      disabled={isLoading}
                      maxLength={128}
                    />
                  </div>

                  {/* Event Selection */}
                  <div className="space-y-2 pt-2 border-t">
                    <Label className="text-sm">Notification Events</Label>
                    <div className="space-y-2">
                      {AVAILABLE_EVENTS.map(event => (
                        <div key={event.value} className="space-y-1">
                          <div className="flex items-start space-x-2">
                            <Checkbox
                              id={`gotify-${event.value}`}
                              checked={(config.gotify.events || DEFAULT_EVENTS).includes(event.value)}
                              onCheckedChange={() => toggleEvent('gotify', event.value)}
                            />
                            <div className="flex-1">
                              <label
                                htmlFor={`gotify-${event.value}`}
                                className="text-sm leading-none cursor-pointer"
                              >
                                {event.label}
                              </label>
                              <p className="text-xs text-muted-foreground">{event.description}</p>
                            </div>
                          </div>
                          {event.value === 'stream_count_exceeded' && (config.gotify.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_count_threshold || ''}
                                onChange={(e) => updateStreamCountThreshold(e.target.value)}
                                placeholder="3"
                              />
                              <span className="text-xs text-muted-foreground">streams</span>
                            </div>
                          )}
                          {event.value === 'stream_bitrate_exceeded' && (config.gotify.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                step="0.1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_bitrate_threshold || ''}
                                onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                                placeholder="50"
                              />
                              <span className="text-xs text-muted-foreground">Mbps</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CollapsibleContent>
          </div>
        </Collapsible>

        {/* ntfy */}
        <Collapsible
          open={openSections.includes('ntfy')}
          onOpenChange={() => toggleSection('ntfy')}
        >
          <div className="border rounded-lg">
            <CollapsibleTrigger asChild>
              <button type="button" className="flex items-center justify-between w-full p-4 hover:bg-muted/50">
              <div className="flex items-center gap-3">
                <Radio className={`h-5 w-5 ${config.ntfy.enabled ? 'text-primary' : 'text-muted-foreground'}`} />
                <div className="text-left">
                  <div className="font-medium">ntfy</div>
                  <div className="text-sm text-muted-foreground">
                    {config.ntfy.enabled ? 'Enabled' : 'Disabled'}
                  </div>
                </div>
              </div>
              <ChevronDown className={`h-4 w-4 transition-transform ${openSections.includes('ntfy') ? 'rotate-180' : ''}`} />
            </button>
              </CollapsibleTrigger>
            <CollapsibleContent className="p-4 pt-0 space-y-4">
              <div className="flex items-center justify-between">
                <Label>Enable ntfy</Label>
                <Switch
                  checked={config.ntfy.enabled}
                  onCheckedChange={(v) => updateNtfy('enabled', v)}
                  disabled={isLoading}
                />
              </div>
              {config.ntfy.enabled && (
                <>
                  <div className="space-y-2">
                    <Label>Server URL</Label>
                    <Input
                      type="url"
                      value={config.ntfy.server_url}
                      onChange={(e) => updateNtfy('server_url', e.target.value)}
                      placeholder="https://ntfy.sh"
                      disabled={isLoading}
                      maxLength={512}
                    />
                  </div>
                  <div className="space-y-2">
                    <Label>Topic</Label>
                    <Input
                      value={config.ntfy.topic}
                      onChange={(e) => updateNtfy('topic', e.target.value)}
                      placeholder="speedarr-notifications"
                      disabled={isLoading}
                      maxLength={100}
                    />
                    <p className="text-xs text-muted-foreground">
                      Subscribe to this topic in the ntfy app
                    </p>
                  </div>

                  {/* Event Selection */}
                  <div className="space-y-2 pt-2 border-t">
                    <Label className="text-sm">Notification Events</Label>
                    <div className="space-y-2">
                      {AVAILABLE_EVENTS.map(event => (
                        <div key={event.value} className="space-y-1">
                          <div className="flex items-start space-x-2">
                            <Checkbox
                              id={`ntfy-${event.value}`}
                              checked={(config.ntfy.events || DEFAULT_EVENTS).includes(event.value)}
                              onCheckedChange={() => toggleEvent('ntfy', event.value)}
                            />
                            <div className="flex-1">
                              <label
                                htmlFor={`ntfy-${event.value}`}
                                className="text-sm leading-none cursor-pointer"
                              >
                                {event.label}
                              </label>
                              <p className="text-xs text-muted-foreground">{event.description}</p>
                            </div>
                          </div>
                          {event.value === 'stream_count_exceeded' && (config.ntfy.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_count_threshold || ''}
                                onChange={(e) => updateStreamCountThreshold(e.target.value)}
                                placeholder="3"
                              />
                              <span className="text-xs text-muted-foreground">streams</span>
                            </div>
                          )}
                          {event.value === 'stream_bitrate_exceeded' && (config.ntfy.events || DEFAULT_EVENTS).includes(event.value) && (
                            <div className="flex items-center gap-2 ml-6">
                              <Label className="text-xs">Threshold:</Label>
                              <Input
                                type="number"
                                min="1"
                                step="0.1"
                                className="w-20 h-7 text-sm"
                                value={config.stream_bitrate_threshold || ''}
                                onChange={(e) => updateStreamBitrateThreshold(e.target.value)}
                                placeholder="50"
                              />
                              <span className="text-xs text-muted-foreground">Mbps</span>
                            </div>
                          )}
                        </div>
                      ))}
                    </div>
                  </div>
                </>
              )}
            </CollapsibleContent>
          </div>
        </Collapsible>
      </div>

      {/* Skip reminder */}
      {!anyEnabled && (
        <div className="text-center">
          <p className="text-sm text-muted-foreground">
            You can skip this step and configure notifications later in Settings.
          </p>
        </div>
      )}
    </div>
  );
};

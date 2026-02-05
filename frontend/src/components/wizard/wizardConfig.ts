/**
 * Wizard step configuration
 *
 * TO REORDER STEPS: Simply change the order of items in the WIZARD_STEPS array.
 * The wizard will automatically update navigation, progress indicator, and validation flow.
 */

import { Rocket, Server, Download, Gauge, Activity, Bell, CheckCircle } from 'lucide-react';
import { WizardStepConfig, WizardState, ValidationResult } from './types';
import { WelcomeStep } from './steps/WelcomeStep';
import { PlexStep } from './steps/PlexStep';
import { DownloadClientsStep } from './steps/DownloadClientsStep';
import { BandwidthStep } from './steps/BandwidthStep';
import { SNMPStep } from './steps/SNMPStep';
import { NotificationsStep } from './steps/NotificationsStep';
import { SummaryStep } from './steps/SummaryStep';

// Validation functions for each step
export const validatePlex = async (state: WizardState): Promise<ValidationResult> => {
  const errors: string[] = [];

  if (!state.plex) {
    errors.push('Plex configuration is required');
    return { valid: false, errors };
  }

  if (!state.plex.url || state.plex.url.trim() === '') {
    errors.push('Plex server URL is required');
  }

  if (!state.plex.token || state.plex.token.trim() === '') {
    errors.push('Plex token is required');
  }

  return { valid: errors.length === 0, errors };
};

export const validateDownloadClients = async (state: WizardState): Promise<ValidationResult> => {
  const errors: string[] = [];

  if (!state.downloadClients || state.downloadClients.length === 0) {
    errors.push('At least one download client is required');
    return { valid: false, errors };
  }

  const enabledClients = state.downloadClients.filter(c => c.enabled);
  if (enabledClients.length === 0) {
    errors.push('At least one download client must be enabled');
  }

  return { valid: errors.length === 0, errors };
};

export const validateBandwidth = async (state: WizardState): Promise<ValidationResult> => {
  const errors: string[] = [];

  if (!state.bandwidth) {
    errors.push('Bandwidth configuration is required');
    return { valid: false, errors };
  }

  if (!state.bandwidth.download.total_limit || state.bandwidth.download.total_limit <= 0) {
    errors.push('Download limit must be greater than 0');
  }

  if (!state.bandwidth.upload.total_limit || state.bandwidth.upload.total_limit <= 0) {
    errors.push('Upload limit must be greater than 0');
  }

  return { valid: errors.length === 0, errors };
};

export const validateSNMP = async (state: WizardState): Promise<ValidationResult> => {
  const errors: string[] = [];

  // SNMP is optional - if not enabled, always valid
  if (!state.snmp?.enabled) {
    return { valid: true, errors: [] };
  }

  if (!state.snmp.host || state.snmp.host.trim() === '') {
    errors.push('SNMP host is required when SNMP is enabled');
  }

  return { valid: errors.length === 0, errors };
};

export const validateNotifications = async (state: WizardState): Promise<ValidationResult> => {
  const errors: string[] = [];

  // Notifications are optional - if not enabled, always valid
  if (!state.notifications?.discord?.enabled) {
    return { valid: true, errors: [] };
  }

  if (!state.notifications.discord.webhook_url || state.notifications.discord.webhook_url.trim() === '') {
    errors.push('Discord webhook URL is required when notifications are enabled');
  }

  return { valid: errors.length === 0, errors };
};

/**
 * WIZARD STEPS CONFIGURATION
 *
 * To change the order of steps, simply rearrange the items in this array.
 * Each step has:
 * - id: Unique identifier
 * - title: Display name
 * - description: Short description for progress indicator
 * - icon: Lucide icon component
 * - component: React component to render
 * - required: Whether this step must be completed
 * - validate: Optional validation function
 * - shouldSkip: Optional function to determine if step should be skipped
 */
export const WIZARD_STEPS: WizardStepConfig[] = [
  {
    id: 'welcome',
    title: 'Welcome',
    description: 'Get started with Speedarr',
    icon: Rocket,
    component: WelcomeStep,
    required: true,
  },
  {
    id: 'plex',
    title: 'Plex',
    description: 'Connect to Plex',
    icon: Server,
    component: PlexStep,
    required: true,
    validate: validatePlex,
  },
  {
    id: 'download-clients',
    title: 'Download Client',
    description: 'Add download client',
    icon: Download,
    component: DownloadClientsStep,
    required: true,
    validate: validateDownloadClients,
  },
  {
    id: 'bandwidth',
    title: 'Bandwidth',
    description: 'Set bandwidth limits',
    icon: Gauge,
    component: BandwidthStep,
    required: true,
    validate: validateBandwidth,
  },
  {
    id: 'snmp',
    title: 'SNMP',
    description: 'Optional network monitoring',
    icon: Activity,
    component: SNMPStep,
    required: false,
    validate: validateSNMP,
  },
  {
    id: 'notifications',
    title: 'Notifications',
    description: 'Optional Discord alerts',
    icon: Bell,
    component: NotificationsStep,
    required: false,
    validate: validateNotifications,
  },
  {
    id: 'summary',
    title: 'Summary',
    description: 'Review and finish',
    icon: CheckCircle,
    component: SummaryStep,
    required: true,
  },
];

// Helper to get step by ID
export const getStepById = (id: string): WizardStepConfig | undefined => {
  return WIZARD_STEPS.find(step => step.id === id);
};

// Helper to get step index by ID
export const getStepIndex = (id: string): number => {
  return WIZARD_STEPS.findIndex(step => step.id === id);
};

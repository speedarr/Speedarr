/**
 * Wizard TypeScript interfaces and types
 */

import { LucideIcon } from 'lucide-react';

// Download client configuration
export interface DownloadClientConfig {
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

// Speedarr URL configuration
export interface SpeedarrConfig {
  url: string;
}

// Plex configuration
export interface PlexConfig {
  url: string;
  token: string;
}

// Bandwidth configuration with client allocation percentages
export interface BandwidthConfig {
  download: {
    total_limit: number;
    client_percents?: Record<string, number>;
  };
  upload: {
    total_limit: number;
    upload_client_percents?: Record<string, number>;
  };
}

// Notifications configuration - all notification agents
export interface NotificationsConfig {
  discord: {
    enabled: boolean;
    webhook_url: string;
    events?: string[];
  };
  pushover: {
    enabled: boolean;
    user_key: string;
    api_token: string;
    events?: string[];
  };
  telegram: {
    enabled: boolean;
    bot_token: string;
    chat_id: string;
    events?: string[];
  };
  gotify: {
    enabled: boolean;
    server_url: string;
    app_token: string;
    events?: string[];
  };
  ntfy: {
    enabled: boolean;
    server_url: string;
    topic: string;
    events?: string[];
  };
  stream_count_threshold?: number | null;
  stream_bitrate_threshold?: number | null;
}

// SNMP configuration (simplified for wizard)
export interface SNMPConfig {
  enabled: boolean;
  host: string;
  port: number;
  version: string;
  community: string;
  interface: string;
}

// Complete wizard state containing all configuration data
export interface WizardState {
  speedarr: SpeedarrConfig | null;
  plex: PlexConfig | null;
  downloadClients: DownloadClientConfig[];
  bandwidth: BandwidthConfig | null;
  notifications: NotificationsConfig | null;
  snmp: SNMPConfig | null;
  completedSteps: string[];
}

// Validation result returned by step validators
export interface ValidationResult {
  valid: boolean;
  errors: string[];
  warnings?: string[];
}

// Props passed to each step component
export interface WizardStepProps {
  // Current data for this step from wizard state
  data: any;
  // Called when step data changes
  onDataChange: (data: any) => void;
  // Whether validation should be shown (after attempted navigation)
  showValidation: boolean;
  // Current validation errors
  errors: string[];
  // Loading state during async operations
  isLoading: boolean;
  // Read-only mode for review/summary
  readOnly?: boolean;
}

// Configuration for a wizard step
export interface WizardStepConfig {
  // Unique identifier for the step
  id: string;
  // Display title
  title: string;
  // Short description shown in progress
  description: string;
  // Icon component from lucide-react
  icon: LucideIcon;
  // React component to render for this step
  component: React.ComponentType<WizardStepProps>;
  // Whether this step is required to complete wizard
  required: boolean;
  // Optional function to determine if step should be skipped
  shouldSkip?: (state: WizardState) => boolean;
  // Optional validation function for the step
  validate?: (state: WizardState) => Promise<ValidationResult>;
}

// Wizard context value type
export interface WizardContextType {
  // Current step index
  currentStepIndex: number;
  // All step configurations
  steps: WizardStepConfig[];
  // Current wizard state with all config data
  state: WizardState;
  // Navigation functions
  goToStep: (index: number) => void;
  goNext: () => Promise<boolean>;
  goBack: () => void;
  canGoBack: boolean;
  canGoNext: boolean;
  // State updates
  updateState: (partial: Partial<WizardState>) => void;
  markStepComplete: (stepId: string) => void;
  // Validation
  validateCurrentStep: () => Promise<ValidationResult>;
  validationErrors: string[];
  showValidation: boolean;
  // Loading state
  isValidating: boolean;
  isSaving: boolean;
  // Completion
  isComplete: boolean;
  finishWizard: () => Promise<void>;
}

// Default empty wizard state
export const DEFAULT_WIZARD_STATE: WizardState = {
  speedarr: null,
  plex: null,
  downloadClients: [],
  bandwidth: null,
  notifications: null,
  snmp: null,
  completedSteps: [],
};

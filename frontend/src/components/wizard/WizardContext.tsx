/**
 * Wizard Context Provider
 *
 * Manages wizard state, navigation, validation, and localStorage persistence.
 */

import React, { createContext, useContext, useState, useEffect, useCallback, ReactNode } from 'react';
import { useNavigate } from 'react-router-dom';
import { WizardContextType, WizardState, ValidationResult, DEFAULT_WIZARD_STATE } from './types';
import { WIZARD_STEPS } from './wizardConfig';
import { apiClient } from '@/api/client';

const STORAGE_KEY = 'speedarr_wizard_state';

const WizardContext = createContext<WizardContextType | undefined>(undefined);

export const useWizard = () => {
  const context = useContext(WizardContext);
  if (!context) {
    throw new Error('useWizard must be used within a WizardProvider');
  }
  return context;
};

interface WizardProviderProps {
  children: ReactNode;
}

export const WizardProvider: React.FC<WizardProviderProps> = ({ children }) => {
  const navigate = useNavigate();

  // Load initial state from localStorage or use defaults
  const loadInitialState = (): WizardState => {
    try {
      const stored = localStorage.getItem(STORAGE_KEY);
      if (stored) {
        const parsed = JSON.parse(stored);
        return { ...DEFAULT_WIZARD_STATE, ...parsed };
      }
    } catch (e) {
      console.error('Failed to load wizard state from localStorage:', e);
    }
    return { ...DEFAULT_WIZARD_STATE };
  };

  const [currentStepIndex, setCurrentStepIndex] = useState(0);
  const [state, setState] = useState<WizardState>(loadInitialState);
  const [validationErrors, setValidationErrors] = useState<string[]>([]);
  const [showValidation, setShowValidation] = useState(false);
  const [isValidating, setIsValidating] = useState(false);
  const [isSaving, setIsSaving] = useState(false);

  // Persist state to localStorage whenever it changes
  useEffect(() => {
    try {
      localStorage.setItem(STORAGE_KEY, JSON.stringify(state));
    } catch (e) {
      console.error('Failed to save wizard state to localStorage:', e);
    }
  }, [state]);

  // Get current step configuration
  const currentStep = WIZARD_STEPS[currentStepIndex];

  // Update wizard state
  const updateState = useCallback((partial: Partial<WizardState>) => {
    setState(prev => ({ ...prev, ...partial }));
  }, []);

  // Mark a step as complete
  const markStepComplete = useCallback((stepId: string) => {
    setState(prev => {
      if (prev.completedSteps.includes(stepId)) return prev;
      return {
        ...prev,
        completedSteps: [...prev.completedSteps, stepId],
      };
    });
  }, []);

  // Validate current step
  const validateCurrentStep = useCallback(async (): Promise<ValidationResult> => {
    const step = WIZARD_STEPS[currentStepIndex];

    // If no validation function, step is valid
    if (!step.validate) {
      return { valid: true, errors: [] };
    }

    setIsValidating(true);
    try {
      const result = await step.validate(state);
      setValidationErrors(result.errors);
      return result;
    } catch (e) {
      const error = 'Validation failed unexpectedly';
      setValidationErrors([error]);
      return { valid: false, errors: [error] };
    } finally {
      setIsValidating(false);
    }
  }, [currentStepIndex, state]);

  // Navigate to a specific step
  const goToStep = useCallback((index: number) => {
    if (index >= 0 && index < WIZARD_STEPS.length) {
      setCurrentStepIndex(index);
      setShowValidation(false);
      setValidationErrors([]);
    }
  }, []);

  // Navigate to next step
  const goNext = useCallback(async (): Promise<boolean> => {
    setShowValidation(true);

    // Validate current step
    const validation = await validateCurrentStep();
    if (!validation.valid) {
      return false;
    }

    // Mark current step as complete
    markStepComplete(currentStep.id);

    // Find next non-skipped step
    let nextIndex = currentStepIndex + 1;
    while (nextIndex < WIZARD_STEPS.length) {
      const nextStep = WIZARD_STEPS[nextIndex];
      if (nextStep.shouldSkip && nextStep.shouldSkip(state)) {
        nextIndex++;
      } else {
        break;
      }
    }

    // If we've gone past the last step, we're at the end
    if (nextIndex >= WIZARD_STEPS.length) {
      return true; // Signal completion
    }

    setCurrentStepIndex(nextIndex);
    setShowValidation(false);
    setValidationErrors([]);
    return true;
  }, [currentStepIndex, currentStep, state, validateCurrentStep, markStepComplete]);

  // Navigate to previous step
  const goBack = useCallback(() => {
    // Find previous non-skipped step
    let prevIndex = currentStepIndex - 1;
    while (prevIndex >= 0) {
      const prevStep = WIZARD_STEPS[prevIndex];
      if (prevStep.shouldSkip && prevStep.shouldSkip(state)) {
        prevIndex--;
      } else {
        break;
      }
    }

    if (prevIndex >= 0) {
      setCurrentStepIndex(prevIndex);
      setShowValidation(false);
      setValidationErrors([]);
    }
  }, [currentStepIndex, state]);

  // Check if we can navigate back
  const canGoBack = currentStepIndex > 0;

  // Check if we can navigate forward (not at last step)
  const canGoNext = currentStepIndex < WIZARD_STEPS.length - 1;

  // Check if wizard is complete (all required steps done)
  const isComplete = WIZARD_STEPS
    .filter(step => step.required)
    .every(step => state.completedSteps.includes(step.id));

  // Finish wizard - save all config and redirect to dashboard
  const finishWizard = useCallback(async () => {
    setIsSaving(true);
    try {
      // Initialize default config first (required for fresh setups)
      await apiClient.initializeConfig();

      // Save Plex settings
      if (state.plex) {
        await apiClient.updateSettingsSection('plex', state.plex);
      }

      // Save download clients
      if (state.downloadClients && state.downloadClients.length > 0) {
        await apiClient.updateDownloadClients(state.downloadClients);
      }

      // Save bandwidth settings with client allocation percentages
      if (state.bandwidth) {
        await apiClient.updateSettingsSection('bandwidth', {
          download: {
            total_limit: state.bandwidth.download.total_limit,
            inactive_safety_net_percent: 5,
            client_percents: state.bandwidth.download.client_percents || {},
          },
          upload: {
            total_limit: state.bandwidth.upload.total_limit,
            upload_client_percents: state.bandwidth.upload.upload_client_percents || {},
          },
          streams: {
            bandwidth_calculation: 'auto',
            manual_per_stream: 8,
            overhead_percent: 100,
          },
        });

        // Set failsafe speeds to 10% of configured bandwidth
        const failsafeDownload = Math.round(state.bandwidth.download.total_limit * 0.1 * 10) / 10;
        const failsafeUpload = Math.round(state.bandwidth.upload.total_limit * 0.1 * 10) / 10;

        await apiClient.updateSettingsSection('failsafe', {
          enabled: true,
          shutdown_download_speed: failsafeDownload,
          shutdown_upload_speed: failsafeUpload,
          shutdown_delay: 30,
          restoration_delay: 60,
          minimum_holding_time: 120,
        });
      }

      // Save notifications settings if any agent is enabled
      const notifications = state.notifications;
      const anyNotificationEnabled = notifications?.discord?.enabled ||
        notifications?.pushover?.enabled || notifications?.telegram?.enabled ||
        notifications?.gotify?.enabled || notifications?.ntfy?.enabled;

      if (anyNotificationEnabled) {
        const defaultEvents = ['stream_started', 'stream_ended', 'failsafe_triggered', 'service_error'];

        await apiClient.updateSettingsSection('notifications', {
          discord: {
            enabled: notifications?.discord?.enabled || false,
            webhook_url: notifications?.discord?.webhook_url || '',
            events: notifications?.discord?.events || defaultEvents,
            rate_limit: 60,
          },
          pushover: {
            enabled: notifications?.pushover?.enabled || false,
            user_key: notifications?.pushover?.user_key || '',
            api_token: notifications?.pushover?.api_token || '',
            priority: 0,
            events: notifications?.pushover?.events || defaultEvents,
          },
          telegram: {
            enabled: notifications?.telegram?.enabled || false,
            bot_token: notifications?.telegram?.bot_token || '',
            chat_id: notifications?.telegram?.chat_id || '',
            events: notifications?.telegram?.events || defaultEvents,
          },
          gotify: {
            enabled: notifications?.gotify?.enabled || false,
            server_url: notifications?.gotify?.server_url || '',
            app_token: notifications?.gotify?.app_token || '',
            priority: 5,
            events: notifications?.gotify?.events || defaultEvents,
          },
          ntfy: {
            enabled: notifications?.ntfy?.enabled || false,
            server_url: notifications?.ntfy?.server_url || 'https://ntfy.sh',
            topic: notifications?.ntfy?.topic || '',
            priority: 3,
            events: notifications?.ntfy?.events || defaultEvents,
          },
          stream_count_threshold: notifications?.stream_count_threshold ?? null,
          stream_bitrate_threshold: notifications?.stream_bitrate_threshold ?? null,
        });
      }

      // Save SNMP settings if enabled
      if (state.snmp?.enabled) {
        await apiClient.updateSettingsSection('snmp', {
          enabled: true,
          host: state.snmp.host,
          port: state.snmp.port,
          version: state.snmp.version,
          community: state.snmp.community,
          interface: state.snmp.interface || '',
          // SNMPv3 fields with defaults
          username: '',
          auth_protocol: 'none',
          auth_password: '',
          priv_protocol: 'none',
          priv_password: '',
        });
      }

      // Call complete-setup endpoint to initialize services
      await apiClient.completeSetup();

      // Clear localStorage
      localStorage.removeItem(STORAGE_KEY);

      // Hard redirect to dashboard (ensures fresh state)
      window.location.href = '/';
    } catch (e) {
      console.error('Failed to complete setup:', e);
      throw e;
    } finally {
      setIsSaving(false);
    }
  }, [state, navigate]);

  const value: WizardContextType = {
    currentStepIndex,
    steps: WIZARD_STEPS,
    state,
    goToStep,
    goNext,
    goBack,
    canGoBack,
    canGoNext,
    updateState,
    markStepComplete,
    validateCurrentStep,
    validationErrors,
    showValidation,
    isValidating,
    isSaving,
    isComplete,
    finishWizard,
  };

  return (
    <WizardContext.Provider value={value}>
      {children}
    </WizardContext.Provider>
  );
};

/**
 * SetupWizard - Main wizard container component
 *
 * Renders the wizard UI including progress indicator, current step, and navigation.
 */

import React from 'react';
import { Card, CardContent, CardHeader, CardTitle } from '@/components/ui/card';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { AlertCircle, Loader2 } from 'lucide-react';
import { WizardProvider, useWizard } from './WizardContext';
import { WizardProgress } from './WizardProgress';
import { WizardNavigation } from './WizardNavigation';

// Inner component that uses the wizard context
const WizardContent: React.FC = () => {
  const {
    currentStepIndex,
    steps,
    state,
    updateState,
    showValidation,
    validationErrors,
    isValidating,
    isSaving,
  } = useWizard();

  const currentStep = steps[currentStepIndex];
  const StepComponent = currentStep.component;

  // Get the appropriate data for the current step
  const getStepData = () => {
    switch (currentStep.id) {
      case 'speedarr-url':
        return state.speedarr;
      case 'plex':
        return state.plex;
      case 'download-clients':
        return state.downloadClients;
      case 'bandwidth':
        return state.bandwidth;
      case 'notifications':
        return state.notifications;
      case 'summary':
        return state; // Pass entire state for summary
      default:
        return null;
    }
  };

  // Handle data changes from step components
  const handleDataChange = (data: any) => {
    switch (currentStep.id) {
      case 'speedarr-url':
        updateState({ speedarr: data });
        break;
      case 'plex':
        updateState({ plex: data });
        break;
      case 'download-clients':
        updateState({ downloadClients: data });
        break;
      case 'bandwidth':
        updateState({ bandwidth: data });
        break;
      case 'notifications':
        updateState({ notifications: data });
        break;
    }
  };

  return (
    <div className="min-h-screen bg-background flex items-center justify-center p-4">
      <Card className="w-full max-w-3xl">
        <CardHeader className="text-center border-b pb-6">
          <div className="flex items-center justify-center gap-3 mb-4">
            <img src="/speedarr.svg" alt="Speedarr" className="h-10 w-10" />
            <CardTitle className="text-2xl">Speedarr Setup</CardTitle>
          </div>
          <WizardProgress />
        </CardHeader>

        <CardContent className="p-6 min-h-[400px]">
          {/* Error display */}
          {showValidation && validationErrors.length > 0 && (
            <Alert variant="destructive" className="mb-6">
              <AlertCircle className="h-4 w-4" />
              <AlertDescription>
                <ul className="list-disc list-inside">
                  {validationErrors.map((error, index) => (
                    <li key={index}>{error}</li>
                  ))}
                </ul>
              </AlertDescription>
            </Alert>
          )}

          {/* Loading overlay */}
          {(isValidating || isSaving) && (
            <div className="absolute inset-0 bg-background/50 flex items-center justify-center z-10">
              <Loader2 className="h-8 w-8 animate-spin text-primary" />
            </div>
          )}

          {/* Current step content */}
          <div className="relative">
            <StepComponent
              data={getStepData()}
              onDataChange={handleDataChange}
              showValidation={showValidation}
              errors={validationErrors}
              isLoading={isValidating || isSaving}
            />
          </div>
        </CardContent>

        <div className="border-t p-4">
          <WizardNavigation />
        </div>
      </Card>
    </div>
  );
};

// Main exported component wraps content with provider
export const SetupWizard: React.FC = () => {
  return (
    <WizardProvider>
      <WizardContent />
    </WizardProvider>
  );
};

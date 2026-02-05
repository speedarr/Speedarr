/**
 * WizardNavigation - Navigation buttons for the wizard
 *
 * Provides Back, Skip, and Next/Finish buttons based on current step.
 */

import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Loader2, ChevronLeft, ChevronRight, Check, SkipForward } from 'lucide-react';
import { useWizard } from './WizardContext';

export const WizardNavigation: React.FC = () => {
  const {
    currentStepIndex,
    steps,
    canGoBack,
    goBack,
    goNext,
    finishWizard,
    isValidating,
    isSaving,
  } = useWizard();

  const [error, setError] = useState<string | null>(null);

  const currentStep = steps[currentStepIndex];
  const isLastStep = currentStepIndex === steps.length - 1;
  const isOptional = !currentStep.required;
  const isLoading = isValidating || isSaving;

  const handleNext = async () => {
    setError(null);
    try {
      await goNext();
    } catch (e) {
      setError('Failed to proceed. Please check your inputs.');
    }
  };

  const handleSkip = async () => {
    setError(null);
    // Skip validation and go to next step
    const nextIndex = currentStepIndex + 1;
    if (nextIndex < steps.length) {
      // Use goToStep indirectly by calling goNext which handles skip logic
      // For skip, we just move forward without validation
      await goNext();
    }
  };

  const handleFinish = async () => {
    setError(null);
    try {
      await finishWizard();
    } catch (e: any) {
      setError(e.response?.data?.detail || 'Failed to complete setup. Please try again.');
    }
  };

  return (
    <div className="flex items-center justify-between">
      {/* Back button */}
      <div>
        {canGoBack && (
          <Button
            variant="outline"
            onClick={goBack}
            disabled={isLoading}
          >
            <ChevronLeft className="h-4 w-4 mr-1" />
            Back
          </Button>
        )}
      </div>

      {/* Error message */}
      {error && (
        <p className="text-sm text-destructive flex-1 text-center px-4">{error}</p>
      )}

      {/* Forward buttons */}
      <div className="flex items-center gap-2">
        {/* Skip button for optional steps */}
        {isOptional && !isLastStep && (
          <Button
            variant="ghost"
            onClick={handleSkip}
            disabled={isLoading}
          >
            Skip
            <SkipForward className="h-4 w-4 ml-1" />
          </Button>
        )}

        {/* Next / Finish button */}
        {isLastStep ? (
          <Button
            onClick={handleFinish}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : (
              <Check className="h-4 w-4 mr-2" />
            )}
            Complete Setup
          </Button>
        ) : (
          <Button
            onClick={handleNext}
            disabled={isLoading}
          >
            {isLoading ? (
              <Loader2 className="h-4 w-4 mr-2 animate-spin" />
            ) : null}
            Next
            <ChevronRight className="h-4 w-4 ml-1" />
          </Button>
        )}
      </div>
    </div>
  );
};

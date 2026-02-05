/**
 * WizardProgress - Step progress indicator
 *
 * Shows all wizard steps with visual indication of current, completed, and optional steps.
 */

import React from 'react';
import { Check } from 'lucide-react';
import { cn } from '@/lib/utils';
import { useWizard } from './WizardContext';

export const WizardProgress: React.FC = () => {
  const { steps, currentStepIndex, state, goToStep } = useWizard();

  return (
    <div className="w-full">
      {/* Progress steps - unified layout for icon/text alignment */}
      <div className="flex justify-between items-start w-full">
        {steps.map((step, index) => {
          const isComplete = state.completedSteps.includes(step.id);
          const isCurrent = index === currentStepIndex;
          const isOptional = !step.required;
          const canNavigate = isComplete || index <= currentStepIndex;
          const Icon = step.icon;
          const prevStepComplete = index > 0 && state.completedSteps.includes(steps[index - 1].id);

          return (
            <React.Fragment key={step.id}>
              {/* Connecting line - before each step except the first */}
              {index > 0 && (
                <div
                  className={cn(
                    'flex-1 h-0.5 self-center mx-1',
                    'mt-5', // Align with center of icon (w-10 h-10 = 40px, half = 20px = mt-5)
                    prevStepComplete ? 'bg-primary' : 'bg-muted'
                  )}
                />
              )}

              {/* Step column - icon and text vertically aligned */}
              <div className="flex flex-col items-center">
                {/* Step indicator */}
                <button
                  onClick={() => canNavigate && goToStep(index)}
                  disabled={!canNavigate}
                  className={cn(
                    'relative flex items-center justify-center w-10 h-10 rounded-full transition-all',
                    'focus:outline-none focus:ring-2 focus:ring-primary focus:ring-offset-2',
                    isCurrent && 'bg-primary text-primary-foreground ring-2 ring-primary ring-offset-2 ring-offset-background',
                    isComplete && !isCurrent && 'bg-primary text-primary-foreground',
                    !isComplete && !isCurrent && 'bg-muted text-muted-foreground',
                    isOptional && !isComplete && !isCurrent && 'border-2 border-dashed border-muted-foreground',
                    canNavigate && !isCurrent && 'hover:opacity-80 cursor-pointer',
                    !canNavigate && 'cursor-not-allowed opacity-60'
                  )}
                  title={step.title}
                >
                  {isComplete ? (
                    <Check className="h-5 w-5" />
                  ) : (
                    <Icon className="h-5 w-5" />
                  )}
                </button>

                {/* Step label - hidden on mobile */}
                <div
                  className={cn(
                    'hidden sm:block text-xs text-center mt-2 w-20',
                    isCurrent ? 'text-primary font-medium' : 'text-muted-foreground',
                    isOptional && 'italic'
                  )}
                >
                  {step.title}
                  {isOptional && <span className="block text-[10px]">(Optional)</span>}
                </div>
              </div>
            </React.Fragment>
          );
        })}
      </div>

      {/* Current step title - visible on mobile */}
      <div className="sm:hidden text-center mt-4">
        <h3 className="text-lg font-medium">{steps[currentStepIndex].title}</h3>
        <p className="text-sm text-muted-foreground">{steps[currentStepIndex].description}</p>
      </div>
    </div>
  );
};

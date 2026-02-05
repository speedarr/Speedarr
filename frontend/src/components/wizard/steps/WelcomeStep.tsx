/**
 * WelcomeStep - Introduction to the setup wizard
 */

import React from 'react';
import { Rocket } from 'lucide-react';
import { WizardStepProps } from '../types';

export const WelcomeStep: React.FC<WizardStepProps> = () => {
  return (
    <div className="text-center space-y-6">
      <div className="flex justify-center">
        <div className="h-20 w-20 rounded-full bg-primary/10 flex items-center justify-center">
          <Rocket className="h-10 w-10 text-primary" />
        </div>
      </div>

      <div className="space-y-2">
        <h2 className="text-2xl font-bold">Welcome to Speedarr</h2>
        <p className="text-muted-foreground max-w-md mx-auto">
          Intelligent bandwidth management for your Plex server. This wizard will help you
          configure the essential settings to get started.
        </p>
      </div>

      <div className="pt-4">
        <p className="text-sm text-muted-foreground">
          Click <strong>Next</strong> to begin setup.
        </p>
      </div>
    </div>
  );
};

import React from 'react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Button } from '@/components/ui/button';
import { AlertTriangle, Loader2, X } from 'lucide-react';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';

interface UnsavedChangesWarningProps {
  isSaving?: boolean;
}

export const UnsavedChangesWarning: React.FC<UnsavedChangesWarningProps> = ({ isSaving = false }) => {
  const {
    isWarningVisible,
    dismissWarning,
    handleSaveAndProceed,
    handleDiscardAndProceed,
  } = useUnsavedChangesContext();

  if (!isWarningVisible) return null;

  return (
    <div className="fixed bottom-4 left-1/2 transform -translate-x-1/2 z-50 animate-in slide-in-from-bottom duration-300">
      <Alert className="border-orange-500 bg-orange-50 dark:bg-orange-950/50 shadow-lg max-w-lg">
        <AlertTriangle className="h-4 w-4 text-orange-600" />
        <AlertDescription className="flex flex-col sm:flex-row items-start sm:items-center gap-3">
          <span className="text-orange-800 dark:text-orange-200 font-medium">
            You have unsaved changes
          </span>
          <div className="flex items-center gap-2">
            <Button
              variant="outline"
              size="sm"
              onClick={handleDiscardAndProceed}
              disabled={isSaving}
              className="border-orange-300 hover:bg-orange-100 dark:hover:bg-orange-900"
            >
              Discard
            </Button>
            <Button
              size="sm"
              onClick={handleSaveAndProceed}
              disabled={isSaving}
              className="bg-orange-600 hover:bg-orange-700 text-white"
            >
              {isSaving && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
              Save Now
            </Button>
            <Button
              variant="ghost"
              size="sm"
              onClick={dismissWarning}
              disabled={isSaving}
              className="h-8 w-8 p-0"
            >
              <X className="h-4 w-4" />
            </Button>
          </div>
        </AlertDescription>
      </Alert>
    </div>
  );
};

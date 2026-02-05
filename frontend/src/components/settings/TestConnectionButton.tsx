import React, { useState } from 'react';
import { Button } from '@/components/ui/button';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { Loader2, CheckCircle, XCircle } from 'lucide-react';
import { apiClient } from '@/api/client';

interface TestConnectionButtonProps {
  service: string;
  config: any;
  disabled?: boolean;
  useExisting?: boolean;
}

export const TestConnectionButton: React.FC<TestConnectionButtonProps> = ({
  service,
  config,
  disabled = false,
  useExisting = false,
}) => {
  const [isTesting, setIsTesting] = useState(false);
  const [result, setResult] = useState<{ success: boolean; message: string } | null>(null);

  const handleTest = async () => {
    setIsTesting(true);
    setResult(null);

    try {
      const response = await apiClient.testConnection(service, config, useExisting);
      setResult({
        success: response.success,
        message: response.message,
      });

      // Auto-dismiss success message after 3 seconds
      if (response.success) {
        setTimeout(() => setResult(null), 3000);
      }
    } catch (error: any) {
      setResult({
        success: false,
        message: error.response?.data?.detail || 'Connection test failed',
      });
    } finally {
      setIsTesting(false);
    }
  };

  return (
    <div className="space-y-2">
      <Button
        type="button"
        variant="outline"
        onClick={handleTest}
        disabled={disabled || isTesting}
      >
        {isTesting && <Loader2 className="mr-2 h-4 w-4 animate-spin" />}
        Test Connection
      </Button>

      {result && (
        <Alert variant={result.success ? 'default' : 'destructive'}>
          {result.success ? (
            <CheckCircle className="h-4 w-4" />
          ) : (
            <XCircle className="h-4 w-4" />
          )}
          <AlertDescription>{result.message}</AlertDescription>
        </Alert>
      )}
    </div>
  );
};

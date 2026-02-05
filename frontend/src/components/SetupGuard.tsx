import React, { useState, useEffect } from 'react';
import { Navigate } from 'react-router-dom';
import { apiClient } from '@/api/client';
import { Loader2 } from 'lucide-react';

interface SetupGuardProps {
  children: React.ReactNode;
}

/**
 * Lightweight guard that only checks if setup is required.
 * Does NOT require authentication — the dashboard is view-only for unauthenticated users.
 * Redirects to /setup when setup is needed (ProtectedRoute on /setup handles auth).
 */
export const SetupGuard: React.FC<SetupGuardProps> = ({ children }) => {
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);

  useEffect(() => {
    const checkSetup = async () => {
      try {
        const status = await apiClient.getSystemStatus();
        setSetupRequired(status.setup_required ?? false);
      } catch {
        setSetupRequired(false);
      }
    };
    checkSetup();
  }, []);

  if (setupRequired === null) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  if (setupRequired) {
    return <Navigate to="/setup" replace />;
  }

  return <>{children}</>;
};

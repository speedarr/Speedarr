import React from 'react';
import { Navigate } from 'react-router-dom';
import { useBootstrap } from '@/contexts/BootstrapContext';
import { Loader2 } from 'lucide-react';

interface SetupGuardProps {
  children: React.ReactNode;
}

/**
 * Lightweight guard that only checks if setup is required, from the shared
 * bootstrap context. Does NOT require authentication. Fails OPEN on error so a
 * transient bootstrap failure can never trap the user on /setup.
 */
export const SetupGuard: React.FC<SetupGuardProps> = ({ children }) => {
  const { data, isLoading, isError } = useBootstrap();

  if (isLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const setupRequired = isError ? false : (data?.setup_required ?? false);
  if (setupRequired) {
    return <Navigate to="/setup" replace />;
  }

  return <>{children}</>;
};

import React from 'react';
import { Navigate } from 'react-router';
import { useBootstrap } from '@/contexts/BootstrapContext';
import { useAuth } from '@/contexts/AuthContext';
import { Loader2 } from 'lucide-react';

interface RequireAuthIfPrivateProps {
  children: React.ReactNode;
}

/**
 * When require_login is enabled, redirect unauthenticated users to /login.
 * Renders a spinner until BOTH bootstrap and auth resolve (no dashboard flash),
 * and fails CLOSED: if the flag is unknown (bootstrap error), treat as private.
 */
export const RequireAuthIfPrivate: React.FC<RequireAuthIfPrivateProps> = ({ children }) => {
  const { data, isLoading: bootstrapLoading, isError } = useBootstrap();
  const { isAuthenticated, isLoading: authLoading } = useAuth();

  if (bootstrapLoading || authLoading) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  const requireLogin = isError ? true : (data?.require_login ?? true);
  if (requireLogin && !isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  return <>{children}</>;
};

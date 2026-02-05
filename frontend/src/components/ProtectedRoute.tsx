import React, { useState, useEffect } from 'react';
import { Navigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { apiClient } from '@/api/client';
import { Loader2 } from 'lucide-react';

interface ProtectedRouteProps {
  children: React.ReactNode;
}

export const ProtectedRoute: React.FC<ProtectedRouteProps> = ({ children }) => {
  const { isAuthenticated, isLoading: authLoading } = useAuth();
  const location = useLocation();
  const [setupRequired, setSetupRequired] = useState<boolean | null>(null);
  const [isCheckingSetup, setIsCheckingSetup] = useState(true);

  useEffect(() => {
    const checkSetupStatus = async () => {
      if (!isAuthenticated) {
        setIsCheckingSetup(false);
        return;
      }

      try {
        const status = await apiClient.getSystemStatus();
        setSetupRequired(status.setup_required ?? false);
      } catch (error) {
        console.error('Failed to check setup status:', error);
        setSetupRequired(false); // Assume setup not required on error
      } finally {
        setIsCheckingSetup(false);
      }
    };

    if (isAuthenticated) {
      checkSetupStatus();
    } else {
      setIsCheckingSetup(false);
    }
  }, [isAuthenticated]);

  // Show loading while checking auth or setup status
  if (authLoading || (isAuthenticated && isCheckingSetup)) {
    return (
      <div className="flex items-center justify-center min-h-screen">
        <Loader2 className="h-8 w-8 animate-spin text-muted-foreground" />
      </div>
    );
  }

  // Redirect to login if not authenticated
  if (!isAuthenticated) {
    return <Navigate to="/login" replace />;
  }

  const isOnSetupPage = location.pathname === '/setup';

  // If setup is required and not already on setup page, redirect to setup
  if (setupRequired && !isOnSetupPage) {
    return <Navigate to="/setup" replace />;
  }

  // If setup is complete and on setup page, redirect to dashboard
  if (!setupRequired && isOnSetupPage) {
    return <Navigate to="/" replace />;
  }

  return <>{children}</>;
};

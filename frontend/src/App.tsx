import React from 'react';
import { BrowserRouter, Routes, Route, Navigate } from 'react-router-dom';
import { QueryClient, QueryClientProvider } from '@tanstack/react-query';
import { ThemeProvider } from '@/contexts/ThemeContext';
import { AuthProvider } from '@/contexts/AuthContext';
import { ProtectedRoute } from '@/components/ProtectedRoute';
import { SetupGuard } from '@/components/SetupGuard';
import { Dashboard } from '@/components/Dashboard';
import { Login } from '@/pages/Login';
import { Home } from '@/pages/Home';
import { Settings } from '@/pages/Settings';
import { Setup } from '@/pages/Setup';
import { ErrorBoundary } from '@/components/ErrorBoundary';

// Create React Query client
const queryClient = new QueryClient({
  defaultOptions: {
    queries: {
      refetchOnWindowFocus: false,
      retry: 1,
    },
  },
});

const App: React.FC = () => {
  return (
    <QueryClientProvider client={queryClient}>
      <ThemeProvider>
        <BrowserRouter>
          <AuthProvider>
            <ErrorBoundary>
              <Routes>
                <Route path="/login" element={<Login />} />
                <Route
                  path="/setup"
                  element={
                    <ProtectedRoute>
                      <Setup />
                    </ProtectedRoute>
                  }
                />
                <Route path="/" element={<SetupGuard><Dashboard /></SetupGuard>}>
                  <Route index element={<ErrorBoundary><Home /></ErrorBoundary>} />
                  <Route path="settings" element={<ProtectedRoute><ErrorBoundary><Settings /></ErrorBoundary></ProtectedRoute>} />
                </Route>
                <Route path="*" element={<Navigate to="/" replace />} />
              </Routes>
            </ErrorBoundary>
          </AuthProvider>
        </BrowserRouter>
      </ThemeProvider>
    </QueryClientProvider>
  );
};

export default App;

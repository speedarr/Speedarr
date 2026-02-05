import React, { useState, useEffect } from 'react';
import { Outlet, useNavigate, useLocation } from 'react-router-dom';
import { useAuth } from '@/contexts/AuthContext';
import { ThemeToggle } from '@/components/ThemeToggle';
import { Button } from '@/components/ui/button';
import { cn } from '@/lib/utils';
import {
  LayoutDashboard,
  Settings,
  LogOut,
  LogIn,
  Menu,
  X,
} from 'lucide-react';
import { UnsavedChangesProvider, useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';
import { UnsavedChangesWarning } from '@/components/settings/UnsavedChangesWarning';

interface NavigationItem {
  text: string;
  icon: React.ReactNode;
  path: string;
}

const DashboardContent: React.FC = () => {
  const [mobileOpen, setMobileOpen] = useState(false);
  const { user, logout } = useAuth();
  const navigate = useNavigate();
  const location = useLocation();

  const {
    hasDirtyTabs,
    triggerWarning,
    setPendingNavigation,
    pendingNavigation,
    isWarningVisible,
    setNavigateCallback,
  } = useUnsavedChangesContext();

  // Register navigate function with context for save-then-navigate flow
  useEffect(() => {
    setNavigateCallback(navigate);
    return () => setNavigateCallback(null);
  }, [navigate, setNavigateCallback]);

  // Only show Settings for admin users
  const navigationItems: NavigationItem[] = [
    { text: 'Dashboard', icon: <LayoutDashboard className="h-5 w-5" />, path: '/' },
    ...(user?.role === 'admin' ? [{ text: 'Settings', icon: <Settings className="h-5 w-5" />, path: '/settings' }] : []),
  ];

  // Handle pending navigation after save/discard
  useEffect(() => {
    if (!isWarningVisible && pendingNavigation && !hasDirtyTabs) {
      navigate(pendingNavigation);
      setPendingNavigation(null);
    }
  }, [isWarningVisible, pendingNavigation, hasDirtyTabs, navigate, setPendingNavigation]);

  const handleNavigation = (path: string) => {
    // Check for unsaved changes when navigating away from settings
    if (location.pathname === '/settings' && hasDirtyTabs && path !== '/settings') {
      setPendingNavigation(path);
      triggerWarning();
      return;
    }
    navigate(path);
    setMobileOpen(false);
  };

  const handleLogout = async () => {
    await logout();
    navigate('/');
  };

  return (
    <div className="min-h-screen bg-slate-50 dark:bg-slate-900">
      {/* Mobile Header */}
      <div className="lg:hidden fixed top-0 left-0 right-0 z-50 bg-white dark:bg-slate-800 border-b border-slate-200 dark:border-slate-700">
        <div className="flex items-center justify-between p-4">
          <div className="flex items-center gap-2">
            <Button
              variant="ghost"
              size="icon"
              onClick={() => setMobileOpen(!mobileOpen)}
            >
              {mobileOpen ? <X className="h-5 w-5" /> : <Menu className="h-5 w-5" />}
            </Button>
            <img src="/speedarr.svg" alt="Speedarr" className="h-7 w-7" />
            <h1 className="text-xl font-bold">Speedarr</h1>
          </div>
          <ThemeToggle />
        </div>
      </div>

      {/* Sidebar */}
      <aside
        className={cn(
          "fixed left-0 z-40 w-64 bg-white dark:bg-slate-800 border-r border-slate-200 dark:border-slate-700 transition-transform",
          "top-16 h-[calc(100vh-4rem)] lg:top-0 lg:h-screen",
          mobileOpen ? "translate-x-0" : "-translate-x-full lg:translate-x-0"
        )}
      >
        <div className="flex flex-col h-full">
          {/* Logo */}
          <div className="hidden lg:flex items-center justify-between h-16 px-6 border-b border-slate-200 dark:border-slate-700">
            <div className="flex items-center gap-2">
              <img src="/speedarr.svg" alt="Speedarr" className="h-8 w-8" />
              <h1 className="text-xl font-bold">Speedarr</h1>
            </div>
            <ThemeToggle />
          </div>

          {/* Navigation */}
          <nav className="flex-1 px-3 py-4 space-y-1 overflow-y-auto">
            {navigationItems.map((item) => {
              const isActive = location.pathname === item.path;
              return (
                <button
                  key={item.text}
                  onClick={() => handleNavigation(item.path)}
                  className={cn(
                    "w-full flex items-center gap-3 px-3 py-2 rounded-md text-sm font-medium transition-colors",
                    isActive
                      ? "bg-primary text-primary-foreground"
                      : "text-slate-700 dark:text-slate-200 hover:bg-slate-100 dark:hover:bg-slate-700"
                  )}
                >
                  {item.icon}
                  <span>{item.text}</span>
                </button>
              );
            })}
          </nav>

          {/* User Info & Logout/Login */}
          <div className="p-4 border-t border-slate-200 dark:border-slate-700 space-y-2">
            {user ? (
              <>
                <div className="text-sm text-slate-600 dark:text-slate-400 px-3">
                  Logged in as <span className="font-medium text-slate-900 dark:text-slate-100">{user.username}</span>
                </div>
                <Button
                  variant="outline"
                  className="w-full justify-start"
                  onClick={handleLogout}
                >
                  <LogOut className="h-4 w-4 mr-2" />
                  Logout
                </Button>
              </>
            ) : (
              <Button
                variant="default"
                className="w-full justify-start"
                onClick={() => navigate('/login')}
              >
                <LogIn className="h-4 w-4 mr-2" />
                Login
              </Button>
            )}
          </div>
        </div>
      </aside>

      {/* Mobile Overlay */}
      {mobileOpen && (
        <div
          className="fixed inset-0 z-30 bg-black/50 lg:hidden"
          onClick={() => setMobileOpen(false)}
        />
      )}

      {/* Main Content */}
      <main className="lg:ml-64 pt-16 lg:pt-0">
        <div className="p-4 lg:p-8">
          <Outlet />
        </div>
      </main>

      {/* Unsaved Changes Warning - only show when on settings page */}
      {location.pathname === '/settings' && <UnsavedChangesWarning />}
    </div>
  );
};

export const Dashboard: React.FC = () => {
  return (
    <UnsavedChangesProvider>
      <DashboardContent />
    </UnsavedChangesProvider>
  );
};

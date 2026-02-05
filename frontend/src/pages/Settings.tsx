import React, { useState, useEffect, useCallback } from 'react';
import { Navigate } from 'react-router-dom';
import { Tabs, TabsContent, TabsList, TabsTrigger } from '@/components/ui/tabs';
import { Settings as SettingsIcon, Server, Gauge, Clock, Bell, Database, Shield, Network, UserCog } from 'lucide-react';
import { SystemSettings } from '@/components/settings/SystemSettings';
import { PlexSettings } from '@/components/settings/PlexSettings';
import { DownloadClientsSettings } from '@/components/settings/DownloadClientsSettings';
import { BandwidthSettings } from '@/components/settings/BandwidthSettings';
import { RestorationSettings } from '@/components/settings/RestorationSettings';
import { NotificationsSettings } from '@/components/settings/NotificationsSettings';
import { HistorySettings } from '@/components/settings/HistorySettings';
import { FailsafeSettings } from '@/components/settings/FailsafeSettings';
import { SNMPSettings } from '@/components/settings/SNMPSettings';
import { AccountSettings } from '@/components/settings/AccountSettings';
import { useUnsavedChangesContext } from '@/contexts/UnsavedChangesContext';
import { useAuth } from '@/contexts/AuthContext';

export const Settings: React.FC = () => {
  const { user } = useAuth();
  const [activeTab, setActiveTab] = useState('general');
  const {
    hasDirtyTabs,
    triggerWarning,
    setPendingTabChange,
    pendingTabChange,
    isWarningVisible,
  } = useUnsavedChangesContext();

  // Handle pending tab change after save/discard
  useEffect(() => {
    if (!isWarningVisible && pendingTabChange && !hasDirtyTabs) {
      setActiveTab(pendingTabChange);
      setPendingTabChange(null);
    }
  }, [isWarningVisible, pendingTabChange, hasDirtyTabs, setPendingTabChange]);

  const handleTabChange = useCallback(
    (newTab: string) => {
      if (hasDirtyTabs && newTab !== activeTab) {
        setPendingTabChange(newTab);
        triggerWarning();
        return;
      }
      setActiveTab(newTab);
    },
    [hasDirtyTabs, activeTab, setPendingTabChange, triggerWarning]
  );

  // Redirect non-admin users to dashboard
  if (user?.role !== 'admin') {
    return <Navigate to="/" replace />;
  }

  return (
    <div className="space-y-6">
      <div>
        <h1 className="text-3xl font-bold">Settings</h1>
        <p className="text-muted-foreground mt-2">
          Manage your Speedarr configuration
        </p>
      </div>

      <Tabs value={activeTab} onValueChange={handleTabChange} className="space-y-6">
        <TabsList className="grid w-full grid-cols-9 lg:w-auto lg:inline-grid">
          <TabsTrigger value="general" className="gap-2">
            <SettingsIcon className="h-4 w-4" />
            <span className="hidden sm:inline">General</span>
          </TabsTrigger>
          <TabsTrigger value="account" className="gap-2">
            <UserCog className="h-4 w-4" />
            <span className="hidden sm:inline">Account</span>
          </TabsTrigger>
          <TabsTrigger value="services" className="gap-2">
            <Server className="h-4 w-4" />
            <span className="hidden sm:inline">Services</span>
          </TabsTrigger>
          <TabsTrigger value="bandwidth" className="gap-2">
            <Gauge className="h-4 w-4" />
            <span className="hidden sm:inline">Bandwidth</span>
          </TabsTrigger>
          <TabsTrigger value="restoration" className="gap-2">
            <Clock className="h-4 w-4" />
            <span className="hidden sm:inline">Holding Times</span>
          </TabsTrigger>
          <TabsTrigger value="notifications" className="gap-2">
            <Bell className="h-4 w-4" />
            <span className="hidden sm:inline">Notifications</span>
          </TabsTrigger>
          <TabsTrigger value="history" className="gap-2">
            <Database className="h-4 w-4" />
            <span className="hidden sm:inline">History</span>
          </TabsTrigger>
          <TabsTrigger value="failsafe" className="gap-2">
            <Shield className="h-4 w-4" />
            <span className="hidden sm:inline">Failsafe</span>
          </TabsTrigger>
          <TabsTrigger value="snmp" className="gap-2">
            <Network className="h-4 w-4" />
            <span className="hidden sm:inline">SNMP</span>
          </TabsTrigger>
        </TabsList>

        <TabsContent value="general" className="space-y-4">
          <SystemSettings />
        </TabsContent>

        <TabsContent value="account" className="space-y-4">
          <AccountSettings />
        </TabsContent>

        <TabsContent value="services" className="space-y-4">
          <PlexSettings />
          <DownloadClientsSettings />
        </TabsContent>

        <TabsContent value="bandwidth" className="space-y-4">
          <BandwidthSettings />
        </TabsContent>

        <TabsContent value="restoration" className="space-y-4">
          <RestorationSettings />
        </TabsContent>

        <TabsContent value="notifications" className="space-y-4">
          <NotificationsSettings />
        </TabsContent>

        <TabsContent value="history" className="space-y-4">
          <HistorySettings />
        </TabsContent>

        <TabsContent value="failsafe" className="space-y-4">
          <FailsafeSettings />
        </TabsContent>

        <TabsContent value="snmp" className="space-y-4">
          <SNMPSettings />
        </TabsContent>
      </Tabs>
    </div>
  );
};

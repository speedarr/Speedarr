import React, { useState, useEffect } from 'react';
import { apiClient } from '@/api/client';
import type { ChartDataPoint } from '@/types';

type SNMPStatus = 'active' | 'inactive' | 'error';

interface SNMPConfig {
  enabled?: boolean;
}

export const SNMPStatusBadge: React.FC = () => {
  const [status, setStatus] = useState<SNMPStatus>('inactive');

  useEffect(() => {
    const checkStatus = async () => {
      try {
        // Check if SNMP is enabled
        const settingsResponse = await apiClient.getSettingsSection('snmp');
        const snmpConfig = settingsResponse.config as SNMPConfig;

        if (!snmpConfig?.enabled) {
          setStatus('inactive');
          return;
        }

        // Check if recent SNMP data exists
        const chartData = await apiClient.getBandwidthChartData({ hours: 1 });

        if (chartData.data && chartData.data.length > 0) {
          // Check if any recent data points have SNMP values
          const hasRecentSNMPData = chartData.data.some(
            (point: ChartDataPoint) => point.snmp_download_speed !== null || point.snmp_upload_speed !== null
          );

          setStatus(hasRecentSNMPData ? 'active' : 'error');
        } else {
          setStatus('error');
        }
      } catch (err) {
        setStatus('error');
      }
    };

    // Check immediately
    checkStatus();

    // Check every 30 seconds
    const interval = setInterval(checkStatus, 30000);

    return () => clearInterval(interval);
  }, []);

  // Don't show badge if SNMP is inactive
  if (status === 'inactive') {
    return null;
  }

  return (
    <div
      className={`inline-flex items-center gap-2 px-3 py-1 rounded-full text-xs font-medium ${
        status === 'active'
          ? 'bg-green-50 text-green-700 ring-1 ring-inset ring-green-600/20 dark:bg-green-500/10 dark:text-green-400 dark:ring-green-500/20'
          : 'bg-red-50 text-red-700 ring-1 ring-inset ring-red-600/20 dark:bg-red-500/10 dark:text-red-400 dark:ring-red-500/20'
      }`}
    >
      <span
        className={`h-2 w-2 rounded-full ${
          status === 'active' ? 'bg-green-600 dark:bg-green-400' : 'bg-red-600 dark:bg-red-400'
        }`}
      />
      SNMP {status === 'active' ? 'Active' : 'Error'}
    </div>
  );
};

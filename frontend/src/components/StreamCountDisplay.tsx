import React from 'react';
import type { SystemStatus } from '@/types';
import { AlertTriangle, Frown } from 'lucide-react';

interface StreamCountDisplayProps {
  status: SystemStatus;
}

/**
 * Center column of the dashboard status card. Renders one of three states:
 * unreachable media server(s), no active streams, or the active stream count
 * with a WAN-focused bitrate — WAN is the hero figure and LAN appears as a
 * small muted line only when there is LAN traffic. Shared by both the SNMP
 * and non-SNMP card layouts in Home.tsx so the two cannot drift.
 */
export const StreamCountDisplay: React.FC<StreamCountDisplayProps> = ({ status }) => {
  const unreachableServers = status.media_server_statuses
    ? Object.values(status.media_server_statuses).filter((s) => !s.connected)
    : [];

  if (unreachableServers.length > 0) {
    return (
      <>
        <AlertTriangle className="h-16 w-16 text-red-500 dark:text-red-400" />
        {unreachableServers.map((s, i) => (
          <p key={i} className="text-sm text-red-500 dark:text-red-400 mt-2">{s.name} Unreachable</p>
        ))}
      </>
    );
  }

  if (status.active_streams === 0) {
    return (
      <>
        <Frown className="h-16 w-16 text-muted-foreground" />
        <p className="text-sm text-muted-foreground mt-2">No Streams</p>
      </>
    );
  }

  const wanBitrate = status.bandwidth.upload.wan_stream_bandwidth
    ?? status.bandwidth.upload.stream_bandwidth
    ?? 0;
  const lanBitrate = status.bandwidth.upload.lan_stream_bandwidth ?? 0;

  return (
    <>
      <div className="text-6xl font-bold text-orange-500 dark:text-orange-400">
        {status.active_streams}
      </div>
      <p className="text-sm text-muted-foreground mt-1">
        {status.active_streams === 1 ? 'Stream' : 'Streams'}
      </p>
      <p className="text-xl font-semibold text-orange-500 dark:text-orange-400 text-center">
        {wanBitrate.toFixed(1)} Mbps WAN
      </p>
      {lanBitrate > 0 && (
        <p className="text-xs text-muted-foreground text-center">
          {lanBitrate.toFixed(1)} Mbps LAN
        </p>
      )}
    </>
  );
};

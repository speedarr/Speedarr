import React from 'react';
import { AlertCircle, AlertTriangle, Clock } from 'lucide-react';
import { Alert, AlertDescription } from '@/components/ui/alert';
import { StreamCountDisplay } from '@/components/StreamCountDisplay';
import { effectiveLimit, type Direction } from '@/lib/dashboardSummaries';
import type { ClientBandwidthStatus, SystemStatus, TemporaryLimitState } from '@/types';

export interface BandwidthOverviewProps {
  status: SystemStatus;
  tempLimits: TemporaryLimitState | null;
}

const hasOverride = (tempLimits: TemporaryLimitState | null, direction: Direction): boolean =>
  !!tempLimits?.active && (direction === 'download' ? tempLimits.download_mbps : tempLimits.upload_mbps) !== null;

/** "Total Limit" row, or the red "Temporary Limit" row while an override is active. */
const TotalLimitRow: React.FC<BandwidthOverviewProps & { direction: Direction }> = ({ status, tempLimits, direction }) => {
  const override = hasOverride(tempLimits, direction);
  return (
    <div className="flex justify-between items-center">
      {override ? (
        <span className="text-sm text-red-500 dark:text-red-400 flex items-center gap-1">
          <Clock className="h-3 w-3" aria-hidden="true" />
          <span>Temporary Limit:</span>
        </span>
      ) : (
        <span className="text-sm text-muted-foreground">Total Limit:</span>
      )}
      <span className={`font-semibold ${override ? 'text-red-500 dark:text-red-400' : ''}`}>
        {effectiveLimit(status, tempLimits, direction).toFixed(0)} Mbps
      </span>
    </div>
  );
};

/** One row per download client: name in the client's colour, speed / limit, or Unreachable. */
const ClientRows: React.FC<{ clients?: ClientBandwidthStatus[] }> = ({ clients }) => (
  <>
    {clients?.map((client) => (
      <div key={client.id} className="flex justify-between items-center">
        <span className="text-sm text-muted-foreground" style={{ color: client.error ? undefined : client.color }}>
          {client.error ? (
            <span className="text-red-500 dark:text-red-400 flex items-center gap-1">
              <AlertTriangle className="h-3 w-3" />
              {client.name}:
            </span>
          ) : (
            <>{client.name}:</>
          )}
        </span>
        {client.error ? (
          <span className="text-sm font-semibold text-red-500 dark:text-red-400">Unreachable</span>
        ) : (
          <span className="font-semibold">
            {client.speed.toFixed(0)} / {client.limit.toFixed(0)} Mbps
          </span>
        )}
      </div>
    ))}
  </>
);

/** "Available" row: against the temporary limit while one is active, else the engine's figure. */
const AvailableRow: React.FC<BandwidthOverviewProps & { direction: Direction }> = ({ status, tempLimits, direction }) => {
  const side = status.bandwidth[direction];
  const available = hasOverride(tempLimits, direction)
    ? Math.max(0, effectiveLimit(status, tempLimits, direction) - side.current_usage)
    : side.available;
  return (
    <div className="flex justify-between items-center">
      <span className="text-sm text-muted-foreground">Available:</span>
      <span className="font-semibold text-green-600 dark:text-green-400">{available.toFixed(0)} Mbps</span>
    </div>
  );
};

const WanFigure: React.FC<{ label: string; speed: number | null | undefined; status: SystemStatus }> = ({ label, speed, status }) => (
  <div className="flex flex-col items-center justify-center">
    <p className="text-sm text-muted-foreground mb-1">{label}</p>
    {status.snmp_status && !status.snmp_status.connected ? (
      <>
        <AlertTriangle className="h-6 w-6 text-red-500 dark:text-red-400" />
        <p className="text-xs text-red-500 dark:text-red-400 mt-1">SNMP Unreachable</p>
      </>
    ) : (
      <>
        <p className="text-2xl font-bold text-purple-600 dark:text-purple-400">
          {speed !== null && speed !== undefined ? `${speed.toFixed(0)}` : '--'}
        </p>
        <p className="text-sm text-muted-foreground">Mbps</p>
      </>
    )}
  </div>
);

/**
 * The dashboard's overview trio (Download | stream count | Upload) as three columns of one panel.
 * Extracted from Home.tsx for issue #86; the rows and figures are unchanged.
 */
export const BandwidthOverview: React.FC<BandwidthOverviewProps> = ({ status, tempLimits }) => {
  const download = status.bandwidth.download;
  const upload = status.bandwidth.upload;
  const uploadReserved = upload.reserved_bandwidth ?? 0;

  return (
    <div className="grid grid-cols-1 md:grid-cols-3 divide-y md:divide-y-0 md:divide-x divide-border">
      {/* Download */}
      <div className="py-4 md:py-0 md:pr-6 space-y-3">
        <h4 className="text-base font-semibold">Download Bandwidth</h4>
        <TotalLimitRow status={status} tempLimits={tempLimits} direction="download" />
        <ClientRows clients={download.clients} />
        {(download.stream_reserve ?? 0) > 0 && (
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Stream Reserve:</span>
            <span className="font-semibold text-orange-500 dark:text-orange-400">
              {(download.stream_reserve ?? 0).toFixed(1)} Mbps
            </span>
          </div>
        )}
        {(download.holding_reserve ?? 0) > 0 && (
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Holding Reserve:</span>
            <span className="font-semibold text-orange-500 dark:text-orange-400">
              {(download.holding_reserve ?? 0).toFixed(1)} Mbps
            </span>
          </div>
        )}
        <AvailableRow status={status} tempLimits={tempLimits} direction="download" />
      </div>

      {/* Stream count, with WAN figures when SNMP is enabled */}
      <div className="flex items-center py-6 md:py-0 md:px-4">
        {status.snmp_enabled ? (
          <div className="grid grid-cols-3 items-center justify-items-center w-full">
            <WanFigure label="WAN Download" speed={download.snmp_speed} status={status} />
            <div className="flex flex-col items-center justify-center border-x border-border py-2 w-full">
              <StreamCountDisplay status={status} />
            </div>
            <WanFigure label="WAN Upload" speed={upload.snmp_speed} status={status} />
          </div>
        ) : (
          <div className="flex flex-col items-center justify-center w-full">
            <StreamCountDisplay status={status} />
          </div>
        )}
      </div>

      {/* Upload */}
      <div className="py-4 md:py-0 md:pl-6 space-y-3">
        <h4 className="text-base font-semibold">Upload Bandwidth</h4>
        <TotalLimitRow status={status} tempLimits={tempLimits} direction="upload" />
        <ClientRows clients={upload.clients} />
        <div className="flex justify-between items-center">
          <span className="text-sm text-muted-foreground">Stream Reserved:</span>
          <span className="font-semibold text-orange-500 dark:text-orange-400">
            {uploadReserved.toFixed(0)} Mbps
          </span>
        </div>
        {uploadReserved > upload.total_limit && (
          <Alert variant="destructive" className="py-2">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              Stream reserved ({uploadReserved.toFixed(0)} Mbps) exceeds upload limit ({upload.total_limit.toFixed(0)} Mbps). Upload clients are limited to the configured minimum speed each.
            </AlertDescription>
          </Alert>
        )}
        {tempLimits?.active && tempLimits.upload_mbps !== null && uploadReserved > tempLimits.upload_mbps && (
          <Alert variant="destructive" className="py-2">
            <AlertCircle className="h-4 w-4" />
            <AlertDescription className="text-xs">
              Stream reserved ({uploadReserved.toFixed(0)} Mbps) exceeds temporary upload limit ({tempLimits.upload_mbps.toFixed(0)} Mbps). Upload clients are limited to the configured minimum speed each.
            </AlertDescription>
          </Alert>
        )}
        {(upload.holding_bandwidth ?? 0) > 0 && (
          <div className="flex justify-between items-center">
            <span className="text-sm text-muted-foreground">Holding:</span>
            <span className="font-semibold text-orange-500 dark:text-orange-400">
              {(upload.holding_bandwidth ?? 0).toFixed(0)} Mbps
            </span>
          </div>
        )}
        <AvailableRow status={status} tempLimits={tempLimits} direction="upload" />
      </div>
    </div>
  );
};

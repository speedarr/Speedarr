import React from 'react';

interface SpeedUnitHintProps {
  mbps: number;
  className?: string;
}

const BYTES_PER_MEGABIT = 1_000_000 / 8;

const wholeNumber = (n: number) => n.toLocaleString(undefined, { maximumFractionDigits: 0 });

/**
 * Restates an Mbps value in the byte-per-second units download clients
 * display (decimal MB/s and KB/s, binary MiB/s and KiB/s).
 * Renders nothing when the value is zero or invalid.
 */
export const SpeedUnitHint: React.FC<SpeedUnitHintProps> = ({
  mbps,
  className = 'text-sm text-muted-foreground',
}) => {
  if (!(mbps > 0)) return null;
  const bytesPerSec = mbps * BYTES_PER_MEGABIT;
  const mb = (bytesPerSec / 1_000_000).toFixed(1);
  const kb = wholeNumber(bytesPerSec / 1_000);
  const mib = (bytesPerSec / 1_048_576).toFixed(1);
  const kib = wholeNumber(bytesPerSec / 1_024);
  return (
    <p className={className}>
      Download clients show speeds in bytes per second, not megabits.{' '}
      <strong className="text-foreground">{mbps.toLocaleString(undefined, { maximumFractionDigits: 1 })} Mbps</strong>{' '}
      is about <strong className="text-foreground">{mb} MB/s</strong> (<strong className="text-foreground">{kb} KB/s</strong>){' '}
      or <strong className="text-foreground">{mib} MiB/s</strong> (<strong className="text-foreground">{kib} KiB/s</strong>),{' '}
      depending on which unit your client uses.
    </p>
  );
};

interface ClientSpeedUnitNoteProps {
  clientName: string;
  speedUnit: string;
  className?: string;
}

/** One-line reminder of the units a specific download client displays versus Speedarr's Mbps. */
export const ClientSpeedUnitNote: React.FC<ClientSpeedUnitNoteProps> = ({
  clientName,
  speedUnit,
  className = 'text-sm text-muted-foreground',
}) => (
  <p className={className}>
    {clientName} displays speeds in {speedUnit}. Speedarr limits are in Mbps (megabits). 8 Mbps ≈ 1 MB/s.
  </p>
);

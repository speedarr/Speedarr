// Failsafe shutdown speeds default to a fraction of the bandwidth limit they belong to.
export const FAILSAFE_DEFAULT_FRACTION = 0.1;

/** The default failsafe speed for a bandwidth limit: 10 % of it, rounded to one decimal (Mbps). */
export function defaultFailsafeSpeed(totalLimit: number): number {
  return Math.round(totalLimit * FAILSAFE_DEFAULT_FRACTION * 10) / 10;
}

/**
 * The failsafe speed to store after the bandwidth limit changes from previousLimit to nextLimit.
 * A speed that still equals the default for the old limit follows the new limit; a speed the user
 * customised is kept; a disabled failsafe (null) stays disabled.
 */
export function nextFailsafeSpeed(
  current: number | null,
  previousLimit: number,
  nextLimit: number,
): number | null {
  if (current === null) return null;
  if (current !== defaultFailsafeSpeed(previousLimit)) return current;
  return defaultFailsafeSpeed(nextLimit);
}

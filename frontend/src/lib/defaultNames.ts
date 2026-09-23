/**
 * The default display name for a new instance of a type: the base name if nothing uses it,
 * otherwise "base N" with the smallest N from 2 that is still free. Comparison ignores case
 * and surrounding spaces, so removing "Plex" and adding again never yields a second "Plex 2".
 */
export function nextDefaultName(base: string, existing: Iterable<string>): string {
  const taken = new Set(Array.from(existing, name => name.trim().toLowerCase()));
  if (!taken.has(base.toLowerCase())) return base;
  for (let n = 2; ; n++) {
    const candidate = `${base} ${n}`;
    if (!taken.has(candidate.toLowerCase())) return candidate;
  }
}

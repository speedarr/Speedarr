// Registers the jest-dom matchers (toBeInTheDocument, toHaveAttribute, ...) with vitest's expect,
// and unmounts rendered trees between tests: RTL only does that automatically when the runner
// exposes a global afterEach, and this project runs vitest without globals.
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

afterEach(() => {
  cleanup();
});

// jsdom's selector engine (nwsapi) takes seconds and recurses hundreds of frames deep when asked
// to evaluate the top-layer pseudo-classes that floating-ui probes while positioning a Radix menu
// (`isTopLayer` in @floating-ui/utils/dom matches `:popover-open` and `:modal`; nwsapi resolves
// them through its `:fullscreen` check, hence all three). Nothing in jsdom is ever in the top
// layer, so answer those selectors with false immediately and leave every other selector to
// jsdom. If floating-ui ever changes the literals, the ten-second menu opens come back silently.
const TOP_LAYER_SELECTORS = new Set([':popover-open', ':modal', ':fullscreen']);
const nativeMatches = Element.prototype.matches;
Element.prototype.matches = function matches(this: Element, selector: string): boolean {
  if (TOP_LAYER_SELECTORS.has(selector)) return false;
  return nativeMatches.call(this, selector);
};

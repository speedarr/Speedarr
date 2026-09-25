// Registers the jest-dom matchers (toBeInTheDocument, toHaveAttribute, ...) with vitest's expect,
// and unmounts rendered trees between tests: RTL only does that automatically when the runner
// exposes a global afterEach, and this project runs vitest without globals.
import { afterEach } from 'vitest';
import { cleanup, configure } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

afterEach(() => {
  cleanup();
});

// The image build runs this suite on linux/arm64 under QEMU, several times slower than native, and
// the suite's wall time swings by a minute between runs. testing-library's findBy and waitFor give up
// after 1 s by default, which is what failed Develop Build 35931511300 on a docs-only commit; the
// per-test timeout in vite.config.ts is 30 s for the same reason. Nothing here waits that long on a
// native run, so a passing test is no slower and only a failing one takes longer to report.
configure({ asyncUtilTimeout: 10_000 });

// jsdom's selector engine took seconds and recursed hundreds of frames deep when asked to evaluate
// the top-layer pseudo-classes that floating-ui probes while positioning a Radix menu (`isTopLayer`
// in @floating-ui/utils/dom matches `:popover-open` and `:modal`; nwsapi, jsdom 26's engine,
// resolved them through its `:fullscreen` check, hence all three). Nothing in jsdom is ever in the
// top layer, so answer those selectors with false immediately and leave every other selector to
// jsdom. Measured on jsdom 26; jsdom 30 ships @asamuzakjp/dom-selector instead and the shim has
// not been re-timed there, so remove it only after timing the suite without it. If floating-ui
// ever changes the literals, the ten-second menu opens come back silently.
// TypeScript 6's DOM lib types `matches` with type-predicate overloads, hence the cast.
const TOP_LAYER_SELECTORS = new Set([':popover-open', ':modal', ':fullscreen']);
const nativeMatches = Element.prototype.matches;
Element.prototype.matches = function matches(this: Element, selector: string): boolean {
  if (TOP_LAYER_SELECTORS.has(selector)) return false;
  return nativeMatches.call(this, selector);
} as typeof Element.prototype.matches;

// jsdom does not implement scrollIntoView; the unsaved-changes banner calls it on a panel's Save
// button when it opens and when a Save Now fails. A no-op keeps those paths runnable, and a test
// that cares spies on it (vi.spyOn(Element.prototype, 'scrollIntoView')).
if (typeof Element.prototype.scrollIntoView !== 'function') {
  Element.prototype.scrollIntoView = () => {};
}

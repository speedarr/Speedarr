// Registers the jest-dom matchers (toBeInTheDocument, toHaveAttribute, ...) with vitest's expect,
// and unmounts rendered trees between tests: RTL only does that automatically when the runner
// exposes a global afterEach, and this project runs vitest without globals.
import { afterEach } from 'vitest';
import { cleanup } from '@testing-library/react';
import '@testing-library/jest-dom/vitest';

afterEach(() => {
  cleanup();
});

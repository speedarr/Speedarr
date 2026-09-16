import { describe, it, expect } from 'vitest';
import { getErrorMessage } from './utils';

describe('getErrorMessage', () => {
  it('returns a string error unchanged', () => {
    expect(getErrorMessage('boom')).toBe('boom');
  });

  it('returns the message of an Error', () => {
    expect(getErrorMessage(new Error('nope'))).toBe('nope');
  });

  it('falls back to a generic message for unknown values', () => {
    expect(getErrorMessage(42)).toBe('An unknown error occurred');
  });
});

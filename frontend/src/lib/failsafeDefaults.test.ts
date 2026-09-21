import { describe, it, expect } from 'vitest';
import { defaultFailsafeSpeed, nextFailsafeSpeed } from './failsafeDefaults';

describe('defaultFailsafeSpeed', () => {
  it('is 10% of the limit rounded to one decimal', () => {
    expect(defaultFailsafeSpeed(100)).toBe(10);
    expect(defaultFailsafeSpeed(123.45)).toBe(12.3);
    expect(defaultFailsafeSpeed(0)).toBe(0);
  });
});

describe('nextFailsafeSpeed', () => {
  it('keeps a failsafe speed the user customised when the limit changes', () => {
    expect(nextFailsafeSpeed(25, 100, 200)).toBe(25);
  });

  it('follows the limit when the failsafe still equals 10% of the old limit', () => {
    expect(nextFailsafeSpeed(10, 100, 200)).toBe(20);
  });

  it('recognises the rounded default as the default', () => {
    expect(nextFailsafeSpeed(12.3, 123.45, 50)).toBe(5);
  });

  it('leaves a disabled failsafe disabled', () => {
    expect(nextFailsafeSpeed(null, 100, 200)).toBeNull();
  });
});

import { describe, it, expect } from 'vitest';
import { nextDefaultName } from './defaultNames';

// #109: a second instance of a type gets the next free number, not a count.
describe('nextDefaultName', () => {
  it('returns the base name when nothing uses it', () => {
    expect(nextDefaultName('qBittorrent', [])).toBe('qBittorrent');
    expect(nextDefaultName('qBittorrent', ['SABnzbd'])).toBe('qBittorrent');
  });

  it('numbers the second instance from 2', () => {
    expect(nextDefaultName('qBittorrent', ['qBittorrent'])).toBe('qBittorrent 2');
  });

  it('keeps counting past numbers already in use', () => {
    expect(nextDefaultName('Plex', ['Plex', 'Plex 2'])).toBe('Plex 3');
  });

  it('fills the lowest free number after a removal', () => {
    // Remove "Plex", keep "Plex 2", add again: the old count-based rule produced a second "Plex 2".
    expect(nextDefaultName('Plex', ['Plex 2'])).toBe('Plex');
    expect(nextDefaultName('Plex', ['Plex', 'Plex 3'])).toBe('Plex 2');
  });

  it('treats names as taken regardless of case or surrounding spaces', () => {
    expect(nextDefaultName('qBittorrent', ['qbittorrent '])).toBe('qBittorrent 2');
    expect(nextDefaultName('qBittorrent', ['QBITTORRENT 2', 'qBittorrent'])).toBe('qBittorrent 3');
  });
});

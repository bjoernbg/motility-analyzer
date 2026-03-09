import { describe, expect, it } from 'vitest';
import {
  getTrimmedDisplayName,
  getVideoDisplayName,
  hasCustomDisplayName,
} from '../displayNames';

describe('display name helpers', () => {
  it('uses the trimmed custom display name when present', () => {
    const video = { filename: 'raw-name.mp4', display_name: '  Custom Name  ' };
    expect(getVideoDisplayName(video)).toBe('Custom Name');
    expect(hasCustomDisplayName(video)).toBe(true);
    expect(getTrimmedDisplayName(video)).toBe('Custom Name');
  });

  it('falls back to the file name when display_name is empty', () => {
    const video = { filename: 'raw-name.mp4', display_name: '   ' };
    expect(getVideoDisplayName(video)).toBe('raw-name.mp4');
    expect(hasCustomDisplayName(video)).toBe(false);
    expect(getTrimmedDisplayName(video)).toBeNull();
  });
});

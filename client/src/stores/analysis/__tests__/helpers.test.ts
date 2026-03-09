import { describe, expect, it } from 'vitest';
import type { FrameData } from '../../../lib/api';
import {
  buildFrameCacheKey,
  evictLeastRecentlyUsedFrame,
  keepOnlyAnalysisFrames,
  parametersMatch,
  type FrameCacheEntry,
} from '../helpers';

function createFrameData(frame: number): FrameData {
  return {
    f: frame,
    pt: [],
    pb: [],
    pc: [],
    colored_regions: [],
  };
}

describe('analysis store helpers', () => {
  it('builds stable frame cache keys', () => {
    expect(buildFrameCacheKey('analysis-1', 42)).toBe('analysis-1:42');
  });

  it('evicts least recently used frame when cache is full', () => {
    const cache = new Map<string, FrameCacheEntry>([
      ['analysis-a:0', { data: createFrameData(0), lastAccessed: 10 }],
      ['analysis-a:1', { data: createFrameData(1), lastAccessed: 50 }],
      ['analysis-a:2', { data: createFrameData(2), lastAccessed: 40 }],
    ]);

    evictLeastRecentlyUsedFrame(cache, 3);

    expect(cache.has('analysis-a:0')).toBe(false);
    expect(cache.size).toBe(2);
  });

  it('keeps only frame cache entries belonging to selected analysis', () => {
    const cache = new Map<string, FrameCacheEntry>([
      ['left:0', { data: createFrameData(0), lastAccessed: 10 }],
      ['right:0', { data: createFrameData(0), lastAccessed: 20 }],
      ['left:1', { data: createFrameData(1), lastAccessed: 30 }],
    ]);

    keepOnlyAnalysisFrames(cache, 'left');

    expect([...cache.keys()]).toEqual(['left:0', 'left:1']);
  });

  it('matches analysis parameters with numeric tolerance', () => {
    const a = {
      smoothing_factor: 0.2,
      silhouette_blur_sigma: 1.6004,
      num_tracking_points: 30,
    };
    const b = {
      smoothing_factor: 0.2,
      silhouette_blur_sigma: 1.6,
      num_tracking_points: 30 as const,
    };

    expect(parametersMatch(a, b)).toBe(true);
  });

  it('detects non-matching parameter values', () => {
    const a = {
      smoothing_factor: 0.2,
      silhouette_blur_sigma: 1.7,
    };
    const b = {
      smoothing_factor: 0.2,
      silhouette_blur_sigma: 1.6,
    };

    expect(parametersMatch(a, b)).toBe(false);
  });
});

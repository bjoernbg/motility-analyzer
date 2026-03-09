import { describe, expect, it } from 'vitest';
import {
  parametersMatch,
  resolveTrackingPointsPreset,
  snapTrackingPointsToPreset,
  TRACKING_POINT_PRESETS,
} from '../analysisParameters';

describe('analysis parameter helpers', () => {
  it('matches numeric fields within tolerance', () => {
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

  it('does not match numeric fields outside tolerance', () => {
    const a = {
      smoothing_factor: 0.2,
      silhouette_blur_sigma: 1.61,
    };
    const b = {
      smoothing_factor: 0.2,
      silhouette_blur_sigma: 1.6,
    };
    expect(parametersMatch(a, b)).toBe(false);
  });

  it('snaps tracking points to the nearest preset', () => {
    expect(snapTrackingPointsToPreset(42)).toBe(50);
    expect(snapTrackingPointsToPreset(118)).toBe(120);
    expect(snapTrackingPointsToPreset(203)).toBe(200);
    expect(TRACKING_POINT_PRESETS).toEqual([30, 50, 80, 120, 200]);
  });

  it('resolves tracking points from unknown values using defaults', () => {
    expect(resolveTrackingPointsPreset(undefined)).toBe(30);
    expect(resolveTrackingPointsPreset('not-a-number')).toBe(30);
  });
});

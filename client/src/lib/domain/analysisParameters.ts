import type { AnalysisParameters } from '../api';
import { DEFAULT_NUM_TRACKING_POINTS } from '../constants';

const DEFAULT_TOLERANCE = 0.001;

export const TRACKING_POINT_PRESETS = [30, 50, 80, 120, 200] as const;

export type TrackingPointPreset = (typeof TRACKING_POINT_PRESETS)[number];

function isDefinedValue(value: unknown): boolean {
  return value !== undefined && value !== null;
}

export function parametersMatch(
  params1: Record<string, unknown>,
  params2: AnalysisParameters,
  tolerance: number = DEFAULT_TOLERANCE
): boolean {
  const keys1 = Object.keys(params1).filter((key) => isDefinedValue(params1[key]));
  const params2Record = params2 as Record<string, unknown>;
  const keys2 = Object.keys(params2Record).filter((key) => isDefinedValue(params2Record[key]));

  if (keys1.length !== keys2.length) {
    return false;
  }

  for (const key of keys1) {
    const left = params1[key];
    const right = params2Record[key];

    if (left === null && right === null) {
      continue;
    }
    if (left === null || right === null) {
      return false;
    }

    if (typeof left === 'number' && typeof right === 'number') {
      if (Math.abs(left - right) > tolerance) {
        return false;
      }
      continue;
    }

    if (left !== right) {
      return false;
    }
  }

  return true;
}

export function snapTrackingPointsToPreset(raw: number): TrackingPointPreset {
  return TRACKING_POINT_PRESETS.reduce((previous, current) =>
    Math.abs(current - raw) < Math.abs(previous - raw) ? current : previous
  );
}

export function resolveTrackingPointsPreset(raw: unknown): TrackingPointPreset {
  const numericRaw = typeof raw === 'number' ? raw : DEFAULT_NUM_TRACKING_POINTS;
  return snapTrackingPointsToPreset(numericRaw);
}

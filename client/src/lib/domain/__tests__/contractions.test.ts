import { describe, expect, it } from 'vitest';

import type { ContractionEvent } from '../../api';
import {
  buildContractionSummary,
  buildContractionTrendChartModel,
  getContractionDetectionPresetId,
  isLegacyContractionDetection,
} from '../contractions';

function createEvent(
  startFrame: number,
  durationSeconds: number,
  area = 10,
  speed = 1.5
): ContractionEvent {
  const endFrame = startFrame + Math.round(durationSeconds * 10) - 1;
  return {
    id: `event-${startFrame}`,
    label: startFrame,
    n_pixels: 10,
    threshold_used: -1,
    t_range_frames: [startFrame, endFrame],
    y_range_idx: [0, 5],
    duration_s: durationSeconds,
    height_phys: 5,
    velocity_phys_per_s: speed,
    line_fit: {
      a_idx_per_frame: 0.1,
      b: 0,
    },
    area_exact: area,
    area_triangle: area,
    created_at: '2026-03-16T12:00:00',
  };
}

describe('contraction summary helpers', () => {
  it('computes summary bins and medians from event metrics', () => {
    const events = [
      createEvent(100, 3, 10, 0.5),
      createEvent(650, 5, 20, -1.5),
      createEvent(1400, 7, 40, 2.5),
    ];

    const summary = buildContractionSummary(events, 10, 150);

    expect(summary).not.toBeNull();
    expect(summary?.totalEvents).toBe(3);
    expect(summary?.overallRatePerMinute).toBeCloseTo(1.2);
    expect(summary?.bins.map((bin) => bin.count)).toEqual([1, 1, 1]);
    expect(summary?.bins.map((bin) => Number(bin.ratePerMinute.toFixed(2)))).toEqual([1, 1, 2]);
    expect(summary?.standardDeviationPerMinute).toBeCloseTo(0.47, 2);
    expect(summary?.medianDurationSeconds).toBe(5);
    expect(summary?.medianAbsSpeedMmPerS).toBe(1.5);
    expect(summary?.medianAreaMm2S).toBe(20);
  });

  it('matches named presets and reports custom expert tuning', () => {
    expect(getContractionDetectionPresetId()).toBe('balanced');
    expect(getContractionDetectionPresetId({
      threshold_percentile: 8,
      min_pixels: 260,
      min_duration_s: 5,
      min_span_mm: 6,
      merge_max_gap_s: 0.75,
    })).toBe('conservative');
    expect(getContractionDetectionPresetId({
      threshold_percentile: 8,
      min_pixels: 260,
      min_duration_s: 8,
      min_span_mm: 6,
      merge_max_gap_s: 0.75,
    })).toBe('custom');
  });

  it('builds chart-ready minute bars and event overlay points', () => {
    const events = [
      createEvent(100, 3, 10, 0.5),
      createEvent(650, 5, 20, -1.5),
      createEvent(1400, 7, 40, 2.5),
    ];
    const summary = buildContractionSummary(events, 10, 150);
    const chartModel = buildContractionTrendChartModel(summary, events, 10, 'speed');

    expect(chartModel).not.toBeNull();
    expect(chartModel?.bars.map((bar) => Number(bar.xMinutes.toFixed(2)))).toEqual([0.5, 1.5, 2.25]);
    expect(chartModel?.overlayPoints.map((point) => Number(point.xMinutes.toFixed(2)))).toEqual([0.17, 1.08, 2.33]);
    expect(chartModel?.overlayPoints.map((point) => point.y)).toEqual([0.5, -1.5, 2.5]);
    expect(chartModel?.rightAxisLabel).toBe('Propagation speed (mm/s)');
    expect(chartModel?.partialBinNote).toBe('Last bin normalized to 30 s');
  });

  it('detects legacy contraction versions', () => {
    expect(isLegacyContractionDetection('legacy-v1')).toBe(true);
    expect(isLegacyContractionDetection('v2')).toBe(false);
    expect(isLegacyContractionDetection(null)).toBe(false);
  });
});

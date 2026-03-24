import type { ContractionDetectionParameters, ContractionEvent } from '../api';
import { CONTRACTION_DETECTION_VERSION_V2 } from '../api';

export type ContractionOverlayMetric = 'none' | 'speed' | 'duration' | 'area';
export type ContractionDetectionPresetId = 'conservative' | 'balanced' | 'sensitive';

export interface ContractionRateBin {
  startTimeSeconds: number;
  endTimeSeconds: number;
  durationSeconds: number;
  count: number;
  ratePerMinute: number;
}

export interface ContractionSummary {
  totalEvents: number;
  overallRatePerMinute: number;
  standardDeviationPerMinute: number;
  medianDurationSeconds: number;
  medianAbsSpeedMmPerS: number;
  medianAreaMm2S: number;
  bins: ContractionRateBin[];
}

export interface ContractionDetectionPreset {
  id: ContractionDetectionPresetId;
  label: string;
  description: string;
  parameters: ContractionDetectionParameters;
}

export interface ContractionTrendBarDatum {
  key: string;
  xMinutes: number;
  widthMinutes: number;
  startTimeSeconds: number;
  endTimeSeconds: number;
  durationSeconds: number;
  count: number;
  ratePerMinute: number;
  isPartial: boolean;
}

export interface ContractionTrendOverlayDatum {
  eventId: string;
  xMinutes: number;
  y: number;
  startTimeSeconds: number;
  durationSeconds: number;
  speedMmPerS: number;
  areaMm2S: number;
}

export interface ContractionTrendChartModel {
  bars: ContractionTrendBarDatum[];
  overlayPoints: ContractionTrendOverlayDatum[];
  xMaxMinutes: number;
  partialBinNote: string | null;
  rightAxisLabel: string | null;
}

export const DEFAULT_CONTRACTION_DETECTION_PARAMETERS: Readonly<ContractionDetectionParameters> = Object.freeze({
  smooth_sigma_y: 1.0,
  smooth_sigma_t: 1.0,
  threshold_percentile: 10.0,
  threshold: null,
  open_iters: 1,
  close_iters: 2,
  min_pixels: 200,
  min_duration_s: 4.0,
  min_span_mm: 5.0,
  area_threshold_median_fraction: 0.7,
  merge_max_gap_s: 1.0,
  merge_max_offset_mm: 5.0,
  merge_max_velocity_delta_mm_s: 1.0,
  min_area: null,
  min_height: null,
  dy: null,
});

const CONTRACTION_DETECTION_PRESETS: ReadonlyArray<ContractionDetectionPreset> = Object.freeze([
  {
    id: 'conservative',
    label: 'Conservative',
    description: 'Prefers cleaner, larger events and suppresses weak candidates.',
    parameters: createContractionDetectionParameters({
      threshold_percentile: 8.0,
      min_pixels: 260,
      min_duration_s: 5.0,
      min_span_mm: 6.0,
      merge_max_gap_s: 0.75,
    }),
  },
  {
    id: 'balanced',
    label: 'Balanced',
    description: 'Default review workflow with the current tuned detector settings.',
    parameters: createContractionDetectionParameters(),
  },
  {
    id: 'sensitive',
    label: 'Sensitive',
    description: 'Captures smaller and shorter events with a lower merge threshold.',
    parameters: createContractionDetectionParameters({
      threshold_percentile: 14.0,
      min_pixels: 140,
      min_duration_s: 3.0,
      min_span_mm: 4.0,
      merge_max_gap_s: 1.25,
    }),
  },
]);

function canonicalizeContractionDetectionParameters(
  parameters?: ContractionDetectionParameters | null
): ContractionDetectionParameters {
  const normalized = {
    ...DEFAULT_CONTRACTION_DETECTION_PARAMETERS,
    ...(parameters ?? {}),
  };

  if ((normalized.min_span_mm ?? null) === null && normalized.min_height !== null) {
    normalized.min_span_mm = normalized.min_height;
  }

  if (
    normalized.min_height !== null &&
    normalized.min_span_mm !== null &&
    normalized.min_height === normalized.min_span_mm
  ) {
    normalized.min_height = null;
  }

  return normalized;
}

function getMedian(values: number[]): number {
  if (values.length === 0) {
    return 0;
  }

  const sortedValues = [...values].sort((left, right) => left - right);
  const middleIndex = Math.floor(sortedValues.length / 2);

  if (sortedValues.length % 2 === 0) {
    return ((sortedValues[middleIndex - 1] ?? 0) + (sortedValues[middleIndex] ?? 0)) / 2;
  }

  return sortedValues[middleIndex] ?? 0;
}

function getOverlayMetricValue(
  event: ContractionEvent,
  metric: Exclude<ContractionOverlayMetric, 'none'>
): number {
  switch (metric) {
    case 'speed':
      return event.velocity_phys_per_s;
    case 'duration':
      return event.duration_s;
    case 'area':
      return event.area_exact;
  }
}

export function getContractionStartTimeSeconds(
  event: ContractionEvent,
  fps: number
): number {
  if (fps <= 0) {
    return 0;
  }
  return event.t_range_frames[0] / fps;
}

export function buildContractionSummary(
  events: ContractionEvent[],
  fps: number | null | undefined,
  durationSeconds: number | null | undefined
): ContractionSummary | null {
  if (!fps || fps <= 0 || !durationSeconds || durationSeconds <= 0) {
    return null;
  }

  const totalEvents = events.length;
  const overallRatePerMinute = totalEvents / (durationSeconds / 60);
  const binCount = Math.max(1, Math.ceil(durationSeconds / 60));
  const bins: ContractionRateBin[] = [];

  for (let index = 0; index < binCount; index += 1) {
    const startTimeSeconds = index * 60;
    const endTimeSeconds = Math.min(durationSeconds, startTimeSeconds + 60);
    bins.push({
      startTimeSeconds,
      endTimeSeconds,
      durationSeconds: Math.max(1e-9, endTimeSeconds - startTimeSeconds),
      count: 0,
      ratePerMinute: 0,
    });
  }

  for (const event of events) {
    const startTimeSeconds = getContractionStartTimeSeconds(event, fps);
    const binIndex = Math.min(binCount - 1, Math.max(0, Math.floor(startTimeSeconds / 60)));
    const bin = bins[binIndex];
    if (bin) {
      bin.count += 1;
    }
  }

  for (const bin of bins) {
    bin.ratePerMinute = bin.count / (bin.durationSeconds / 60);
  }

  const mean = bins.reduce((sum, bin) => sum + bin.ratePerMinute, 0) / bins.length;
  const variance = bins.reduce((sum, bin) => {
    const diff = bin.ratePerMinute - mean;
    return sum + (diff * diff);
  }, 0) / bins.length;

  return {
    totalEvents,
    overallRatePerMinute,
    standardDeviationPerMinute: Math.sqrt(variance),
    medianDurationSeconds: getMedian(events.map((event) => event.duration_s)),
    medianAbsSpeedMmPerS: getMedian(events.map((event) => Math.abs(event.velocity_phys_per_s))),
    medianAreaMm2S: getMedian(events.map((event) => event.area_exact)),
    bins,
  };
}

export function getContractionPartialBinNote(
  summary: ContractionSummary | null
): string | null {
  const lastBin = summary?.bins[summary.bins.length - 1];
  if (!lastBin || lastBin.durationSeconds >= 59.999) {
    return null;
  }

  return `Last bin normalized to ${lastBin.durationSeconds.toFixed(0)} s`;
}

export function buildContractionTrendChartModel(
  summary: ContractionSummary | null,
  events: ContractionEvent[],
  fps: number | null | undefined,
  overlayMetric: ContractionOverlayMetric
): ContractionTrendChartModel | null {
  if (!summary) {
    return null;
  }

  const lastBin = summary.bins[summary.bins.length - 1];
  const bars = summary.bins.map((bin, index) => ({
    key: `bin-${index}-${bin.startTimeSeconds}`,
    xMinutes: ((bin.startTimeSeconds + bin.endTimeSeconds) / 2) / 60,
    widthMinutes: bin.durationSeconds / 60,
    startTimeSeconds: bin.startTimeSeconds,
    endTimeSeconds: bin.endTimeSeconds,
    durationSeconds: bin.durationSeconds,
    count: bin.count,
    ratePerMinute: bin.ratePerMinute,
    isPartial: bin.durationSeconds < 59.999,
  }));

  const overlayPoints = overlayMetric === 'none' || !fps || fps <= 0
    ? []
    : [...events]
      .sort((left, right) => left.t_range_frames[0] - right.t_range_frames[0])
      .map((event) => ({
        eventId: event.id,
        xMinutes: getContractionStartTimeSeconds(event, fps) / 60,
        y: getOverlayMetricValue(event, overlayMetric),
        startTimeSeconds: getContractionStartTimeSeconds(event, fps),
        durationSeconds: event.duration_s,
        speedMmPerS: event.velocity_phys_per_s,
        areaMm2S: event.area_exact,
      }));

  return {
    bars,
    overlayPoints,
    xMaxMinutes: (lastBin?.endTimeSeconds ?? 0) / 60,
    partialBinNote: getContractionPartialBinNote(summary),
    rightAxisLabel: getContractionOverlayMetricLabel(overlayMetric),
  };
}

export function createContractionDetectionParameters(
  parameters?: ContractionDetectionParameters | null
): ContractionDetectionParameters {
  return canonicalizeContractionDetectionParameters(parameters);
}

export function getContractionDetectionPresets(): readonly ContractionDetectionPreset[] {
  return CONTRACTION_DETECTION_PRESETS;
}

export function getContractionDetectionPresetId(
  parameters?: ContractionDetectionParameters | null
): ContractionDetectionPresetId | 'custom' {
  const matchingPreset = CONTRACTION_DETECTION_PRESETS.find((preset) =>
    areContractionDetectionParametersEqual(parameters, preset.parameters)
  );

  return matchingPreset?.id ?? 'custom';
}

export function getContractionDetectionPreset(
  presetId: ContractionDetectionPresetId
): ContractionDetectionPreset {
  const preset = CONTRACTION_DETECTION_PRESETS.find((item) => item.id === presetId);
  if (!preset) {
    throw new Error(`Unknown contraction detection preset: ${presetId}`);
  }
  return preset;
}

export function getContractionDetectionPresetLabel(
  presetId: ContractionDetectionPresetId | 'custom'
): string {
  if (presetId === 'custom') {
    return 'Custom';
  }
  return getContractionDetectionPreset(presetId).label;
}

export function areContractionDetectionParametersEqual(
  left?: ContractionDetectionParameters | null,
  right?: ContractionDetectionParameters | null
): boolean {
  const normalizedLeft = canonicalizeContractionDetectionParameters(left);
  const normalizedRight = canonicalizeContractionDetectionParameters(right);

  return (
    normalizedLeft.smooth_sigma_y === normalizedRight.smooth_sigma_y &&
    normalizedLeft.smooth_sigma_t === normalizedRight.smooth_sigma_t &&
    normalizedLeft.threshold_percentile === normalizedRight.threshold_percentile &&
    normalizedLeft.threshold === normalizedRight.threshold &&
    normalizedLeft.open_iters === normalizedRight.open_iters &&
    normalizedLeft.close_iters === normalizedRight.close_iters &&
    normalizedLeft.min_pixels === normalizedRight.min_pixels &&
    normalizedLeft.min_duration_s === normalizedRight.min_duration_s &&
    normalizedLeft.min_span_mm === normalizedRight.min_span_mm &&
    normalizedLeft.area_threshold_median_fraction === normalizedRight.area_threshold_median_fraction &&
    normalizedLeft.merge_max_gap_s === normalizedRight.merge_max_gap_s &&
    normalizedLeft.merge_max_offset_mm === normalizedRight.merge_max_offset_mm &&
    normalizedLeft.merge_max_velocity_delta_mm_s === normalizedRight.merge_max_velocity_delta_mm_s &&
    normalizedLeft.min_area === normalizedRight.min_area &&
    normalizedLeft.min_height === normalizedRight.min_height &&
    normalizedLeft.dy === normalizedRight.dy
  );
}

export function getContractionOverlayMetricLabel(
  metric: ContractionOverlayMetric
): string | null {
  switch (metric) {
    case 'none':
      return null;
    case 'speed':
      return 'Propagation speed (mm/s)';
    case 'duration':
      return 'Duration (s)';
    case 'area':
      return 'Area (mm²·s)';
  }
}

export function isLegacyContractionDetection(
  detectionVersion: string | null | undefined
): boolean {
  return Boolean(detectionVersion && detectionVersion !== CONTRACTION_DETECTION_VERSION_V2);
}

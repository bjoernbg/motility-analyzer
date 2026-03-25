import { colormapValueToRgb } from './colormap';

export const DEFAULT_TOPOGRAPHY_MAX_COLUMNS = 512;
const MIN_RANGE = 1e-9;
const HEIGHT_SCALE_RATIO = 0.2;
const MIN_FOOTPRINT_ASPECT_RATIO = 1;
const MAX_FOOTPRINT_ASPECT_RATIO = 2;
const DEFAULT_AXIS_TICK_COUNT = 5;

export interface HeatmapTopographyMetrics {
  columnCount: number;
  footprintAspectRatio: number;
  frameCenterOffset: number;
  frameCount: number;
  heightScale: number;
  maxHeight: number;
  pointCenterOffset: number;
  pointCount: number;
  yScale: number;
}

export interface HeatmapTopographySurface {
  colors: Float32Array;
  frameWindows: Array<[startFrame: number, endFrameExclusive: number]>;
  indices: Uint32Array;
  metrics: HeatmapTopographyMetrics;
  positions: Float32Array;
}

export interface HeatmapTopographySurfaceOptions {
  colormap: Uint8Array;
  frameCount: number;
  heatmapMaxMm: number;
  heatmapMinMm: number;
  maxColumns?: number;
  pixelToMmFactor: number;
  pointCount: number;
  values: Float32Array;
}

export interface HeatmapTopographyFrameLine {
  positions: Float32Array;
}

export interface HeatmapTopographyAxisTick {
  label: string;
  position: number;
}

export interface HeatmapTopographyAxes {
  bounds: {
    maxX: number;
    maxY: number;
    maxZ: number;
    minX: number;
    minY: number;
    minZ: number;
  };
  xLabel: string;
  xTicks: HeatmapTopographyAxisTick[];
  yLabel: string;
  yTicks: HeatmapTopographyAxisTick[];
  zLabel: string;
  zTicks: HeatmapTopographyAxisTick[];
}

export interface HeatmapTopographyFrameLineOptions {
  frame: number | null | undefined;
  heatmapMaxMm: number;
  heatmapMinMm: number;
  metrics: HeatmapTopographyMetrics;
  pixelToMmFactor: number;
  values: Float32Array;
}

export interface BuildHeatmapTopographyAxesOptions {
  fps: number;
  heatmapMaxMm: number;
  heatmapMinMm: number;
  metrics: HeatmapTopographyMetrics;
}

function clamp(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

function createEmptySurface(frameCount: number, pointCount: number): HeatmapTopographySurface {
  return {
    colors: new Float32Array(0),
    frameWindows: [],
    indices: new Uint32Array(0),
    metrics: {
      columnCount: 0,
      footprintAspectRatio: MIN_FOOTPRINT_ASPECT_RATIO,
      frameCenterOffset: Math.max(0, (frameCount - 1) / 2),
      frameCount,
      heightScale: 1,
      maxHeight: 0,
      pointCenterOffset: 0,
      pointCount,
      yScale: 1,
    },
    positions: new Float32Array(0),
  };
}

export function convertHeatmapPixelValueToMm(valuePx: number, pixelToMmFactor: number): number {
  const safeFactor = Math.max(pixelToMmFactor, MIN_RANGE);
  return valuePx / safeFactor;
}

export function normalizeHeatmapMmValue(
  valueMm: number,
  heatmapMinMm: number,
  heatmapMaxMm: number,
): number {
  const range = Math.max(heatmapMaxMm - heatmapMinMm, MIN_RANGE);
  return clamp((valueMm - heatmapMinMm) / range, 0, 1);
}

export function resolveTopographyFootprintAspectRatio(
  frameCount: number,
  pointCount: number,
): number {
  if (frameCount <= 0 || pointCount <= 0) {
    return MIN_FOOTPRINT_ASPECT_RATIO;
  }

  return clamp(
    frameCount / pointCount,
    MIN_FOOTPRINT_ASPECT_RATIO,
    MAX_FOOTPRINT_ASPECT_RATIO,
  );
}

export function mapTopographyNormalizedValueToHeight(
  normalizedValue: number,
  heightScale: number,
): number {
  return (1 - clamp(normalizedValue, 0, 1)) * Math.max(heightScale, 0);
}

export function mapHeatmapMmValueToTopographyHeight(
  valueMm: number,
  heatmapMinMm: number,
  heatmapMaxMm: number,
  heightScale: number,
): number {
  return mapTopographyNormalizedValueToHeight(
    normalizeHeatmapMmValue(valueMm, heatmapMinMm, heatmapMaxMm),
    heightScale,
  );
}

export function resolveTopographyColumnCount(
  frameCount: number,
  maxColumns = DEFAULT_TOPOGRAPHY_MAX_COLUMNS,
): number {
  if (frameCount <= 0) {
    return 0;
  }

  return Math.min(frameCount, Math.max(1, Math.floor(maxColumns)));
}

export function buildHeatmapTopographySurface(
  options: HeatmapTopographySurfaceOptions,
): HeatmapTopographySurface {
  const {
    colormap,
    frameCount,
    heatmapMaxMm,
    heatmapMinMm,
    maxColumns = DEFAULT_TOPOGRAPHY_MAX_COLUMNS,
    pixelToMmFactor,
    pointCount,
    values,
  } = options;

  if (frameCount <= 0 || pointCount <= 0 || values.length === 0) {
    return createEmptySurface(frameCount, pointCount);
  }

  const columnCount = resolveTopographyColumnCount(frameCount, maxColumns);
  if (columnCount <= 0) {
    return createEmptySurface(frameCount, pointCount);
  }

  const frameCenterOffset = Math.max(0, (frameCount - 1) / 2);
  const footprintAspectRatio = resolveTopographyFootprintAspectRatio(frameCount, pointCount);
  const frameSpan = Math.max(frameCount - 1, 1);
  const yScale = pointCount > 1 && frameCount > 1
    ? frameSpan / ((pointCount - 1) * footprintAspectRatio)
    : 1;
  const pointCenterOffset = Math.max(0, ((pointCount - 1) * yScale) / 2);
  const groundSpan = Math.max(frameCount - 1, (pointCount - 1) * yScale, 1);
  const heightScale = groundSpan * HEIGHT_SCALE_RATIO;
  const frameWindows: Array<[number, number]> = new Array(columnCount);
  const positions = new Float32Array(columnCount * pointCount * 3);
  const colors = new Float32Array(columnCount * pointCount * 3);
  let maxHeight = 0;

  for (let columnIndex = 0; columnIndex < columnCount; columnIndex += 1) {
    const startFrame = Math.floor((columnIndex * frameCount) / columnCount);
    const endFrameExclusive = Math.max(
      startFrame + 1,
      Math.floor(((columnIndex + 1) * frameCount) / columnCount),
    );
    const framePosition = columnCount === 1
      ? 0
      : (columnIndex / (columnCount - 1)) * (frameCount - 1);
    frameWindows[columnIndex] = [startFrame, endFrameExclusive];

    for (let pointIndex = 0; pointIndex < pointCount; pointIndex += 1) {
      let accumulatedValuePx = 0;
      let sampleCount = 0;

      for (let frame = startFrame; frame < endFrameExclusive; frame += 1) {
        accumulatedValuePx += values[frame * pointCount + pointIndex] ?? 0;
        sampleCount += 1;
      }

      const averageValuePx = sampleCount > 0 ? accumulatedValuePx / sampleCount : 0;
      const valueMm = convertHeatmapPixelValueToMm(averageValuePx, pixelToMmFactor);
      const normalizedValue = normalizeHeatmapMmValue(valueMm, heatmapMinMm, heatmapMaxMm);
      const [r, g, b] = colormapValueToRgb(colormap, normalizedValue);
      const height = mapTopographyNormalizedValueToHeight(normalizedValue, heightScale);
      const vertexOffset = (columnIndex * pointCount + pointIndex) * 3;

      positions[vertexOffset] = framePosition - frameCenterOffset;
      positions[vertexOffset + 1] = pointIndex * yScale - pointCenterOffset;
      positions[vertexOffset + 2] = height;

      colors[vertexOffset] = r;
      colors[vertexOffset + 1] = g;
      colors[vertexOffset + 2] = b;

      if (height > maxHeight) {
        maxHeight = height;
      }
    }
  }

  let indices = new Uint32Array(0);
  if (columnCount > 1 && pointCount > 1) {
    indices = new Uint32Array((columnCount - 1) * (pointCount - 1) * 6);
    let writeIndex = 0;

    for (let columnIndex = 0; columnIndex < columnCount - 1; columnIndex += 1) {
      for (let pointIndex = 0; pointIndex < pointCount - 1; pointIndex += 1) {
        const a = columnIndex * pointCount + pointIndex;
        const b = (columnIndex + 1) * pointCount + pointIndex;
        const c = a + 1;
        const d = b + 1;

        indices[writeIndex] = a;
        indices[writeIndex + 1] = b;
        indices[writeIndex + 2] = c;
        indices[writeIndex + 3] = c;
        indices[writeIndex + 4] = b;
        indices[writeIndex + 5] = d;
        writeIndex += 6;
      }
    }
  }

  return {
    colors,
    frameWindows,
    indices,
    metrics: {
      columnCount,
      footprintAspectRatio,
      frameCenterOffset,
      frameCount,
      heightScale,
      maxHeight,
      pointCenterOffset,
      pointCount,
      yScale,
    },
    positions,
  };
}

export function buildHeatmapTopographyFrameLine(
  options: HeatmapTopographyFrameLineOptions,
): HeatmapTopographyFrameLine | null {
  const {
    frame,
    heatmapMaxMm,
    heatmapMinMm,
    metrics,
    pixelToMmFactor,
    values,
  } = options;

  if (
    frame === null ||
    frame === undefined ||
    frame < 0 ||
    frame >= metrics.frameCount ||
    metrics.pointCount <= 0
  ) {
    return null;
  }

  const positions = new Float32Array(metrics.pointCount * 3);
  const lineOffset = Math.max(metrics.heightScale * 0.025, 0.05);

  for (let pointIndex = 0; pointIndex < metrics.pointCount; pointIndex += 1) {
    const valuePx = values[frame * metrics.pointCount + pointIndex] ?? 0;
    const valueMm = convertHeatmapPixelValueToMm(valuePx, pixelToMmFactor);
    const vertexOffset = pointIndex * 3;

    positions[vertexOffset] = frame - metrics.frameCenterOffset;
    positions[vertexOffset + 1] = pointIndex * metrics.yScale - metrics.pointCenterOffset;
    positions[vertexOffset + 2] = mapHeatmapMmValueToTopographyHeight(
      valueMm,
      heatmapMinMm,
      heatmapMaxMm,
      metrics.heightScale,
    ) + lineOffset;
  }

  return { positions };
}

function buildRoundedTickIndices(maxIndex: number, targetTickCount: number): number[] {
  if (maxIndex <= 0 || targetTickCount <= 1) {
    return [0];
  }

  const segments = Math.max(targetTickCount - 1, 1);
  const ticks = new Set<number>();
  for (let step = 0; step <= segments; step += 1) {
    ticks.add(Math.round((step / segments) * maxIndex));
  }

  return [...ticks].sort((left, right) => left - right);
}

function formatAxisNumber(value: number): string {
  const rounded = Math.round(value * 10) / 10;
  return Number.isInteger(rounded) ? `${rounded}` : rounded.toFixed(1);
}

export function buildHeatmapTopographyAxes(
  options: BuildHeatmapTopographyAxesOptions,
): HeatmapTopographyAxes {
  const {
    fps,
    heatmapMaxMm,
    heatmapMinMm,
    metrics,
  } = options;
  const minX = -metrics.frameCenterOffset;
  const maxX = Math.max(0, metrics.frameCount - 1) - metrics.frameCenterOffset;
  const minY = -metrics.pointCenterOffset;
  const maxY = Math.max(0, (metrics.pointCount - 1) * metrics.yScale) - metrics.pointCenterOffset;
  const minZ = 0;
  const maxZ = metrics.heightScale;
  const safeFps = Math.max(fps, MIN_RANGE);
  const xTickFrames = buildRoundedTickIndices(
    Math.max(metrics.frameCount - 1, 0),
    DEFAULT_AXIS_TICK_COUNT,
  );
  const yTickIndices = buildRoundedTickIndices(
    Math.max(metrics.pointCount - 1, 0),
    Math.min(metrics.pointCount, DEFAULT_AXIS_TICK_COUNT),
  );
  const zTickValues = heatmapMaxMm > heatmapMinMm
    ? buildRoundedTickIndices(DEFAULT_AXIS_TICK_COUNT - 1, DEFAULT_AXIS_TICK_COUNT)
        .map((step) => heatmapMinMm + (step / (DEFAULT_AXIS_TICK_COUNT - 1)) * (heatmapMaxMm - heatmapMinMm))
    : [heatmapMinMm];

  return {
    bounds: {
      maxX,
      maxY,
      maxZ,
      minX,
      minY,
      minZ,
    },
    xLabel: 'Time (s)',
    xTicks: xTickFrames.map((frame) => ({
      label: formatAxisNumber(frame / safeFps),
      position: frame - metrics.frameCenterOffset,
    })),
    yLabel: 'Point',
    yTicks: yTickIndices.map((pointIndex) => ({
      label: `${pointIndex}`,
      position: pointIndex * metrics.yScale - metrics.pointCenterOffset,
    })),
    zLabel: 'Distance (mm)',
    zTicks: zTickValues.map((valueMm) => ({
      label: formatAxisNumber(valueMm),
      position: mapHeatmapMmValueToTopographyHeight(
        valueMm,
        heatmapMinMm,
        heatmapMaxMm,
        metrics.heightScale,
      ),
    })),
  };
}

export function resolveTopographyFrameFromWorldX(
  worldX: number,
  metrics: HeatmapTopographyMetrics,
): number {
  return clamp(Math.round(worldX + metrics.frameCenterOffset), 0, Math.max(0, metrics.frameCount - 1));
}

export function resolveTopographyPointIndexFromWorldY(
  worldY: number,
  metrics: HeatmapTopographyMetrics,
): number {
  if (metrics.pointCount <= 1) {
    return 0;
  }

  const rawPointIndex = (worldY + metrics.pointCenterOffset) / metrics.yScale;
  return clamp(Math.round(rawPointIndex), 0, metrics.pointCount - 1);
}

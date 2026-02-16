import { ref, watch, type Ref } from 'vue';
import { getHeatmapMeta, getHeatmapRaw, type HeatmapMeta } from '../lib/api';
import { useHeatmapCache } from './useHeatmapCache';
import { PIXEL_TO_MM_FACTOR } from '../lib/constants';

interface LoadedHeatmapMm {
  meta: HeatmapMeta;
  valuesMm: Float32Array;
}

export interface HeatmapDiffMeta {
  width: number;
  height: number;
  fps: number;
  minTimeSec: number;
  maxTimeSec: number;
  diffAbsMaxMm: number;
}

interface UseHeatmapDiffOptions {
  leftAnalysisId: Ref<string | null | undefined>;
  rightAnalysisId: Ref<string | null | undefined>;
  minSyncedTimeSec: Ref<number>;
  maxSyncedTimeSec: Ref<number>;
  rightTimeShiftSec: Ref<number>;
  leftFps: Ref<number>;
  rightFps: Ref<number>;
}

const MAX_TRANSFORM_CACHE = 4;
const transformedCache = new Map<
  string,
  {
    meta: HeatmapDiffMeta;
    leftAlignedMm: Float32Array;
    rightAlignedMm: Float32Array;
    diffMm: Float32Array;
    timestamp: number;
  }
>();
const sourceHeatmapMmCache = new Map<string, LoadedHeatmapMm>();

function evictLru<T extends { timestamp: number }>(cache: Map<string, T>, maxEntries: number): void {
  if (cache.size < maxEntries) {
    return;
  }

  let oldestKey: string | null = null;
  let oldestTimestamp = Number.POSITIVE_INFINITY;
  for (const [key, entry] of cache.entries()) {
    if (entry.timestamp < oldestTimestamp) {
      oldestTimestamp = entry.timestamp;
      oldestKey = key;
    }
  }

  if (oldestKey) {
    cache.delete(oldestKey);
  }
}

function createGaussianKernel(sigma: number): Float32Array {
  if (sigma <= 0.01) {
    return new Float32Array([1]);
  }

  const radius = Math.max(1, Math.ceil(sigma * 3));
  const size = radius * 2 + 1;
  const kernel = new Float32Array(size);
  const sigma2 = sigma * sigma;
  let sum = 0;
  for (let i = -radius; i <= radius; i++) {
    const value = Math.exp(-(i * i) / (2 * sigma2));
    kernel[i + radius] = value;
    sum += value;
  }

  if (sum <= 0) {
    return new Float32Array([1]);
  }

  for (let i = 0; i < size; i++) {
    kernel[i] = (kernel[i] ?? 0) / sum;
  }
  return kernel;
}

function clampInt(value: number, min: number, max: number): number {
  if (value < min) return min;
  if (value > max) return max;
  return value;
}

function blurHeatmap(values: Float32Array, width: number, height: number, sigma: number): Float32Array {
  if (width <= 0 || height <= 0 || values.length === 0 || sigma <= 0.01) {
    return values.slice();
  }

  const kernel = createGaussianKernel(sigma);
  const radius = Math.floor(kernel.length / 2);
  const tmp = new Float32Array(values.length);
  const out = new Float32Array(values.length);

  for (let pointIndex = 0; pointIndex < height; pointIndex++) {
    for (let frameIndex = 0; frameIndex < width; frameIndex++) {
      let acc = 0;
      for (let k = -radius; k <= radius; k++) {
        const sourceFrame = clampInt(frameIndex + k, 0, width - 1);
        const sourceIndex = sourceFrame * height + pointIndex;
        acc += (values[sourceIndex] ?? 0) * (kernel[k + radius] ?? 0);
      }
      tmp[frameIndex * height + pointIndex] = acc;
    }
  }

  for (let frameIndex = 0; frameIndex < width; frameIndex++) {
    const base = frameIndex * height;
    for (let pointIndex = 0; pointIndex < height; pointIndex++) {
      let acc = 0;
      for (let k = -radius; k <= radius; k++) {
        const sourcePoint = clampInt(pointIndex + k, 0, height - 1);
        acc += (tmp[base + sourcePoint] ?? 0) * (kernel[k + radius] ?? 0);
      }
      out[base + pointIndex] = acc;
    }
  }

  return out;
}

function sampleInterpolated(
  valuesMm: Float32Array,
  width: number,
  height: number,
  sourceFps: number,
  timeSec: number,
  pointIndex: number
): number {
  if (width <= 0 || height <= 0 || sourceFps <= 0) {
    return 0;
  }

  const clampedPoint = clampInt(pointIndex, 0, height - 1);
  const framePosition = timeSec * sourceFps;

  if (!Number.isFinite(framePosition)) {
    return 0;
  }

  if (framePosition <= 0) {
    return valuesMm[clampedPoint] ?? 0;
  }

  const lastFrame = width - 1;
  if (framePosition >= lastFrame) {
    return valuesMm[lastFrame * height + clampedPoint] ?? 0;
  }

  const leftFrame = Math.floor(framePosition);
  const rightFrame = Math.min(lastFrame, leftFrame + 1);
  const t = framePosition - leftFrame;
  const left = valuesMm[leftFrame * height + clampedPoint] ?? 0;
  const right = valuesMm[rightFrame * height + clampedPoint] ?? 0;
  return left + (right - left) * t;
}

function percentileAbs(values: Float32Array, percentile: number): number {
  if (values.length === 0) {
    return 1;
  }

  const clamped = Math.min(1, Math.max(0, percentile));
  const targetSamples = 200_000;
  const stride = Math.max(1, Math.ceil(values.length / targetSamples));
  const sampled: number[] = [];
  for (let i = 0; i < values.length; i += stride) {
    sampled.push(Math.abs(values[i] ?? 0));
  }

  if (sampled.length === 0) {
    return 1;
  }

  sampled.sort((a, b) => a - b);
  const idx = Math.max(0, Math.min(sampled.length - 1, Math.floor(clamped * (sampled.length - 1))));
  return Math.max(1e-6, sampled[idx] ?? 1);
}

async function loadHeatmapMm(
  analysisId: string,
  heatmapCache: ReturnType<typeof useHeatmapCache>
): Promise<LoadedHeatmapMm> {
  const cachedConverted = sourceHeatmapMmCache.get(analysisId);
  if (cachedConverted) {
    return cachedConverted;
  }

  let meta: HeatmapMeta;
  let valuesPx: Float32Array;

  const cachedRaw = heatmapCache.getCached(analysisId);
  if (cachedRaw) {
    meta = cachedRaw.meta;
    valuesPx = cachedRaw.data;
  } else {
    const [metaResp, rawResp] = await Promise.all([
      getHeatmapMeta(analysisId),
      getHeatmapRaw(analysisId),
    ]);

    meta = { ...metaResp, width: rawResp.width, height: rawResp.height };
    valuesPx = new Float32Array(rawResp.buffer);
    heatmapCache.setCache(analysisId, meta, valuesPx);
  }

  const expectedSize = meta.width * meta.height;
  if (valuesPx.length !== expectedSize) {
    throw new Error(
      `Invalid heatmap size for ${analysisId}: expected ${expectedSize}, got ${valuesPx.length}`
    );
  }

  const factor = meta.display_settings?.pixel_to_mm_factor ?? PIXEL_TO_MM_FACTOR;
  const safeFactor = factor > 0 ? factor : PIXEL_TO_MM_FACTOR;
  const valuesMm = new Float32Array(valuesPx.length);
  for (let i = 0; i < valuesPx.length; i++) {
    valuesMm[i] = (valuesPx[i] ?? 0) / safeFactor;
  }

  const loaded = { meta, valuesMm };
  sourceHeatmapMmCache.set(analysisId, loaded);
  return loaded;
}

export function useHeatmapDiff(options: UseHeatmapDiffOptions) {
  const heatmapCache = useHeatmapCache();

  const isLoading = ref(false);
  const error = ref<string | null>(null);

  const meta = ref<HeatmapDiffMeta | null>(null);
  const leftAlignedMm = ref<Float32Array | null>(null);
  const rightAlignedMm = ref<Float32Array | null>(null);
  const diffMm = ref<Float32Array | null>(null);

  const blurSigma = ref(1.0);
  const deadbandMm = ref(0.15);
  const overlayAlpha = ref(0.45);

  let requestId = 0;

  async function recompute(): Promise<void> {
    const leftId = options.leftAnalysisId.value;
    const rightId = options.rightAnalysisId.value;
    if (!leftId || !rightId) {
      meta.value = null;
      leftAlignedMm.value = null;
      rightAlignedMm.value = null;
      diffMm.value = null;
      return;
    }

    const minSyncedTime = options.minSyncedTimeSec.value;
    const maxSyncedTime = options.maxSyncedTimeSec.value;
    const outputFps = Math.max(options.leftFps.value, options.rightFps.value, 1);

    if (!Number.isFinite(minSyncedTime) || !Number.isFinite(maxSyncedTime) || maxSyncedTime < minSyncedTime) {
      meta.value = null;
      leftAlignedMm.value = null;
      rightAlignedMm.value = null;
      diffMm.value = null;
      return;
    }

    const cacheKey = [
      leftId,
      rightId,
      minSyncedTime.toFixed(6),
      maxSyncedTime.toFixed(6),
      options.rightTimeShiftSec.value.toFixed(6),
      outputFps.toFixed(6),
      blurSigma.value.toFixed(3),
      deadbandMm.value.toFixed(3),
    ].join('|');

    const cachedTransform = transformedCache.get(cacheKey);
    if (cachedTransform) {
      cachedTransform.timestamp = Date.now();
      meta.value = cachedTransform.meta;
      leftAlignedMm.value = cachedTransform.leftAlignedMm;
      rightAlignedMm.value = cachedTransform.rightAlignedMm;
      diffMm.value = cachedTransform.diffMm;
      error.value = null;
      return;
    }

    const currentRequestId = ++requestId;
    isLoading.value = true;
    error.value = null;

    try {
      const [leftHeatmap, rightHeatmap] = await Promise.all([
        loadHeatmapMm(leftId, heatmapCache),
        loadHeatmapMm(rightId, heatmapCache),
      ]);

      if (currentRequestId !== requestId) {
        return;
      }

      if (
        leftHeatmap.meta.width === 0 ||
        leftHeatmap.meta.height === 0 ||
        rightHeatmap.meta.width === 0 ||
        rightHeatmap.meta.height === 0
      ) {
        meta.value = null;
        leftAlignedMm.value = null;
        rightAlignedMm.value = null;
        diffMm.value = null;
        error.value = 'No heatmap data available for one or both analyses.';
        return;
      }

      const height = Math.min(leftHeatmap.meta.height, rightHeatmap.meta.height);
      if (leftHeatmap.meta.height !== rightHeatmap.meta.height) {
        console.warn(
          `Heatmap height mismatch: left=${leftHeatmap.meta.height}, right=${rightHeatmap.meta.height}. Using min=${height}.`
        );
      }

      const spanSec = Math.max(0, maxSyncedTime - minSyncedTime);
      const width = Math.max(1, Math.floor(spanSec * outputFps) + 1);
      const alignedSize = width * height;
      const alignedLeft = new Float32Array(alignedSize);
      const alignedRight = new Float32Array(alignedSize);

      for (let frameIndex = 0; frameIndex < width; frameIndex++) {
        const syncedTime = minSyncedTime + frameIndex / outputFps;
        const rightTime = syncedTime + options.rightTimeShiftSec.value;
        const rowStart = frameIndex * height;

        for (let pointIndex = 0; pointIndex < height; pointIndex++) {
          alignedLeft[rowStart + pointIndex] = sampleInterpolated(
            leftHeatmap.valuesMm,
            leftHeatmap.meta.width,
            leftHeatmap.meta.height,
            leftHeatmap.meta.fps,
            syncedTime,
            pointIndex
          );
          alignedRight[rowStart + pointIndex] = sampleInterpolated(
            rightHeatmap.valuesMm,
            rightHeatmap.meta.width,
            rightHeatmap.meta.height,
            rightHeatmap.meta.fps,
            rightTime,
            pointIndex
          );
        }
      }

      const blurredLeft = blurHeatmap(alignedLeft, width, height, blurSigma.value);
      const blurredRight = blurHeatmap(alignedRight, width, height, blurSigma.value);

      const diff = new Float32Array(alignedSize);
      for (let i = 0; i < alignedSize; i++) {
        const delta = (blurredLeft[i] ?? 0) - (blurredRight[i] ?? 0);
        diff[i] = Math.abs(delta) < deadbandMm.value ? 0 : delta;
      }

      const diffAbsMaxMm = percentileAbs(diff, 0.95);
      const nextMeta: HeatmapDiffMeta = {
        width,
        height,
        fps: outputFps,
        minTimeSec: minSyncedTime,
        maxTimeSec: maxSyncedTime,
        diffAbsMaxMm,
      };

      meta.value = nextMeta;
      leftAlignedMm.value = blurredLeft;
      rightAlignedMm.value = blurredRight;
      diffMm.value = diff;

      evictLru(transformedCache, MAX_TRANSFORM_CACHE);
      transformedCache.set(cacheKey, {
        meta: nextMeta,
        leftAlignedMm: blurredLeft,
        rightAlignedMm: blurredRight,
        diffMm: diff,
        timestamp: Date.now(),
      });
    } catch (err) {
      if (currentRequestId !== requestId) {
        return;
      }
      meta.value = null;
      leftAlignedMm.value = null;
      rightAlignedMm.value = null;
      diffMm.value = null;
      error.value = err instanceof Error ? err.message : 'Failed to compute heatmap diff.';
    } finally {
      if (currentRequestId === requestId) {
        isLoading.value = false;
      }
    }
  }

  watch(
    () => [
      options.leftAnalysisId.value,
      options.rightAnalysisId.value,
      options.minSyncedTimeSec.value,
      options.maxSyncedTimeSec.value,
      options.rightTimeShiftSec.value,
      options.leftFps.value,
      options.rightFps.value,
      blurSigma.value,
      deadbandMm.value,
    ],
    () => {
      recompute();
    },
    { immediate: true }
  );

  return {
    isLoading,
    error,
    meta,
    leftAlignedMm,
    rightAlignedMm,
    diffMm,
    blurSigma,
    deadbandMm,
    overlayAlpha,
    recompute,
  };
}

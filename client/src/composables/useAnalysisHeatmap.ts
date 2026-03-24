import {
  computed,
  onMounted,
  onUnmounted,
  ref,
  toValue,
  watch,
  type MaybeRefOrGetter,
} from 'vue';

import { getHeatmapMeta, getHeatmapRaw, type HeatmapMeta } from '../lib/api';
import { HEATMAP_MAX_MM, HEATMAP_MIN_MM, PIXEL_TO_MM_FACTOR } from '../lib/constants';
import { useAnalysisStore } from '../stores/analysis';
import { useHeatmapCache } from './useHeatmapCache';

export interface UseAnalysisHeatmapOptions {
  analysisId: MaybeRefOrGetter<string | null | undefined>;
  pixelToMmFactorOverride?: MaybeRefOrGetter<number | null | undefined>;
  heatmapMinMmOverride?: MaybeRefOrGetter<number | null | undefined>;
  heatmapMaxMmOverride?: MaybeRefOrGetter<number | null | undefined>;
}

export function useAnalysisHeatmap(options: UseAnalysisHeatmapOptions) {
  const store = useAnalysisStore();
  const heatmapCache = useHeatmapCache();

  const meta = ref<HeatmapMeta | null>(null);
  const data = ref<Float32Array | null>(null);
  const isLoading = ref(true);
  const error = ref<string | null>(null);
  const isRefreshing = ref(false);
  const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null);

  const resolvedAnalysisId = computed(() => toValue(options.analysisId) ?? null);

  const pixelToMmFactor = computed(
    () =>
      toValue(options.pixelToMmFactorOverride) ??
      meta.value?.display_settings?.pixel_to_mm_factor ??
      PIXEL_TO_MM_FACTOR,
  );
  const heatmapMinMm = computed(
    () =>
      toValue(options.heatmapMinMmOverride) ??
      meta.value?.display_settings?.heatmap_min_mm ??
      HEATMAP_MIN_MM,
  );
  const heatmapMaxMm = computed(
    () =>
      toValue(options.heatmapMaxMmOverride) ??
      meta.value?.display_settings?.heatmap_max_mm ??
      HEATMAP_MAX_MM,
  );

  const hasExportableData = computed(() => {
    return Boolean(
      meta.value &&
      data.value &&
      meta.value.width > 0 &&
      meta.value.height > 0 &&
      !error.value,
    );
  });

  const hasRenderableData = computed(() => {
    return Boolean(
      meta.value &&
      data.value &&
      meta.value.width > 0 &&
      meta.value.height > 0,
    );
  });

  const isAnalysisProcessing = computed(() => {
    return (
      resolvedAnalysisId.value !== null &&
      store.currentAnalysis?.id === resolvedAnalysisId.value &&
      store.progressStatus === 'processing'
    );
  });

  function clearState(): void {
    meta.value = null;
    data.value = null;
    error.value = null;
    isLoading.value = false;
  }

  async function loadData(skipCache = false): Promise<void> {
    const analysisId = resolvedAnalysisId.value;
    if (!analysisId) {
      clearState();
      return;
    }

    try {
      if (!skipCache) {
        isLoading.value = true;
      }
      error.value = null;

      if (!skipCache) {
        const cached = heatmapCache.getCached(analysisId);
        if (cached) {
          meta.value = cached.meta;
          data.value = cached.data;
          isLoading.value = false;
          return;
        }
      }

      const metaResp = await getHeatmapMeta(analysisId);
      if (resolvedAnalysisId.value !== analysisId) {
        return;
      }

      if (metaResp.width === 0 || metaResp.height === 0) {
        if (!skipCache) {
          meta.value = metaResp;
          data.value = null;
          error.value = null;
        }
        return;
      }

      const rawResult = await getHeatmapRaw(analysisId);
      if (resolvedAnalysisId.value !== analysisId) {
        return;
      }

      const dataArray = new Float32Array(rawResult.buffer);
      const actualWidth = rawResult.width;
      const actualHeight = rawResult.height;

      if (actualWidth === 0 || actualHeight === 0) {
        if (!skipCache) {
          meta.value = metaResp;
          data.value = null;
          error.value = null;
        }
        return;
      }

      const expectedSize = actualWidth * actualHeight;
      if (dataArray.length !== expectedSize) {
        throw new Error(`Data size mismatch: expected ${expectedSize}, got ${dataArray.length}`);
      }

      const resolvedMeta: HeatmapMeta = {
        ...metaResp,
        width: actualWidth,
        height: actualHeight,
      };

      if (!skipCache) {
        heatmapCache.setCache(analysisId, resolvedMeta, dataArray);
      }

      meta.value = resolvedMeta;
      data.value = dataArray;
    } catch (err) {
      if (err instanceof Error && err.name === 'AbortError') {
        return;
      }

      if (resolvedAnalysisId.value === analysisId && !skipCache) {
        error.value = err instanceof Error ? err.message : 'Failed to load heatmap data';
        console.error('Failed to load heatmap data:', err);
      }
    } finally {
      if (resolvedAnalysisId.value === analysisId) {
        isLoading.value = false;
      }
    }
  }

  function stopLiveRefresh(): void {
    if (refreshTimer.value) {
      clearInterval(refreshTimer.value);
      refreshTimer.value = null;
    }
    isRefreshing.value = false;
  }

  function startLiveRefresh(): void {
    if (refreshTimer.value || !resolvedAnalysisId.value) {
      return;
    }

    refreshTimer.value = setInterval(async () => {
      if (isRefreshing.value) {
        return;
      }

      isRefreshing.value = true;
      try {
        await loadData(true);
      } finally {
        isRefreshing.value = false;
      }
    }, 5000);
  }

  onMounted(() => {
    void loadData();
    if (isAnalysisProcessing.value) {
      startLiveRefresh();
    }
  });

  onUnmounted(() => {
    stopLiveRefresh();
  });

  watch(resolvedAnalysisId, (analysisId, previousAnalysisId) => {
    if (analysisId === previousAnalysisId) {
      return;
    }

    meta.value = null;
    data.value = null;
    error.value = null;
    isLoading.value = Boolean(analysisId);

    if (!analysisId) {
      stopLiveRefresh();
      return;
    }

    void loadData();
  });

  watch(isAnalysisProcessing, (processing, wasProcessing) => {
    if (processing) {
      startLiveRefresh();
      return;
    }

    if (!wasProcessing || !resolvedAnalysisId.value) {
      return;
    }

    stopLiveRefresh();
    heatmapCache.invalidate(resolvedAnalysisId.value);
    void loadData();
  });

  return {
    data,
    error,
    hasExportableData,
    hasRenderableData,
    heatmapMaxMm,
    heatmapMinMm,
    isLoading,
    loadData,
    meta,
    pixelToMmFactor,
  };
}

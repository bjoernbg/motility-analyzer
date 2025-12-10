/**
 * Composable for caching heatmap data during a session.
 * Stores both metadata and raw binary data per analysis ID to enable
 * instant switching between analyses.
 */
import { ref } from 'vue';
import type { HeatmapMeta } from '../lib/api';

interface CachedHeatmap {
  meta: HeatmapMeta;
  data: Float32Array;
  timestamp: number;
}

// Session-level cache (persists across component instances)
const heatmapCache = ref<Map<string, CachedHeatmap>>(new Map());

// Maximum number of cached heatmaps to prevent memory issues
const MAX_CACHE_SIZE = 10;

export function useHeatmapCache() {
  /**
   * Get cached heatmap data for an analysis.
   * @returns The cached data or null if not cached.
   */
  function getCached(analysisId: string): CachedHeatmap | null {
    const cached = heatmapCache.value.get(analysisId);
    if (cached) {
      // Update timestamp for LRU behavior
      cached.timestamp = Date.now();
      return cached;
    }
    return null;
  }

  /**
   * Store heatmap data in the cache.
   */
  function setCache(analysisId: string, meta: HeatmapMeta, data: Float32Array): void {
    // Evict oldest entry if cache is full
    if (heatmapCache.value.size >= MAX_CACHE_SIZE) {
      let oldestKey: string | null = null;
      let oldestTime = Infinity;
      
      for (const [key, value] of heatmapCache.value.entries()) {
        if (value.timestamp < oldestTime) {
          oldestTime = value.timestamp;
          oldestKey = key;
        }
      }
      
      if (oldestKey) {
        heatmapCache.value.delete(oldestKey);
      }
    }

    heatmapCache.value.set(analysisId, {
      meta,
      data,
      timestamp: Date.now(),
    });
  }

  /**
   * Check if a heatmap is cached.
   */
  function isCached(analysisId: string): boolean {
    return heatmapCache.value.has(analysisId);
  }

  /**
   * Invalidate a specific cached heatmap.
   */
  function invalidate(analysisId: string): void {
    heatmapCache.value.delete(analysisId);
  }

  /**
   * Clear all cached heatmaps.
   */
  function clearAll(): void {
    heatmapCache.value.clear();
  }

  /**
   * Get cache statistics.
   */
  function getCacheStats(): { size: number; maxSize: number; analysisIds: string[] } {
    return {
      size: heatmapCache.value.size,
      maxSize: MAX_CACHE_SIZE,
      analysisIds: Array.from(heatmapCache.value.keys()),
    };
  }

  return {
    getCached,
    setCache,
    isCached,
    invalidate,
    clearAll,
    getCacheStats,
  };
}


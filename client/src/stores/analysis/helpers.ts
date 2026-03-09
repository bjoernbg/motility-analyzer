import type { AnalysisParameters, FrameData } from '../../lib/api';
import { parametersMatch as domainParametersMatch } from '../../lib/domain/analysisParameters';

export interface FrameCacheEntry {
  data: FrameData;
  lastAccessed: number;
}

export function buildFrameCacheKey(analysisId: string, frameNum: number): string {
  return `${analysisId}:${frameNum}`;
}

export function evictLeastRecentlyUsedFrame(
  cache: Map<string, FrameCacheEntry>,
  maxCacheSize: number
): void {
  if (cache.size < maxCacheSize) {
    return;
  }

  let oldestKey: string | null = null;
  let oldestTimestamp = Infinity;

  for (const [key, entry] of cache.entries()) {
    if (entry.lastAccessed < oldestTimestamp) {
      oldestTimestamp = entry.lastAccessed;
      oldestKey = key;
    }
  }

  if (oldestKey) {
    cache.delete(oldestKey);
  }
}

export function keepOnlyAnalysisFrames(
  cache: Map<string, FrameCacheEntry>,
  analysisId: string
): void {
  const prefix = `${analysisId}:`;
  const keysToDelete: string[] = [];

  for (const key of cache.keys()) {
    if (!key.startsWith(prefix)) {
      keysToDelete.push(key);
    }
  }

  for (const key of keysToDelete) {
    cache.delete(key);
  }
}

export function parametersMatch(
  params1: Record<string, unknown>,
  params2: AnalysisParameters
): boolean {
  return domainParametersMatch(params1, params2);
}

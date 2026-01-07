<script setup lang="ts">
import { ref, computed } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import { Button } from './ui/button';
import type { WaveDetectionParameters } from '../lib/api';

const store = useAnalysisStore();

const showAdvanced = ref(false);
const parameters = ref<WaveDetectionParameters>({
  smooth_sigma_y: 1.0,
  smooth_sigma_t: 1.0,
  threshold_percentile: 10.0,
  open_iters: 1,
  close_iters: 2,
  min_pixels: 200,
});

const canDetectWaves = computed(() => {
  return store.currentAnalysis?.status === 'completed' && !store.isDetectingWaves;
});

const hasWaveEvents = computed(() => {
  return store.waveEvents.length > 0;
});

async function handleDetectWaves() {
  if (!store.currentAnalysis) return;
  
  try {
    await store.detectWavesForAnalysis(store.currentAnalysis.id, parameters.value);
  } catch (err) {
    console.error('Failed to detect waves:', err);
  }
}

async function handleClearWaves() {
  if (!store.currentAnalysis) return;
  
  if (confirm('Clear all wave detection results?')) {
    try {
      await store.clearWaveEventsForAnalysis(store.currentAnalysis.id);
    } catch (err) {
      console.error('Failed to clear wave events:', err);
    }
  }
}
</script>

<template>
  <div class="wave-detection-controls">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold">Wave Detection</h3>
      <div class="flex gap-2">
        <Button
          v-if="hasWaveEvents"
          variant="outline"
          size="sm"
          @click="handleClearWaves"
        >
          Clear Results
        </Button>
        <Button
          :disabled="!canDetectWaves"
          @click="handleDetectWaves"
        >
          {{ hasWaveEvents ? 'Re-detect Waves' : 'Detect Waves' }}
        </Button>
      </div>
    </div>

    <div v-if="store.isDetectingWaves" class="text-sm text-muted-foreground mb-4">
      Detecting waves...
    </div>

    <div v-if="store.waveDetectionError" class="text-sm text-destructive mb-4">
      Error: {{ store.waveDetectionError }}
    </div>

    <div v-if="hasWaveEvents" class="text-sm text-muted-foreground mb-4">
      Detected {{ store.waveEvents.length }} wave event(s)
    </div>

    <details v-if="!hasWaveEvents || showAdvanced" class="mb-4">
      <summary class="cursor-pointer text-sm font-medium mb-2">
        Advanced Parameters
      </summary>
      <div class="space-y-3 mt-2 p-3 bg-muted rounded-md">
        <div class="grid grid-cols-2 gap-3">
          <div>
            <label class="text-xs font-medium">Smoothing Sigma Y</label>
            <input
              v-model.number="parameters.smooth_sigma_y"
              type="number"
              step="0.1"
              min="0"
              class="w-full mt-1 px-2 py-1 text-sm border rounded"
            />
          </div>
          <div>
            <label class="text-xs font-medium">Smoothing Sigma T</label>
            <input
              v-model.number="parameters.smooth_sigma_t"
              type="number"
              step="0.1"
              min="0"
              class="w-full mt-1 px-2 py-1 text-sm border rounded"
            />
          </div>
          <div>
            <label class="text-xs font-medium">Threshold Percentile</label>
            <input
              v-model.number="parameters.threshold_percentile"
              type="number"
              step="0.1"
              min="0"
              max="100"
              class="w-full mt-1 px-2 py-1 text-sm border rounded"
            />
          </div>
          <div>
            <label class="text-xs font-medium">Min Pixels</label>
            <input
              v-model.number="parameters.min_pixels"
              type="number"
              step="1"
              min="1"
              class="w-full mt-1 px-2 py-1 text-sm border rounded"
            />
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<style scoped>
.wave-detection-controls {
  padding: 1rem;
  border: 1px solid hsl(var(--border));
  border-radius: 0.5rem;
  background: hsl(var(--card));
}
</style>


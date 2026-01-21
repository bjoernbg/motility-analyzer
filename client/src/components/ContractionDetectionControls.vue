<script setup lang="ts">
import { ref, computed } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import { Button } from './ui/button';
import type { ContractionDetectionParameters } from '../lib/api';

const store = useAnalysisStore();

const showAdvanced = ref(false);
const parameters = ref<ContractionDetectionParameters>({
  smooth_sigma_y: 1.0,
  smooth_sigma_t: 1.0,
  threshold_percentile: 10.0,
  open_iters: 1,
  close_iters: 2,
  min_pixels: 200,
  min_area: null,
  min_height: null,
});

const canDetectContractions = computed(() => {
  return store.currentAnalysis?.status === 'completed' && !store.isDetectingContractions;
});

const hasContractionEvents = computed(() => {
  return store.contractionEvents.length > 0;
});

async function handleDetectContractions() {
  if (!store.currentAnalysis) return;
  
  try {
    await store.detectContractionsForAnalysis(store.currentAnalysis.id, parameters.value);
  } catch (err) {
    console.error('Failed to detect contractions:', err);
  }
}

async function handleClearContractions() {
  if (!store.currentAnalysis) return;
  
  if (confirm('Clear all contraction detection results?')) {
    try {
      await store.clearContractionEventsForAnalysis(store.currentAnalysis.id);
    } catch (err) {
      console.error('Failed to clear contraction events:', err);
    }
  }
}
</script>

<template>
  <div class="contraction-detection-controls">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold">Contraction Detection</h3>
      <div class="flex gap-2">
        <Button
          v-if="hasContractionEvents"
          variant="outline"
          size="sm"
          @click="handleClearContractions"
        >
          Clear Results
        </Button>
        <Button
          :disabled="!canDetectContractions"
          @click="handleDetectContractions"
        >
          {{ hasContractionEvents ? 'Re-detect Contractions' : 'Detect Contractions' }}
        </Button>
      </div>
    </div>

    <div v-if="store.isDetectingContractions" class="text-sm text-muted-foreground mb-4">
      Detecting contractions...
    </div>

    <div v-if="store.contractionDetectionError" class="text-sm text-destructive mb-4">
      Error: {{ store.contractionDetectionError }}
    </div>

    <div v-if="hasContractionEvents" class="text-sm text-muted-foreground mb-4">
      Detected {{ store.contractionEvents.length }} contraction event(s)
    </div>

    <details v-if="!hasContractionEvents || showAdvanced" class="mb-4">
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
            <div class="text-xs text-muted-foreground mt-0.5">
              Spatial smoothing (higher = smoother across tracking points)
            </div>
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
            <div class="text-xs text-muted-foreground mt-0.5">
              Temporal smoothing (higher = smoother across time)
            </div>
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
            <div class="text-xs text-muted-foreground mt-0.5">
              Lower values detect more contractions (0-100)
            </div>
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
            <div class="text-xs text-muted-foreground mt-0.5">
              Filter events with fewer pixels (removes noise)
            </div>
          </div>
          <div>
            <label class="text-xs font-medium">Min Area (mm²·s)</label>
            <input
              v-model.number="parameters.min_area"
              type="number"
              step="0.1"
              min="0"
              placeholder="No filter"
              class="w-full mt-1 px-2 py-1 text-sm border rounded"
            />
            <div class="text-xs text-muted-foreground mt-0.5">
              Filter events below this area
            </div>
          </div>
          <div>
            <label class="text-xs font-medium">Min Height (mm)</label>
            <input
              v-model.number="parameters.min_height"
              type="number"
              step="0.1"
              min="0"
              placeholder="No filter"
              class="w-full mt-1 px-2 py-1 text-sm border rounded"
            />
            <div class="text-xs text-muted-foreground mt-0.5">
              Filter events below this height
            </div>
          </div>
        </div>
      </div>
    </details>
  </div>
</template>

<style scoped>
.contraction-detection-controls {
  padding: 1rem;
  border: 1px solid hsl(var(--border));
  border-radius: 0.5rem;
  background: hsl(var(--card));
}
</style>


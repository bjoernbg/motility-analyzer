<script setup lang="ts">
import { computed, ref, watch } from 'vue';

import type { ContractionDetectionParameters } from '../lib/api';
import { useAnalysisStore } from '../stores/analysis';
import {
  areContractionDetectionParametersEqual,
  buildContractionSummary,
  createContractionDetectionParameters,
  getContractionDetectionPresetId,
} from '../lib/domain/contractions';
import ContractionDetectionControls from './ContractionDetectionControls.vue';
import ContractionEventsList from './ContractionEventsList.vue';
import ContractionSummary from './ContractionSummary.vue';

const store = useAnalysisStore();
const emit = defineEmits<{
  'select-contraction': [contractionId: string | null];
}>();

const videoDuration = computed(() => store.currentVideo?.metadata?.duration ?? null);
const videoFps = computed(() => store.currentVideo?.metadata?.fps ?? null);
const contractionSummary = computed(() =>
  buildContractionSummary(
    store.contractionEvents,
    videoFps.value,
    videoDuration.value
  )
);

const hasResults = computed(() => store.currentAnalysis !== null);
const hasContractionEvents = computed(() => store.contractionEvents.length > 0);
const canDetectContractions = computed(() => {
  return store.currentAnalysis?.status === 'completed' && !store.isDetectingContractions;
});

const detectionParametersDraft = ref<ContractionDetectionParameters>(
  createContractionDetectionParameters()
);
const selectedContractionId = ref<string | null>(null);

const detectionParametersDirty = computed(() =>
  !areContractionDetectionParametersEqual(
    detectionParametersDraft.value,
    store.contractionDetectionParametersUsed
  )
);
const draftPresetId = computed(() =>
  getContractionDetectionPresetId(detectionParametersDraft.value)
);
const loadedPresetId = computed(() => {
  if (!store.contractionDetectionParametersUsed) {
    return null;
  }

  return getContractionDetectionPresetId(store.contractionDetectionParametersUsed);
});

watch(
  () => store.currentAnalysis?.id,
  () => {
    selectedContractionId.value = null;
    emit('select-contraction', null);
  }
);

watch(
  () => store.contractionDetectionParametersUsed,
  (parametersUsed) => {
    detectionParametersDraft.value = createContractionDetectionParameters(parametersUsed);
  },
  { immediate: true, deep: true }
);

watch(
  () => store.contractionEvents,
  (events) => {
    if (selectedContractionId.value && !events.some((event) => event.id === selectedContractionId.value)) {
      selectedContractionId.value = null;
      emit('select-contraction', null);
    }
  },
  { deep: true }
);

function handleJumpToFrame(frame: number) {
  void store.seekToFrame(frame);
}

function handleDetectionParametersUpdate(nextParameters: ContractionDetectionParameters) {
  detectionParametersDraft.value = createContractionDetectionParameters(nextParameters);
}

function handleResetToResults() {
  detectionParametersDraft.value = createContractionDetectionParameters(
    store.contractionDetectionParametersUsed
  );
}

async function handleDetectContractions() {
  if (!store.currentAnalysis) {
    return;
  }

  try {
    await store.detectContractionsForAnalysis(
      store.currentAnalysis.id,
      detectionParametersDraft.value
    );
  } catch (err) {
    console.error('Failed to detect contractions:', err);
  }
}

async function handleClearContractions() {
  if (!store.currentAnalysis) {
    return;
  }

  if (confirm('Clear all contraction detection results?')) {
    try {
      await store.clearContractionEventsForAnalysis(store.currentAnalysis.id);
      selectedContractionId.value = null;
      emit('select-contraction', null);
    } catch (err) {
      console.error('Failed to clear contraction events:', err);
    }
  }
}

function handleSelectContraction(contractionId: string) {
  selectedContractionId.value = contractionId;
  emit('select-contraction', contractionId);
}
</script>

<template>
  <div class="analysis-results">
    <div v-if="!store.currentAnalysis" class="empty-panel">
      No analysis has been run yet.
    </div>

    <div v-else-if="store.isProcessing" class="empty-panel">
      Analysis in progress. Results will appear here when complete.
    </div>

    <div v-else-if="store.progressStatus === 'failed'" class="status-panel failed-panel">
      Analysis failed. Please try again.
    </div>

    <div v-else-if="store.progressStatus === 'cancelled'" class="status-panel cancelled-panel">
      Analysis was cancelled.
    </div>

    <div v-else-if="!hasResults" class="empty-panel">
      No results available yet.
    </div>

    <div v-else class="results-content">
      <div class="results-shell">
        <div class="overview-section">
          <ContractionSummary
            :summary="contractionSummary"
            :detection-version="store.contractionDetectionVersion"
            :events="store.contractionEvents"
            :fps="videoFps"
            :selected-contraction-id="selectedContractionId"
            @select-contraction="handleSelectContraction"
          />
        </div>

        <div class="detection-section">
          <ContractionDetectionControls
            :model-value="detectionParametersDraft"
            :parameters-used="store.contractionDetectionParametersUsed"
            :draft-preset-id="draftPresetId"
            :loaded-preset-id="loadedPresetId"
            :is-dirty="detectionParametersDirty"
            :has-contraction-events="hasContractionEvents"
            :can-detect="canDetectContractions"
            :is-detecting="store.isDetectingContractions"
            :detection-error="store.contractionDetectionError"
            @update:model-value="handleDetectionParametersUpdate"
            @detect="handleDetectContractions"
            @clear="handleClearContractions"
            @reset-to-results="handleResetToResults"
          />
        </div>

        <div class="events-section">
          <ContractionEventsList
            :events="store.contractionEvents"
            :fps="videoFps"
            :selected-contraction-id="selectedContractionId"
            @jump-to-frame="handleJumpToFrame"
            @select-contraction="handleSelectContraction"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.results-content {
  display: grid;
  gap: 1rem;
}

.results-shell {
  display: grid;
  gap: 0.75rem;
  grid-template-columns: repeat(12, minmax(0, 1fr));
}

.overview-section,
.events-section,
.detection-section {
  grid-column: span 12;
}

.empty-panel,
.status-panel {
  padding: 1.5rem;
  border-radius: 0.7rem;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
}

.failed-panel {
  color: var(--color-error-600);
  background: var(--color-error-100);
}

.cancelled-panel {
  color: var(--color-warning-600);
  background: var(--color-warning-100);
}

@media (min-width: 1080px) {
  .overview-section {
    grid-column: span 8;
  }

  .detection-section {
    grid-column: span 4;
  }

  .events-section {
    grid-column: span 12;
  }
}
</style>

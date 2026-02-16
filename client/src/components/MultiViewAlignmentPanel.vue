<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';

const store = useAnalysisStore();

const localShiftSec = ref(0);

watch(
  () => store.rightTimeShiftSec,
  (value) => {
    localShiftSec.value = value;
  },
  { immediate: true }
);

const suggestion = computed(() => store.latestAlignmentSuggestion);
const hasSuggestion = computed(() => suggestion.value !== null);
const realignJob = computed(() => store.realignJob);
const canStartAutoFix = computed(() => {
  if (store.isStartingAutoReanalyze) return false;
  return hasSuggestion.value && (!realignJob.value || realignJob.value.status !== 'running');
});

const confidencePercent = computed(() => {
  if (!suggestion.value) return null;
  return Math.round((suggestion.value.time_shift.confidence ?? 0) * 100);
});

async function handleAnalyzeAlignment() {
  await store.computeMultiViewAlignment({ applyTimeShift: true, sampleFrames: 7, maxShiftSec: 3.0 });
}

async function handleApplyShift() {
  await store.setMultiViewTimeShift(localShiftSec.value);
}

async function handleAutoFixWindows() {
  await store.startAutoReanalyzeFromAlignment();
}
</script>

<template>
  <section class="alignment-panel">
    <div class="alignment-header">
      <h4>Alignment</h4>
      <Button size="sm" :disabled="store.isComputingAlignment" @click="handleAnalyzeAlignment">
        {{ store.isComputingAlignment ? 'Analyzing...' : 'Analyze Alignment' }}
      </Button>
    </div>

    <div v-if="suggestion" class="alignment-suggestion">
      <p class="alignment-row">
        Time shift:
        <strong>{{ suggestion.time_shift.right_time_shift_sec.toFixed(3) }}s</strong>
        ({{ suggestion.time_shift.method }}, {{ confidencePercent }}%)
      </p>
      <p v-if="suggestion.time_shift.warning" class="alignment-warning">
        {{ suggestion.time_shift.warning }}
      </p>
      <p class="alignment-row">
        Window Δ:
        <strong>L {{ suggestion.window.left_window_delta_px }}px</strong>,
        <strong>R {{ suggestion.window.right_window_delta_px }}px</strong>
      </p>
      <p class="alignment-row">
        Right margin Δ:
        <strong>{{ suggestion.window.right_margin_delta_px.toFixed(1) }}px</strong>
      </p>
      <p class="alignment-row small">
        Suggested windows:
        L {{ suggestion.window.left_suggested_x_left ?? '-' }} ↔ {{ suggestion.window.left_suggested_x_right ?? '-' }},
        R {{ suggestion.window.right_suggested_x_left ?? '-' }} ↔ {{ suggestion.window.right_suggested_x_right ?? '-' }}
      </p>
    </div>

    <div class="manual-shift">
      <Label for="right-shift-input">Manual Right Time Shift (s)</Label>
      <div class="manual-shift-row">
        <Input
          id="right-shift-input"
          v-model.number="localShiftSec"
          type="number"
          step="0.01"
        />
        <Button
          size="sm"
          variant="outline"
          :disabled="store.isUpdatingAlignment"
          @click="handleApplyShift"
        >
          {{ store.isUpdatingAlignment ? 'Saving...' : 'Apply' }}
        </Button>
      </div>
    </div>

    <div class="autofix">
      <Button
        size="sm"
        variant="outline"
        :disabled="!canStartAutoFix"
        @click="handleAutoFixWindows"
      >
        {{ store.isStartingAutoReanalyze ? 'Starting...' : 'Auto-Fix Windows' }}
      </Button>
      <p v-if="realignJob" class="job-status">
        Job {{ realignJob.id.slice(0, 8) }}: {{ realignJob.status }}
      </p>
      <p v-if="realignJob?.error" class="alignment-warning">
        {{ realignJob.error }}
      </p>
    </div>
  </section>
</template>

<style scoped>
.alignment-panel {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 0.65rem;
  background: var(--bg-secondary);
  display: flex;
  flex-direction: column;
  gap: 0.65rem;
}

.alignment-header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  gap: 0.5rem;
}

.alignment-header h4 {
  margin: 0;
  font-size: 0.86rem;
}

.alignment-suggestion {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.alignment-row {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-primary);
}

.alignment-row.small {
  font-size: 0.74rem;
  color: var(--text-secondary);
}

.alignment-warning {
  margin: 0;
  font-size: 0.75rem;
  color: var(--color-error-600);
}

.manual-shift {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.manual-shift-row {
  display: flex;
  gap: 0.4rem;
}

.autofix {
  display: flex;
  flex-direction: column;
  gap: 0.3rem;
}

.job-status {
  margin: 0;
  font-size: 0.76rem;
  color: var(--text-secondary);
}
</style>

<script setup lang="ts">
import { computed, shallowRef } from 'vue';

import type { ContractionDetectionParameters } from '../lib/api';
import {
  createContractionDetectionParameters,
  getContractionDetectionPreset,
  getContractionDetectionPresetLabel,
  getContractionDetectionPresets,
  type ContractionDetectionPresetId,
} from '../lib/domain/contractions';
import { Button } from './ui/button';

const props = defineProps<{
  modelValue: ContractionDetectionParameters;
  parametersUsed: ContractionDetectionParameters | null;
  draftPresetId: ContractionDetectionPresetId | 'custom';
  loadedPresetId: ContractionDetectionPresetId | 'custom' | null;
  isDirty: boolean;
  hasContractionEvents: boolean;
  canDetect: boolean;
  isDetecting: boolean;
  detectionError: string | null;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: ContractionDetectionParameters];
  detect: [];
  clear: [];
  'reset-to-results': [];
}>();

const showAdvanced = shallowRef(false);

const presets = getContractionDetectionPresets();

const hasLoadedParameters = computed(() => props.parametersUsed !== null);

const draftStateLabel = computed(() => {
  if (props.isDirty) {
    return `Draft: ${getContractionDetectionPresetLabel(props.draftPresetId)}`;
  }

  if (props.loadedPresetId) {
    return `Current: ${getContractionDetectionPresetLabel(props.loadedPresetId)}`;
  }

  return `Default: ${getContractionDetectionPresetLabel('balanced')}`;
});

function updateParameters(partial: Partial<ContractionDetectionParameters>) {
  emit('update:modelValue', {
    ...props.modelValue,
    ...partial,
  });
}

function applyPreset(presetId: ContractionDetectionPresetId) {
  emit('update:modelValue', createContractionDetectionParameters(
    getContractionDetectionPreset(presetId).parameters
  ));
}

function handleAdvancedToggle(event: Event) {
  showAdvanced.value = (event.target as HTMLDetailsElement).open;
}

function handleNumericInput(
  key: keyof ContractionDetectionParameters,
  event: Event,
  nullable = false
) {
  const rawValue = (event.target as HTMLInputElement).value;
  if (rawValue === '' && nullable) {
    updateParameters({ [key]: null } as Partial<ContractionDetectionParameters>);
    return;
  }

  const nextValue = Number(rawValue);
  if (Number.isNaN(nextValue)) {
    return;
  }

  updateParameters({ [key]: nextValue } as Partial<ContractionDetectionParameters>);
}

function handleAreaThresholdInput(event: Event) {
  const nextValue = Number((event.target as HTMLInputElement).value);
  if (Number.isNaN(nextValue)) {
    return;
  }

  updateParameters({
    area_threshold_median_fraction: nextValue / 100,
  });
}
</script>

<template>
  <aside class="contraction-detection-controls">
    <div class="controls-header">
      <div class="heading-group">
        <div class="title-row">
          <h3>Contraction Detection</h3>
          <span class="draft-state" :data-dirty="props.isDirty">{{ draftStateLabel }}</span>
        </div>
      </div>

      <div class="action-row">
        <Button
          v-if="props.hasContractionEvents"
          variant="ghost"
          size="sm"
          @click="emit('clear')"
        >
          Remove result
        </Button>
        <Button
          v-if="hasLoadedParameters"
          variant="outline"
          size="sm"
          :disabled="!props.isDirty"
          @click="emit('reset-to-results')"
        >
          Reset changes
        </Button>
        <Button
          :disabled="!props.canDetect"
          @click="emit('detect')"
        >
          {{ props.hasContractionEvents ? 'Run detection again' : 'Run detection' }}
        </Button>
      </div>
    </div>

    <div v-if="props.isDetecting" class="status-text">
      Detecting contractions...
    </div>

    <div v-if="props.detectionError" class="error-text">
      Error: {{ props.detectionError }}
    </div>

    <div class="preset-row">
      <button
        v-for="preset in presets"
        :key="preset.id"
        type="button"
        class="preset-button"
        :data-active="props.draftPresetId === preset.id"
        @click="applyPreset(preset.id)"
      >
        {{ preset.label }}
        <span v-if="props.loadedPresetId === preset.id" class="preset-chip">Current</span>
      </button>
    </div>

    <details class="advanced-panel" :open="showAdvanced" @toggle="handleAdvancedToggle">
      <summary>Advanced settings <span class="advanced-hint">Threshold, smoothing, merge rules</span></summary>

      <div class="advanced-grid">
        <div class="control-field">
          <label for="min-duration">Minimum Duration (s)</label>
          <input
            id="min-duration"
            :value="props.modelValue.min_duration_s ?? ''"
            type="number"
            step="0.1"
            min="0"
            @input="handleNumericInput('min_duration_s', $event)"
          />
        </div>

        <div class="control-field">
          <label for="min-span">Minimum Span (mm)</label>
          <input
            id="min-span"
            :value="props.modelValue.min_span_mm ?? ''"
            type="number"
            step="0.1"
            min="0"
            @input="handleNumericInput('min_span_mm', $event, true)"
          />
        </div>

        <div class="control-field">
          <label for="area-threshold">Area Threshold (% of median)</label>
          <input
            id="area-threshold"
            :value="Math.round((props.modelValue.area_threshold_median_fraction ?? 0.7) * 100)"
            type="number"
            step="1"
            min="1"
            max="100"
            @input="handleAreaThresholdInput"
          />
        </div>

        <div class="control-field">
          <label for="sigma-y">Smoothing Sigma Y</label>
          <input
            id="sigma-y"
            :value="props.modelValue.smooth_sigma_y ?? ''"
            type="number"
            step="0.1"
            min="0"
            @input="handleNumericInput('smooth_sigma_y', $event)"
          />
        </div>

        <div class="control-field">
          <label for="sigma-t">Smoothing Sigma T</label>
          <input
            id="sigma-t"
            :value="props.modelValue.smooth_sigma_t ?? ''"
            type="number"
            step="0.1"
            min="0"
            @input="handleNumericInput('smooth_sigma_t', $event)"
          />
        </div>

        <div class="control-field">
          <label for="threshold-percentile">Threshold Percentile</label>
          <input
            id="threshold-percentile"
            :value="props.modelValue.threshold_percentile ?? ''"
            type="number"
            step="0.1"
            min="0"
            max="100"
            @input="handleNumericInput('threshold_percentile', $event)"
          />
        </div>

        <div class="control-field">
          <label for="min-pixels">Minimum Seed Pixels</label>
          <input
            id="min-pixels"
            :value="props.modelValue.min_pixels ?? ''"
            type="number"
            step="1"
            min="1"
            @input="handleNumericInput('min_pixels', $event)"
          />
        </div>

        <div class="control-field">
          <label for="merge-gap">Merge Max Gap (s)</label>
          <input
            id="merge-gap"
            :value="props.modelValue.merge_max_gap_s ?? ''"
            type="number"
            step="0.1"
            min="0"
            @input="handleNumericInput('merge_max_gap_s', $event)"
          />
        </div>

        <div class="control-field">
          <label for="merge-offset">Merge Max Offset (mm)</label>
          <input
            id="merge-offset"
            :value="props.modelValue.merge_max_offset_mm ?? ''"
            type="number"
            step="0.1"
            min="0"
            @input="handleNumericInput('merge_max_offset_mm', $event)"
          />
        </div>

        <div class="control-field">
          <label for="merge-velocity">Merge Max Speed Delta (mm/s)</label>
          <input
            id="merge-velocity"
            :value="props.modelValue.merge_max_velocity_delta_mm_s ?? ''"
            type="number"
            step="0.1"
            min="0"
            @input="handleNumericInput('merge_max_velocity_delta_mm_s', $event)"
          />
        </div>

        <div class="control-field">
          <label for="open-iters">Opening Iterations</label>
          <input
            id="open-iters"
            :value="props.modelValue.open_iters ?? ''"
            type="number"
            step="1"
            min="0"
            @input="handleNumericInput('open_iters', $event)"
          />
        </div>

        <div class="control-field">
          <label for="close-iters">Closing Iterations</label>
          <input
            id="close-iters"
            :value="props.modelValue.close_iters ?? ''"
            type="number"
            step="1"
            min="0"
            @input="handleNumericInput('close_iters', $event)"
          />
        </div>

        <div class="control-field">
          <label for="min-area">Optional Min Area (mm²·s)</label>
          <input
            id="min-area"
            :value="props.modelValue.min_area ?? ''"
            type="number"
            step="0.1"
            min="0"
            placeholder="No filter"
            @input="handleNumericInput('min_area', $event, true)"
          />
        </div>
      </div>
    </details>
  </aside>
</template>

<style scoped>
.contraction-detection-controls {
  padding: 0.85rem;
  border: 1px solid hsl(var(--border));
  border-radius: 1rem;
  background: hsl(var(--card));
  display: grid;
  gap: 0.65rem;
  align-content: start;
}

.controls-header {
  display: flex;
  justify-content: space-between;
  align-items: flex-start;
  gap: 1rem;
}

.heading-group {
  min-width: 0;
}

.title-row {
  display: flex;
  align-items: center;
  gap: 0.65rem;
  flex-wrap: wrap;
}

.controls-header h3 {
  margin: 0;
  font-size: 1rem;
  font-weight: 600;
}

.draft-state {
  border-radius: 999px;
  background: hsl(var(--muted));
  color: hsl(var(--muted-foreground));
  padding: 0.2rem 0.6rem;
  font-size: 0.76rem;
  font-weight: 600;
}

.preset-chip {
  border-radius: 999px;
  background: hsl(var(--primary) / 0.1);
  color: hsl(var(--primary));
  padding: 0.12rem 0.45rem;
  font-size: 0.7rem;
  font-weight: 700;
}

.draft-state[data-dirty='true'] {
  background: hsl(var(--primary) / 0.1);
  color: hsl(var(--primary));
}

.action-row {
  display: flex;
  gap: 0.45rem;
  flex-wrap: wrap;
  justify-content: flex-end;
}

.status-text,
.error-text {
  font-size: 0.9rem;
}

.error-text {
  color: hsl(var(--destructive));
}

.preset-row {
  display: flex;
  flex-wrap: wrap;
  gap: 0.4rem;
}

.preset-button {
  display: inline-flex;
  align-items: center;
  gap: 0.4rem;
  border: 1px solid hsl(var(--border));
  border-radius: 0.5rem;
  background: hsl(var(--background));
  padding: 0.4rem 0.75rem;
  font: inherit;
  font-size: 0.85rem;
  font-weight: 600;
  cursor: pointer;
  transition: border-color 0.15s ease, box-shadow 0.15s ease;
}

.preset-button:hover {
  border-color: hsl(var(--primary) / 0.3);
}

.preset-button[data-active='true'] {
  border-color: hsl(var(--primary));
  box-shadow: 0 0 0 2px hsl(var(--primary) / 0.12);
}

.advanced-panel {
  border-top: 1px solid hsl(var(--border));
  padding-top: 1rem;
}

.advanced-panel summary {
  cursor: pointer;
  font-weight: 600;
  font-size: 0.88rem;
  color: hsl(var(--foreground));
}

.advanced-hint {
  font-weight: 400;
  font-size: 0.8rem;
  color: hsl(var(--muted-foreground));
  margin-left: 0.25rem;
}

.advanced-grid {
  display: grid;
  gap: 0.6rem;
  grid-template-columns: repeat(auto-fit, minmax(170px, 1fr));
  margin-top: 0.7rem;
}

.control-field {
  display: flex;
  flex-direction: column;
  gap: 0.38rem;
}

.control-field label {
  font-size: 0.76rem;
  font-weight: 600;
  color: hsl(var(--muted-foreground));
}

.control-field input {
  border: 1px solid hsl(var(--border));
  border-radius: 0.5rem;
  background: hsl(var(--background));
  padding: 0.4rem 0.6rem;
  font: inherit;
  font-size: 0.88rem;
}

.control-field input:focus {
  outline: none;
  border-color: hsl(var(--primary));
  box-shadow: 0 0 0 3px hsl(var(--primary) / 0.12);
}

@media (max-width: 900px) {
  .controls-header {
    flex-direction: column;
    align-items: stretch;
  }

  .action-row {
    justify-content: flex-start;
  }
}
</style>

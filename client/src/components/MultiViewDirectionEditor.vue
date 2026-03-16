<script setup lang="ts">
import type { MultiViewAnalysisDirection } from '../lib/api';
import {
  formatMultiViewDirection,
  selectMultiViewDirection,
} from '../lib/domain/multiViewDirections';
import { Label } from './ui/label';

const props = withDefaults(
  defineProps<{
    leftDirection: MultiViewAnalysisDirection;
    rightDirection: MultiViewAnalysisDirection;
    disabled?: boolean;
    firstLabel?: string;
    secondLabel?: string;
    title?: string;
    hint?: string | null;
  }>(),
  {
    disabled: false,
    firstLabel: 'First Analysis',
    secondLabel: 'Second Analysis',
    title: undefined,
    hint: null,
  }
);

const emit = defineEmits<{
  updateDirections: [
    directions: {
      leftDirection: MultiViewAnalysisDirection;
      rightDirection: MultiViewAnalysisDirection;
      isValid: boolean;
    },
  ];
}>();

function handleDirectionChange(
  slot: 'left' | 'right',
  rawDirection: string
) {
  if (rawDirection !== 'front' && rawDirection !== 'bottom') {
    return;
  }

  emit(
    'updateDirections',
    selectMultiViewDirection(
      {
        leftDirection: props.leftDirection,
        rightDirection: props.rightDirection,
      },
      slot,
      rawDirection
    )
  );
}

function handleSelectChange(slot: 'left' | 'right', event: Event) {
  const target = event.target;
  if (!(target instanceof HTMLSelectElement)) {
    return;
  }

  handleDirectionChange(slot, target.value);
}
</script>

<template>
  <section class="direction-editor">
    <div v-if="title || hint" class="direction-editor-header">
      <h4 v-if="title" class="direction-editor-title">{{ title }}</h4>
      <p v-if="hint" class="direction-editor-hint">{{ hint }}</p>
    </div>

    <div class="direction-editor-grid">
      <div class="direction-field">
        <Label class="direction-label">{{ firstLabel }}</Label>
        <select
          class="direction-select"
          :disabled="disabled"
          :value="leftDirection"
          @change="handleSelectChange('left', $event)"
        >
          <option value="front">{{ formatMultiViewDirection('front') }}</option>
          <option value="bottom">{{ formatMultiViewDirection('bottom') }}</option>
        </select>
      </div>

      <div class="direction-field">
        <Label class="direction-label">{{ secondLabel }}</Label>
        <select
          class="direction-select"
          :disabled="disabled"
          :value="rightDirection"
          @change="handleSelectChange('right', $event)"
        >
          <option value="front">{{ formatMultiViewDirection('front') }}</option>
          <option value="bottom">{{ formatMultiViewDirection('bottom') }}</option>
        </select>
      </div>
    </div>
  </section>
</template>

<style scoped>
.direction-editor {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.direction-editor-header {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.direction-editor-title {
  margin: 0;
  font-size: 0.86rem;
}

.direction-editor-hint {
  margin: 0;
  font-size: 0.77rem;
  color: var(--text-secondary);
}

.direction-editor-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.75rem;
}

.direction-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.direction-label {
  font-size: 0.78rem;
}

.direction-select {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 0.45rem 0.5rem;
  background: var(--bg-primary);
}

@media (max-width: 720px) {
  .direction-editor-grid {
    grid-template-columns: 1fr;
  }
}
</style>

<template>
  <Teleport to="body">
    <Transition name="modal">
      <div v-if="modelValue" class="modal-overlay" @click="handleOverlayClick">
        <div class="modal-container" @click.stop>
          <div class="modal-header">
            <h2 class="modal-title">Combine Analyses</h2>
            <button class="close-button" @click="closeDialog">
              <Icon name="lucide:x" size="1.25em" />
            </button>
          </div>

          <div class="modal-body">
            <div class="form-field">
              <Label for="combination-name">Combination Name</Label>
              <Input
                id="combination-name"
                v-model="combinationName"
                placeholder="e.g., Front + Side View"
                @keyup.enter="handleSubmit"
              />
            </div>

            <div class="form-field">
              <Label for="second-analysis">Select Second Analysis</Label>
              <select
                id="second-analysis"
                v-model="selectedAnalysisId"
                class="analysis-select"
              >
                <option value="">-- Select Analysis --</option>
                <option
                  v-for="analysis in availableAnalyses"
                  :key="analysis.id"
                  :value="analysis.id"
                >
                  {{ formatAnalysisName(analysis) }}
                </option>
              </select>
            </div>

            <!-- Validation Results -->
            <div v-if="validationResult" class="validation-results">
              <!-- Errors -->
              <div v-if="validationResult.errors.length > 0" class="errors-box">
                <div class="errors-title">
                  <Icon name="lucide:alert-circle" size="1.1em" />
                  <span>Incompatible:</span>
                </div>
                <ul class="errors-list">
                  <li v-for="(error, index) in validationResult.errors" :key="index">
                    {{ error }}
                  </li>
                </ul>
              </div>

              <!-- Warnings -->
              <div v-if="validationResult.warnings.length > 0" class="warnings-box">
                <div class="warnings-title">
                  <Icon name="lucide:alert-triangle" size="1.1em" />
                  <span>Warnings:</span>
                </div>
                <ul class="warnings-list">
                  <li v-for="(warning, index) in validationResult.warnings" :key="index">
                    {{ warning }}
                  </li>
                </ul>
              </div>

              <!-- Success indicator -->
              <div v-if="validationResult.compatible && validationResult.warnings.length === 0" class="success-box">
                <Icon name="lucide:check-circle" size="1.1em" />
                <span>Analyses are compatible!</span>
              </div>
            </div>
          </div>

          <div class="modal-footer">
            <Button variant="outline" @click="closeDialog">
              Cancel
            </Button>
            <Button
              @click="handleSubmit"
              :disabled="!canSubmit || isValidating || isCreating"
            >
              <span v-if="isCreating">Creating...</span>
              <span v-else>Create Combination</span>
            </Button>
          </div>
        </div>
      </div>
    </Transition>
  </Teleport>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import type { Analysis, CompatibilityCheckResult } from '../lib/api';
import { validateCombination } from '../lib/api';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Input } from './ui/input';
import Icon from './ui/icon/Icon.vue';

const props = defineProps<{
  modelValue: boolean;
  currentAnalysisId: string;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
  'created': [];
}>();

const store = useAnalysisStore();

const combinationName = ref('');
const selectedAnalysisId = ref('');
const validationResult = ref<CompatibilityCheckResult | null>(null);
const isValidating = ref(false);
const isCreating = ref(false);

// Filter out the current analysis from available analyses
const availableAnalyses = computed(() => {
  return store.availableAnalyses.filter(
    (a) => a.id !== props.currentAnalysisId && a.status === 'completed'
  );
});

const canSubmit = computed(() => {
  return (
    combinationName.value.trim().length > 0 &&
    selectedAnalysisId.value !== '' &&
    validationResult.value?.compatible === true
  );
});

function formatAnalysisName(analysis: Analysis): string {
  const date = new Date(analysis.created_at).toLocaleString();
  const method = analysis.parameters?.edge_detection_method || 'unknown';
  return `${date} - ${method}`;
}

function closeDialog() {
  emit('update:modelValue', false);
  // Reset form
  combinationName.value = '';
  selectedAnalysisId.value = '';
  validationResult.value = null;
}

function handleOverlayClick() {
  closeDialog();
}

async function handleSubmit() {
  if (!canSubmit.value) return;

  try {
    isCreating.value = true;
    await store.createCombinedAnalysis(
      combinationName.value,
      props.currentAnalysisId,
      selectedAnalysisId.value
    );
    emit('created');
    closeDialog();
  } catch (error) {
    console.error('Failed to create combination:', error);
  } finally {
    isCreating.value = false;
  }
}

// Debounced validation
let validationTimeout: ReturnType<typeof setTimeout> | null = null;

watch(selectedAnalysisId, async (newId) => {
  if (!newId) {
    validationResult.value = null;
    return;
  }

  // Clear existing timeout
  if (validationTimeout) {
    clearTimeout(validationTimeout);
  }

  // Debounce validation
  validationTimeout = setTimeout(async () => {
    try {
      isValidating.value = true;
      validationResult.value = await validateCombination(
        props.currentAnalysisId,
        newId
      );
    } catch (error) {
      console.error('Validation failed:', error);
      validationResult.value = {
        compatible: false,
        errors: ['Failed to validate combination. Please try again.'],
        warnings: [],
        details: {}
      };
    } finally {
      isValidating.value = false;
    }
  }, 500);
});

// Reset when dialog is opened
watch(() => props.modelValue, (isOpen) => {
  if (isOpen) {
    // Suggest a default name if both videos have filenames
    if (store.currentVideo?.filename) {
      const video1Name = store.currentVideo.filename.replace(/\.[^/.]+$/, '');
      combinationName.value = `${video1Name} - Combined View`;
    }
  }
});
</script>

<style scoped>
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-container {
  background: white;
  border-radius: 0.5rem;
  box-shadow: 0 20px 25px -5px rgba(0, 0, 0, 0.1), 0 10px 10px -5px rgba(0, 0, 0, 0.04);
  max-width: 500px;
  width: 90%;
  max-height: 90vh;
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.5rem;
  border-bottom: 1px solid #e5e7eb;
}

.modal-title {
  font-size: 1.25rem;
  font-weight: 600;
  color: #111827;
  margin: 0;
}

.close-button {
  background: none;
  border: none;
  color: #6b7280;
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 0.25rem;
  transition: all 0.2s;
}

.close-button:hover {
  background: #f3f4f6;
  color: #111827;
}

.modal-body {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
}

.form-field {
  margin-bottom: 1.5rem;
}

.form-field:last-child {
  margin-bottom: 0;
}

.analysis-select {
  width: 100%;
  padding: 0.5rem 0.75rem;
  border: 1px solid #d1d5db;
  border-radius: 0.375rem;
  font-size: 0.875rem;
  background: white;
  cursor: pointer;
}

.analysis-select:focus {
  outline: none;
  border-color: #2563eb;
  box-shadow: 0 0 0 3px rgba(37, 99, 235, 0.1);
}

.validation-results {
  margin-top: 1rem;
}

.errors-box,
.warnings-box,
.success-box {
  padding: 0.75rem 1rem;
  border-radius: 0.375rem;
  margin-bottom: 0.75rem;
}

.errors-box {
  background: #fef2f2;
  border: 1px solid #fecaca;
}

.warnings-box {
  background: #fffbeb;
  border: 1px solid #fde68a;
}

.success-box {
  background: #f0fdf4;
  border: 1px solid #bbf7d0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
  color: #16a34a;
}

.errors-title,
.warnings-title {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  font-weight: 600;
  margin-bottom: 0.5rem;
}

.errors-title {
  color: #dc2626;
}

.warnings-title {
  color: #d97706;
}

.errors-list,
.warnings-list {
  margin: 0;
  padding-left: 1.5rem;
  font-size: 0.875rem;
}

.errors-list {
  color: #991b1b;
}

.warnings-list {
  color: #92400e;
}

.errors-list li,
.warnings-list li {
  margin-bottom: 0.25rem;
}

.modal-footer {
  display: flex;
  justify-content: flex-end;
  gap: 0.75rem;
  padding: 1.5rem;
  border-top: 1px solid #e5e7eb;
}

/* Modal transition */
.modal-enter-active,
.modal-leave-active {
  transition: opacity 0.2s;
}

.modal-enter-active .modal-container,
.modal-leave-active .modal-container {
  transition: transform 0.2s, opacity 0.2s;
}

.modal-enter-from,
.modal-leave-to {
  opacity: 0;
}

.modal-enter-from .modal-container,
.modal-leave-to .modal-container {
  transform: scale(0.95);
  opacity: 0;
}
</style>

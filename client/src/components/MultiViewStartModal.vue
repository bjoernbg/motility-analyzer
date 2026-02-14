<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import { listAnalyses, type Analysis, type MultiViewValidationResult } from '../lib/api';
import { Button } from './ui/button';
import { Input } from './ui/input';
import { Label } from './ui/label';
import { Icon } from './ui/icon';

const props = defineProps<{
  modelValue: boolean;
}>();

const emit = defineEmits<{
  'update:modelValue': [value: boolean];
}>();

const store = useAnalysisStore();

const sessionName = ref('');
const leftVideoId = ref('');
const rightVideoId = ref('');
const leftAnalysisId = ref('');
const rightAnalysisId = ref('');

const leftCompletedAnalyses = ref<Analysis[]>([]);
const rightCompletedAnalyses = ref<Analysis[]>([]);

const validationResult = ref<MultiViewValidationResult | null>(null);
const isValidating = ref(false);
const isCreating = ref(false);
const deletingSessionId = ref<string | null>(null);

let validationTimeout: ReturnType<typeof setTimeout> | null = null;

const canCreate = computed(() => {
  return (
    sessionName.value.trim().length > 0 &&
    leftAnalysisId.value.length > 0 &&
    rightAnalysisId.value.length > 0 &&
    validationResult.value?.compatible === true
  );
});

function closeModal() {
  emit('update:modelValue', false);
}

function resetForm() {
  sessionName.value = '';
  leftVideoId.value = '';
  rightVideoId.value = '';
  leftAnalysisId.value = '';
  rightAnalysisId.value = '';
  leftCompletedAnalyses.value = [];
  rightCompletedAnalyses.value = [];
  validationResult.value = null;
}

async function loadCompletedAnalysesForVideo(videoId: string): Promise<Analysis[]> {
  if (!videoId) return [];
  const analyses = await listAnalyses(videoId, 'completed', 200, 0);
  return analyses
    .filter((analysis) => analysis.status === 'completed')
    .sort((a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime());
}

function formatAnalysisLabel(analysis: Analysis): string {
  const createdAt = new Date(analysis.created_at).toLocaleString();
  const trackingPoints = analysis.parameters?.num_tracking_points ?? 'unknown';
  return `${createdAt} · ${trackingPoints} pts`;
}

async function runValidation() {
  if (!leftAnalysisId.value || !rightAnalysisId.value) {
    validationResult.value = null;
    return;
  }

  try {
    isValidating.value = true;
    validationResult.value = await store.validateMultiViewSelection(
      leftAnalysisId.value,
      rightAnalysisId.value
    );
  } catch (err) {
    const errorMessage = err instanceof Error ? err.message : 'Failed to validate pair';
    validationResult.value = {
      compatible: false,
      errors: [errorMessage],
      details: {},
    };
  } finally {
    isValidating.value = false;
  }
}

async function createSession() {
  if (!canCreate.value) return;

  try {
    isCreating.value = true;
    await store.createMultiViewSession(
      sessionName.value.trim(),
      leftAnalysisId.value,
      rightAnalysisId.value
    );
    closeModal();
    resetForm();
  } catch (err) {
    console.error('Failed to create multi-view session:', err);
  } finally {
    isCreating.value = false;
  }
}

async function openSession(sessionId: string) {
  try {
    await store.selectMultiViewSession(sessionId);
    closeModal();
  } catch (err) {
    console.error('Failed to open multi-view session:', err);
  }
}

async function deleteSession(sessionId: string) {
  try {
    deletingSessionId.value = sessionId;
    await store.deleteMultiViewSessionById(sessionId);
  } catch (err) {
    console.error('Failed to delete multi-view session:', err);
  } finally {
    deletingSessionId.value = null;
  }
}

watch(
  () => props.modelValue,
  async (isOpen) => {
    if (!isOpen) return;

    await Promise.all([
      store.loadVideos(),
      store.loadMultiViewSessions(),
    ]);

    if (!sessionName.value) {
      sessionName.value = `Multi-View ${new Date().toLocaleString()}`;
    }
  }
);

watch(leftVideoId, async (newVideoId) => {
  leftAnalysisId.value = '';
  validationResult.value = null;
  leftCompletedAnalyses.value = await loadCompletedAnalysesForVideo(newVideoId);
});

watch(rightVideoId, async (newVideoId) => {
  rightAnalysisId.value = '';
  validationResult.value = null;
  rightCompletedAnalyses.value = await loadCompletedAnalysesForVideo(newVideoId);
});

watch([leftAnalysisId, rightAnalysisId], () => {
  if (validationTimeout) {
    clearTimeout(validationTimeout);
  }

  validationTimeout = setTimeout(() => {
    runValidation();
  }, 300);
});
</script>

<template>
  <Teleport to="body">
    <div v-if="modelValue" class="modal-overlay" @click.self="closeModal">
      <div class="modal-container">
        <div class="modal-header">
          <h2>Start Combined Analysis</h2>
          <button class="close-button" @click="closeModal">
            <Icon name="lucide:x" size="1.2em" />
          </button>
        </div>

        <div class="modal-body">
          <div class="form-grid">
            <div class="form-field form-field-full">
              <Label for="session-name">Session Name</Label>
              <Input id="session-name" v-model="sessionName" placeholder="Front + Side" />
            </div>

            <div class="form-column">
              <h3>Left Side</h3>
              <div class="form-field">
                <Label for="left-video">Video</Label>
                <select id="left-video" v-model="leftVideoId" class="select-input">
                  <option value="">Select video</option>
                  <option v-for="video in store.videos" :key="video.id" :value="video.id">
                    {{ video.filename }}
                  </option>
                </select>
              </div>

              <div class="form-field">
                <Label for="left-analysis">Completed Analysis</Label>
                <select id="left-analysis" v-model="leftAnalysisId" class="select-input" :disabled="!leftVideoId">
                  <option value="">Select analysis</option>
                  <option v-for="analysis in leftCompletedAnalyses" :key="analysis.id" :value="analysis.id">
                    {{ formatAnalysisLabel(analysis) }}
                  </option>
                </select>
              </div>
            </div>

            <div class="form-column">
              <h3>Right Side</h3>
              <div class="form-field">
                <Label for="right-video">Video</Label>
                <select id="right-video" v-model="rightVideoId" class="select-input">
                  <option value="">Select video</option>
                  <option v-for="video in store.videos" :key="video.id" :value="video.id">
                    {{ video.filename }}
                  </option>
                </select>
              </div>

              <div class="form-field">
                <Label for="right-analysis">Completed Analysis</Label>
                <select id="right-analysis" v-model="rightAnalysisId" class="select-input" :disabled="!rightVideoId">
                  <option value="">Select analysis</option>
                  <option v-for="analysis in rightCompletedAnalyses" :key="analysis.id" :value="analysis.id">
                    {{ formatAnalysisLabel(analysis) }}
                  </option>
                </select>
              </div>
            </div>
          </div>

          <div v-if="isValidating" class="validation-box validation-pending">
            Validating selected analyses...
          </div>

          <div
            v-if="validationResult && validationResult.errors.length > 0"
            class="validation-box validation-error"
          >
            <strong>Incompatible selection</strong>
            <ul>
              <li v-for="(error, index) in validationResult.errors" :key="index">{{ error }}</li>
            </ul>
          </div>

          <div
            v-else-if="validationResult && validationResult.compatible"
            class="validation-box validation-success"
          >
            Analyses are compatible and ready for combined view.
          </div>

          <div class="sessions-section">
            <h3>Saved Sessions</h3>
            <div v-if="store.multiViewSessions.length === 0" class="empty-state">
              No saved sessions yet.
            </div>
            <div v-else class="session-list">
              <div v-for="session in store.multiViewSessions" :key="session.id" class="session-item">
                <div class="session-info">
                  <div class="session-name">{{ session.name }}</div>
                  <div class="session-date">{{ new Date(session.created_at).toLocaleString() }}</div>
                </div>
                <div class="session-actions">
                  <Button size="sm" variant="outline" @click="openSession(session.id)">
                    Open
                  </Button>
                  <Button
                    size="sm"
                    variant="outline"
                    :disabled="deletingSessionId === session.id"
                    @click="deleteSession(session.id)"
                  >
                    {{ deletingSessionId === session.id ? 'Deleting...' : 'Delete' }}
                  </Button>
                </div>
              </div>
            </div>
          </div>
        </div>

        <div class="modal-footer">
          <Button variant="outline" @click="closeModal">Cancel</Button>
          <Button :disabled="!canCreate || isCreating" @click="createSession">
            {{ isCreating ? 'Starting...' : 'Start Combined Analysis' }}
          </Button>
        </div>
      </div>
    </div>
  </Teleport>
</template>

<style scoped>
.modal-overlay {
  position: fixed;
  inset: 0;
  background: rgba(0, 0, 0, 0.55);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
}

.modal-container {
  width: min(1100px, 92vw);
  max-height: 90vh;
  background: var(--bg-primary);
  border-radius: 10px;
  border: 1px solid var(--border-light);
  display: flex;
  flex-direction: column;
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1rem 1.25rem;
  border-bottom: 1px solid var(--border-light);
}

.modal-header h2 {
  margin: 0;
  font-size: 1.15rem;
}

.close-button {
  width: 32px;
  height: 32px;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.modal-body {
  padding: 1rem 1.25rem;
  overflow: auto;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.form-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.form-field {
  display: flex;
  flex-direction: column;
  gap: 0.35rem;
}

.form-field-full {
  grid-column: 1 / -1;
}

.form-column {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 0.85rem;
  display: flex;
  flex-direction: column;
  gap: 0.7rem;
}

.form-column h3 {
  margin: 0;
  font-size: 0.95rem;
}

.select-input {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 0.45rem 0.5rem;
  background: var(--bg-primary);
}

.validation-box {
  border-radius: 8px;
  padding: 0.7rem 0.8rem;
  font-size: 0.9rem;
}

.validation-pending {
  background: var(--bg-secondary);
}

.validation-error {
  background: var(--color-error-100);
  border: 1px solid var(--color-error-300);
  color: var(--color-error-700);
}

.validation-success {
  background: var(--color-success-100);
  border: 1px solid var(--color-success-300);
  color: var(--color-success-700);
}

.validation-error ul {
  margin: 0.45rem 0 0 1.15rem;
  padding: 0;
}

.sessions-section {
  border-top: 1px solid var(--border-light);
  padding-top: 0.8rem;
}

.sessions-section h3 {
  margin: 0 0 0.7rem;
  font-size: 0.95rem;
}

.empty-state {
  color: var(--text-secondary);
  font-size: 0.9rem;
}

.session-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.session-item {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  padding: 0.65rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.session-name {
  font-weight: 600;
}

.session-date {
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.session-actions {
  display: flex;
  gap: 0.5rem;
}

.modal-footer {
  border-top: 1px solid var(--border-light);
  padding: 1rem 1.25rem;
  display: flex;
  justify-content: flex-end;
  gap: 0.6rem;
}

@media (max-width: 900px) {
  .form-grid {
    grid-template-columns: 1fr;
  }
}
</style>

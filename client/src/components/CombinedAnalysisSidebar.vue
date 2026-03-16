<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import type { MultiViewAnalysisDirection } from '../lib/api';
import {
  formatMultiViewDirection,
  type MultiViewDirectionPair,
} from '../lib/domain/multiViewDirections';
import { useAnalysisStore } from '../stores/analysis';
import MultiViewAlignmentPanel from './MultiViewAlignmentPanel.vue';
import MultiViewDirectionEditor from './MultiViewDirectionEditor.vue';
import { Button } from './ui/button';

const store = useAnalysisStore();

const hasLoadedSources = computed(() => {
  return Boolean(store.leftAnalysis && store.rightAnalysis && store.leftVideo && store.rightVideo);
});

const leftVideoName = computed(() => {
  return store.leftVideo ? getVideoName(store.leftVideo) : '';
});

const rightVideoName = computed(() => {
  return store.rightVideo ? getVideoName(store.rightVideo) : '';
});

const leftAnalysisName = computed(() => {
  return store.leftAnalysis ? getAnalysisName(store.leftAnalysis) : '';
});

const rightAnalysisName = computed(() => {
  return store.rightAnalysis ? getAnalysisName(store.rightAnalysis) : '';
});

const isCurrentSessionAutoAligned = computed(() => {
  const session = store.currentMultiViewSession;
  if (!session) {
    return false;
  }
  const alignmentSource = session.metadata?.alignment?.source;
  const realignStatus = session.metadata?.realign_job?.status;
  return alignmentSource === 'auto' || realignStatus === 'committed';
});

const localLeftDirection = ref<MultiViewAnalysisDirection>('front');
const localRightDirection = ref<MultiViewAnalysisDirection>('bottom');

watch(
  () => store.currentMultiViewDirections,
  (directions) => {
    localLeftDirection.value = directions.leftDirection;
    localRightDirection.value = directions.rightDirection;
  },
  { immediate: true }
);

const hasDirectionChanges = computed(() => {
  return (
    localLeftDirection.value !== store.currentMultiViewDirections.leftDirection ||
    localRightDirection.value !== store.currentMultiViewDirections.rightDirection
  );
});

const leftDirectionLabel = computed(() =>
  formatMultiViewDirection(store.currentMultiViewDirections.leftDirection)
);
const rightDirectionLabel = computed(() =>
  formatMultiViewDirection(store.currentMultiViewDirections.rightDirection)
);

function formatDate(value: string | undefined): string {
  if (!value) {
    return 'Unknown date';
  }
  return new Date(value).toLocaleString();
}

function getVideoName(video: { filename: string; display_name?: string | null }): string {
  const customName = video.display_name?.trim();
  return customName && customName.length > 0 ? customName : video.filename;
}

function getAnalysisName(analysis: { display_name?: string | null; created_at: string }): string {
  const customName = analysis.display_name?.trim();
  if (customName && customName.length > 0) {
    return customName;
  }
  return formatDate(analysis.created_at);
}

function handleDirectionsUpdate(directions: MultiViewDirectionPair) {
  localLeftDirection.value = directions.leftDirection;
  localRightDirection.value = directions.rightDirection;
}

async function saveDirections() {
  if (!store.currentMultiViewSession) {
    return;
  }

  try {
    await store.updateCurrentMultiViewDirections(
      localLeftDirection.value,
      localRightDirection.value
    );
  } catch (error) {
    console.error('Failed to update multi-view directions:', error);
  }
}
</script>

<template>
  <div class="combined-sidebar">
    <section class="sidebar-section">
      <h3>Analyses</h3>

      <div v-if="store.currentMultiViewSession" class="session-summary">
        <p class="session-name">
          {{ store.currentMultiViewSession.name }}
          <span v-if="isCurrentSessionAutoAligned" class="auto-aligned-badge">Auto-aligned</span>
        </p>
        <p class="session-date">Created {{ formatDate(store.currentMultiViewSession.created_at) }}</p>
        <div class="direction-summary">
          <span class="direction-badge">First: {{ leftDirectionLabel }}</span>
          <span class="direction-badge">Second: {{ rightDirectionLabel }}</span>
        </div>
      </div>
      <p v-else class="empty-text">No combined analysis selected.</p>

      <div v-if="store.currentMultiViewSession && hasLoadedSources" class="source-list">
        <div class="source-item">
          <div class="source-label-row">
            <p class="source-label">First Analysis</p>
            <span class="direction-badge">{{ leftDirectionLabel }}</span>
          </div>
          <p class="source-title">{{ leftVideoName }}</p>
          <p class="source-meta">{{ leftAnalysisName }}</p>
        </div>

        <div class="source-item">
          <div class="source-label-row">
            <p class="source-label">Second Analysis</p>
            <span class="direction-badge">{{ rightDirectionLabel }}</span>
          </div>
          <p class="source-title">{{ rightVideoName }}</p>
          <p class="source-meta">{{ rightAnalysisName }}</p>
        </div>
      </div>

      <p v-if="store.currentMultiViewSession && !hasLoadedSources" class="warning-text">
        This combined analysis references missing source analyses or videos. You can still delete it from the sidebar list.
      </p>
    </section>

    <section class="sidebar-section">
      <h3>Measurement Configuration</h3>
      <div v-if="store.currentMultiViewSession" class="direction-settings">
        <MultiViewDirectionEditor
          :left-direction="localLeftDirection"
          :right-direction="localRightDirection"
          :disabled="store.isUpdatingDirections"
          title="3D View Directions"
          hint="Front controls the model spine and height. Bottom controls depth. Changes are saved to this combined analysis."
          @update-directions="handleDirectionsUpdate"
        />
        <p v-if="!store.currentMultiViewDirections.isValid" class="warning-text">
          This session has an invalid direction pair. Pick one front and one bottom direction, then save.
        </p>
        <div class="direction-actions">
          <Button
            size="sm"
            variant="outline"
            :disabled="!hasDirectionChanges || store.isUpdatingDirections"
            @click="saveDirections"
          >
            {{ store.isUpdatingDirections ? 'Saving...' : 'Save Directions' }}
          </Button>
        </div>
      </div>
      <MultiViewAlignmentPanel v-if="store.currentMultiViewSession && hasLoadedSources" />
      <p v-else-if="!store.currentMultiViewSession" class="placeholder-copy">
        Select a valid combined analysis to configure alignment.
      </p>
      <p v-else class="placeholder-copy">
        Alignment controls are unavailable until both source analyses load.
      </p>
    </section>
  </div>
</template>

<style scoped>
.combined-sidebar {
  padding: 1rem;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.sidebar-section {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.sidebar-section + .sidebar-section {
  border-top: 1px solid var(--border-light);
  padding-top: 1rem;
}

h3 {
  margin: 0;
  font-size: 0.95rem;
}

.session-summary {
  padding: 0.6rem;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
}

.session-name {
  margin: 0;
  font-weight: 600;
  font-size: 0.9rem;
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
}

.auto-aligned-badge {
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 0.65rem;
  font-weight: 600;
  line-height: 1;
  padding: 0.2rem 0.4rem;
}

.session-date {
  margin: 0.25rem 0 0;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.direction-summary {
  margin-top: 0.5rem;
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.source-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.source-item {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  padding: 0.55rem;
}

.source-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.source-label {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-secondary);
  text-transform: uppercase;
}

.direction-badge {
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 0.68rem;
  font-weight: 600;
  line-height: 1;
  padding: 0.24rem 0.45rem;
}

.source-title {
  margin: 0.2rem 0 0;
  font-size: 0.86rem;
  font-weight: 600;
}

.source-meta {
  margin: 0.15rem 0 0;
  font-size: 0.78rem;
  color: var(--text-secondary);
}

.placeholder-title {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 600;
}

.placeholder-copy,
.empty-text,
.warning-text {
  margin: 0;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.warning-text {
  color: var(--color-error-600);
}

.direction-settings {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.direction-actions {
  display: flex;
  justify-content: flex-end;
}
</style>

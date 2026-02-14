<script setup lang="ts">
import { computed } from 'vue';
import { useAnalysisStore } from '../stores/analysis';

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
</script>

<template>
  <div class="combined-sidebar">
    <section class="sidebar-section">
      <h3>Analyses</h3>

      <div v-if="store.currentMultiViewSession" class="session-summary">
        <p class="session-name">{{ store.currentMultiViewSession.name }}</p>
        <p class="session-date">Created {{ formatDate(store.currentMultiViewSession.created_at) }}</p>
      </div>
      <p v-else class="empty-text">No combined analysis selected.</p>

      <div v-if="store.currentMultiViewSession && hasLoadedSources" class="source-list">
        <div class="source-item">
          <p class="source-label">Left</p>
          <p class="source-title">{{ leftVideoName }}</p>
          <p class="source-meta">{{ leftAnalysisName }}</p>
        </div>

        <div class="source-item">
          <p class="source-label">Right</p>
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
      <p class="placeholder-title">Combined measurement tools are coming next.</p>
      <p class="placeholder-copy">
        This area is reserved for settings that operate across both source analyses.
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
}

.session-date {
  margin: 0.25rem 0 0;
  font-size: 0.8rem;
  color: var(--text-secondary);
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

.source-label {
  margin: 0;
  font-size: 0.72rem;
  color: var(--text-secondary);
  text-transform: uppercase;
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
</style>

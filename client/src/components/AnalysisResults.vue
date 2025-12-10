<script setup lang="ts">
import { computed } from 'vue';
import { useAnalysisStore } from '../stores/analysis';

const store = useAnalysisStore();

const globalData = computed(() => {
  return store.currentAnalysis?.global_data || null;
});

const hasGlobalData = computed(() => {
  return globalData.value !== null && Object.keys(globalData.value).length > 0;
});

function formatKey(key: string): string {
  return key
    .split('_')
    .map((word) => word.charAt(0).toUpperCase() + word.slice(1))
    .join(' ');
}

function formatValue(value: unknown): string {
  if (typeof value === 'number') {
    if (Number.isInteger(value)) {
      return value.toString();
    }
    return value.toFixed(2);
  }
  if (typeof value === 'object' && value !== null) {
    return JSON.stringify(value, null, 2);
  }
  return String(value);
}
</script>

<template>
  <div class="analysis-results">
    <div class="header">
      <h2>Analysis Results</h2>
    </div>
    
    <div v-if="!store.currentAnalysis" class="no-analysis">
      No analysis has been run yet.
    </div>
    
    <div v-else-if="store.isProcessing" class="processing">
      Analysis in progress... Results will appear here when complete.
    </div>
    
    <div v-else-if="store.progressStatus === 'failed'" class="failed">
      Analysis failed. Please try again.
    </div>
    
    <div v-else-if="store.progressStatus === 'cancelled'" class="cancelled">
      Analysis was cancelled.
    </div>
    
    <div v-else-if="!hasGlobalData" class="no-results">
      No results available yet.
    </div>
    
    <div v-else class="results-content">
      <h3>Global Statistics</h3>
      <div class="stats-grid">
        <div
          v-for="(value, key) in globalData"
          :key="key"
          class="stat-item"
        >
          <div class="stat-label">{{ formatKey(key) }}</div>
          <div class="stat-value">{{ formatValue(value) }}</div>
        </div>
      </div>
      
      <div v-if="store.currentAnalysis" class="frame-info">
        <h3>Frame Data</h3>
        <p>
          {{ store.currentAnalysis.processed_frames || store.liveFrameData.size || 0 }} frames analyzed.
          View overlays on the video player.
        </p>
      </div>
    </div>
  </div>
</template>

<style scoped>
.analysis-results {
  padding: 1rem;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

h2 {
  margin: 0;
}

h3 {
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  font-size: 1rem;
  font-weight: 600;
}

.no-analysis,
.processing,
.failed,
.cancelled,
.no-results {
  padding: 1.5rem;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
}

.failed {
  color: var(--color-error-600);
  background: var(--color-error-100);
  border-radius: 4px;
}

.cancelled {
  color: var(--color-warning-600);
  background: var(--color-warning-100);
  border-radius: 4px;
}

.results-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.stat-item {
  padding: 1rem;
  border: 1px solid var(--color-neutral-200);
  border-radius: 4px;
  background: var(--bg-secondary);
}

.stat-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.frame-info {
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 4px;
}

.frame-info p {
  margin: 0;
  color: var(--text-secondary);
}
</style>


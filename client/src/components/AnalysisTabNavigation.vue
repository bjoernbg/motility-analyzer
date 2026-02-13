<template>
  <div v-if="store.isInCombinedMode" class="analysis-tabs">
    <div class="tabs-container">
      <button
        class="tab-button"
        :class="{ active: store.combinedViewMode === 'analysis1' }"
        @click="selectTab('analysis1')"
      >
        {{ analysis1Name }}
      </button>
      <button
        class="tab-button"
        :class="{ active: store.combinedViewMode === 'analysis2' }"
        @click="selectTab('analysis2')"
      >
        {{ analysis2Name }}
      </button>
      <button
        class="tab-button combined-tab"
        :class="{ active: store.combinedViewMode === 'combined' }"
        @click="selectTab('combined')"
      >
        Combined
      </button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed } from 'vue';
import { useAnalysisStore } from '../stores/analysis';

const store = useAnalysisStore();

const analysis1Name = computed(() => {
  if (!store.video1?.filename) return 'Analysis 1';
  // Extract filename without extension
  const name = store.video1.filename.replace(/\.[^/.]+$/, '');
  // Truncate if too long
  return name.length > 25 ? name.substring(0, 25) + '...' : name;
});

const analysis2Name = computed(() => {
  if (!store.video2?.filename) return 'Analysis 2';
  // Extract filename without extension
  const name = store.video2.filename.replace(/\.[^/.]+$/, '');
  // Truncate if too long
  return name.length > 25 ? name.substring(0, 25) + '...' : name;
});

function selectTab(mode: 'analysis1' | 'analysis2' | 'combined') {
  store.setCombinedViewMode(mode);
}
</script>

<style scoped>
.analysis-tabs {
  margin-bottom: 1rem;
}

.tabs-container {
  display: flex;
  gap: 0.25rem;
  border-bottom: 2px solid #e5e7eb;
}

.tab-button {
  padding: 0.75rem 1.5rem;
  background: transparent;
  border: none;
  border-bottom: 2px solid transparent;
  color: #6b7280;
  font-weight: 500;
  cursor: pointer;
  transition: all 0.2s;
  margin-bottom: -2px;
  white-space: nowrap;
}

.tab-button:hover {
  color: #374151;
  background: #f9fafb;
}

.tab-button.active {
  color: #2563eb;
  border-bottom-color: #2563eb;
  font-weight: 600;
}

.tab-button.combined-tab {
  margin-left: 1rem;
  position: relative;
}

.tab-button.combined-tab::before {
  content: '';
  position: absolute;
  left: -0.75rem;
  top: 50%;
  transform: translateY(-50%);
  width: 2px;
  height: 60%;
  background: #e5e7eb;
}
</style>

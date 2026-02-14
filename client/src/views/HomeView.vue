<script setup lang="ts">
import { onUnmounted, ref } from 'vue';
import VideoSelector from '../components/VideoSelector.vue';
import AnalysisParams from '../components/AnalysisParams.vue';
import MediaViewer from '../components/MediaViewer.vue';
import MediaController from '../components/MediaController.vue';
import AnalysisResults from '../components/AnalysisResults.vue';
import MultiViewStartModal from '../components/MultiViewStartModal.vue';
import MultiViewWorkspace from '../components/MultiViewWorkspace.vue';
import { useAnalysisStore } from '../stores/analysis';

const store = useAnalysisStore();
const showMultiViewModal = ref(false);

function handleSeek(frame: number) {
  store.seekToFrame(frame);
}

onUnmounted(() => {
  // Cleanup polling when leaving the view
  store.stopPolling();
});
</script>

<template>
  <div class="home-view">
    <div class="container">
      <div class="header-row">
        <h1 class="text-2xl">Motility Analyzer</h1>
        <button class="start-combined-button" @click="showMultiViewModal = true">
          Start Combined Analysis
        </button>
      </div>
      
      <div class="layout">
        <div class="left-panel">
          <VideoSelector />
          <AnalysisParams />
        </div>
        
        <div class="right-panel">
          <MultiViewWorkspace v-if="store.isInMultiViewMode" />
          <template v-else>
            <MediaViewer />
            <MediaController @seek="handleSeek" />
            <AnalysisResults />
          </template>
        </div>
      </div>
    </div>

    <MultiViewStartModal v-model="showMultiViewModal" />
  </div>
</template>

<style scoped>
.home-view {
  min-height: 100vh;
  background: var(--bg-secondary);
  padding: 2rem;
}

.container {
  max-width: 2400px;
  margin: 0 auto;
}

h1 {
  margin-top: 0;
  margin-bottom: 0;
  color: var(--text-primary);
}

.header-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  margin-bottom: 1rem;
  gap: 1rem;
}

.start-combined-button {
  border: 1px solid var(--border-light);
  background: var(--bg-primary);
  color: var(--text-primary);
  border-radius: 6px;
  padding: 0.55rem 0.9rem;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
}

.start-combined-button:hover {
  background: var(--bg-secondary);
}

.layout {
  display: grid;
  grid-template-columns: 300px 1fr;
  gap: 1rem;
}

.left-panel,
.right-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

@media (max-width: 1200px) {
  .layout {
    grid-template-columns: 1fr;
  }
}

</style>

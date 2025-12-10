<script setup lang="ts">
import { ref, onUnmounted } from 'vue';
import VideoSelector from '../components/VideoSelector.vue';
import AnalysisParams from '../components/AnalysisParams.vue';
import MediaViewer from '../components/MediaViewer.vue';
import MediaController from '../components/MediaController.vue';
import AnalysisResults from '../components/AnalysisResults.vue';
import { useAnalysisStore } from '../stores/analysis';

const store = useAnalysisStore();
const mediaViewerRef = ref<InstanceType<typeof MediaViewer> | null>(null);

function handleSeek(frame: number) {
  if (mediaViewerRef.value && 'seekToFrame' in mediaViewerRef.value) {
    (mediaViewerRef.value as any).seekToFrame(frame);
  }
}

onUnmounted(() => {
  // Cleanup polling when leaving the view
  store.stopPolling();
});
</script>

<template>
  <div class="home-view">
    <div class="container">
      <h1 class="text-2xl">Motility Analyzer</h1>
      
      <div class="layout">
        <div class="left-panel">
          <VideoSelector />
          <AnalysisParams />
        </div>
        
        <div class="right-panel">
          <MediaViewer ref="mediaViewerRef" />
          <MediaController @seek="handleSeek" />
          <AnalysisResults />
        </div>
      </div>
    </div>
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
  margin-bottom: 1rem;
  text-align: center;
  color: var(--text-primary);
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

</style>

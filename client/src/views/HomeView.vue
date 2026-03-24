<script setup lang="ts">
import { onUnmounted, ref } from 'vue';
import WorkspaceEntitySelector from '../components/WorkspaceEntitySelector.vue';
import CombinedAnalysisSidebar from '../components/CombinedAnalysisSidebar.vue';
import AnalysisParams from '../components/AnalysisParams.vue';
import MediaViewer from '../components/MediaViewer.vue';
import MediaController from '../components/MediaController.vue';
import AnalysisResults from '../components/AnalysisResults.vue';
import MultiViewStartModal from '../components/MultiViewStartModal.vue';
import MultiViewWorkspace from '../components/MultiViewWorkspace.vue';
import { useAnalysisStore } from '../stores/analysis';
import { useWorkspaceEntityRouting } from '../composables/useWorkspaceEntityRouting';

const store = useAnalysisStore();
const showMultiViewModal = ref(false);
const selectedContractionId = ref<string | null>(null);

useWorkspaceEntityRouting();

function handleSeek(frame: number) {
  store.seekToFrame(frame);
}

function handleContractionSelection(contractionId: string | null) {
  selectedContractionId.value = contractionId;
}

onUnmounted(() => {
  store.stopPolling();
});
</script>

<template>
  <div class="home-view">
    <div class="container">
      <div class="header-row">
        <h1 class="text-2xl">Motility Analyzer</h1>
      </div>

      <div class="layout">
        <div class="left-panel">
          <WorkspaceEntitySelector @create-combined="showMultiViewModal = true" />

          <AnalysisParams v-if="store.isInVideoMode" />
          <CombinedAnalysisSidebar v-else-if="store.isInCombinedMode" />
          <div v-else class="empty-panel">
            Select a video or combined analysis to begin.
          </div>
        </div>

        <div class="right-panel">
          <template v-if="store.isInVideoMode">
            <MediaViewer :selected-contraction-id="selectedContractionId" />
            <MediaController @seek="handleSeek" />
            <AnalysisResults @select-contraction="handleContractionSelection" />
          </template>

          <MultiViewWorkspace v-else-if="store.isInCombinedMode" />

          <div v-else class="empty-workspace">
            Choose an entity from the sidebar to open a workspace.
          </div>
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

.layout {
  display: grid;
  grid-template-columns: 320px 1fr;
  gap: 1rem;
}

.left-panel,
.right-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.empty-panel,
.empty-workspace {
  border: 1px dashed var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 0.9rem;
  padding: 1rem;
}

.empty-workspace {
  min-height: 60vh;
  display: flex;
  align-items: center;
  justify-content: center;
}

@media (max-width: 1200px) {
  .layout {
    grid-template-columns: 1fr;
  }

  .empty-workspace {
    min-height: 200px;
  }
}
</style>

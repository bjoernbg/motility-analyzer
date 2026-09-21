<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import { useRoute } from 'vue-router';
import CombinedAnalysisSidebar from '../components/CombinedAnalysisSidebar.vue';
import AnalysisParams from '../components/AnalysisParams.vue';
import MediaViewer from '../components/MediaViewer.vue';
import MediaController from '../components/MediaController.vue';
import AnalysisResults from '../components/AnalysisResults.vue';
import MultiViewStartModal from '../components/MultiViewStartModal.vue';
import MultiViewWorkspace from '../components/MultiViewWorkspace.vue';
import ProjectSelectorDrawer from '../components/ProjectSelectorDrawer.vue';
import { Button } from '../components/ui/button';
import { getVideoDisplayName } from '../lib/domain/displayNames';
import { useAnalysisStore } from '../stores/analysis';
import { useWorkspaceEntityRouting } from '../composables/useWorkspaceEntityRouting';

const store = useAnalysisStore();
const route = useRoute();
const showMultiViewModal = ref(false);
const isProjectDrawerOpen = ref(false);
const selectedContractionId = ref<string | null>(null);

useWorkspaceEntityRouting();

const hasActiveEntity = computed(() => store.isInVideoMode || store.isInCombinedMode);

const activeProjectName = computed(() => {
  if (store.isInVideoMode && store.currentVideo) {
    return getVideoDisplayName(store.currentVideo);
  }

  if (store.isInCombinedMode && store.currentMultiViewSession) {
    return store.currentMultiViewSession.name;
  }

  return 'No project selected';
});

const activeProjectKindLabel = computed(() => {
  if (store.isInVideoMode) {
    return 'Video';
  }

  if (store.isInCombinedMode) {
    return 'Combined analysis';
  }

  return null;
});

const projectMetaCopy = computed(() => {
  if (store.isInVideoMode) {
    return 'Video analyses and measurement settings are shown below.';
  }

  if (store.isInCombinedMode) {
    return 'Combined alignment and session settings are shown below.';
  }

  return 'Choose a video or combined analysis to begin.';
});

function handleSeek(frame: number) {
  store.seekToFrame(frame);
}

function handleContractionSelection(contractionId: string | null) {
  selectedContractionId.value = contractionId;
}

function openProjectDrawer() {
  isProjectDrawerOpen.value = true;
}

function handleProjectSelected() {
  isProjectDrawerOpen.value = false;
}

function handleCreateCombined() {
  isProjectDrawerOpen.value = false;
  showMultiViewModal.value = true;
}

onMounted(() => {
  void Promise.all([store.loadVideos(), store.loadMultiViewSessions()]);
});

watch(
  () => [route.name, store.activeEntityType, store.activeEntityId] as const,
  ([routeName, activeEntityType, activeEntityId]) => {
    const hasEntity =
      (activeEntityType === 'video' || activeEntityType === 'combined') &&
      activeEntityId !== null;

    if (hasEntity) {
      isProjectDrawerOpen.value = false;
      return;
    }

    if (routeName === 'home') {
      isProjectDrawerOpen.value = true;
    }
  },
  { immediate: true }
);

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
          <section class="project-switcher">
            <div class="project-switcher-header">
              <p class="project-switcher-label">Project</p>
              <Button
                class="project-switcher-action"
                size="sm"
                :variant="hasActiveEntity ? 'outline' : 'default'"
                @click="openProjectDrawer"
              >
                {{ hasActiveEntity ? 'Change project' : 'Select project' }}
              </Button>
            </div>

            <p class="project-switcher-title">{{ activeProjectName }}</p>
            <span v-if="activeProjectKindLabel" class="project-kind-badge">
              {{ activeProjectKindLabel }}
            </span>
            <p class="project-switcher-meta">{{ projectMetaCopy }}</p>
          </section>

          <AnalysisParams v-if="store.isInVideoMode" />
          <CombinedAnalysisSidebar v-else-if="store.isInCombinedMode" />
          <div v-else class="empty-panel">
            No project selected. Use the project picker to choose a video or combined analysis.
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
    <ProjectSelectorDrawer
      v-model:open="isProjectDrawerOpen"
      @entity-selected="handleProjectSelected"
      @create-combined="handleCreateCombined"
    />
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

.project-switcher,
.left-panel,
.right-panel {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.project-switcher {
  padding: 0.9rem 1rem;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
  gap: 0.75rem;
}

.project-switcher-header {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 0.75rem;
}

.project-switcher-label,
.project-switcher-title {
  margin: 0;
}

.project-switcher-label {
  font-size: 0.72rem;
  font-weight: 600;
  letter-spacing: 0.04em;
  text-transform: uppercase;
  color: var(--text-secondary);
}

.project-switcher-title {
  font-size: 1rem;
  font-weight: 600;
  color: var(--text-primary);
  line-height: 1.3;
  overflow-wrap: anywhere;
}

.project-kind-badge {
  align-self: flex-start;
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 0.68rem;
  font-weight: 600;
  line-height: 1;
  padding: 0.22rem 0.45rem;
}

.project-switcher-meta {
  margin: 0;
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.project-switcher-action {
  flex-shrink: 0;
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

  .project-switcher {
    gap: 0.85rem;
  }

  .project-switcher-header {
    flex-direction: column;
    align-items: stretch;
  }

  .project-switcher-action {
    align-self: flex-start;
  }

  .empty-workspace {
    min-height: 200px;
  }
}
</style>

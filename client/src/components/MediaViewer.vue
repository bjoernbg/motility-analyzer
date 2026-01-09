<template>
  <div class="media-viewer">
    <div class="view-toggle-container">
      <div class="view-toggle">
        <button :class="{ active: viewMode === 'video' }" @click="viewMode = 'video'">
          Video
        </button>
        <button :class="{ active: viewMode === 'heatmap' }" @click="viewMode = 'heatmap'">
          Heatmap
        </button>
      </div>
      <div class="flex items-center gap-1">
        <div v-if="viewMode === 'video' && hasFrameData" class="overlay-toggle">
          <ButtonGroup>
            <Button :variant="showCanvasOverlay ? 'default' : 'outline'" @click="showCanvasOverlay = !showCanvasOverlay"
              size="sm" title="Display detected paths">
              <Icon name="lucide:chart-scatter" size="1.1em" />
            </Button>
          </ButtonGroup>
        </div>
        <div v-if="viewMode === 'heatmap' && store.contractionEvents.length > 0" class="contraction-overlay-toggle">
          <ButtonGroup>
            <Button :variant="showContractionOverlays ? 'default' : 'outline'"
              @click="showContractionOverlays = !showContractionOverlays" size="sm"
              title="Display detected contraction waves">
              <Icon name="lucide:chart-scatter" size="1.1em" />
            </Button>
          </ButtonGroup>
        </div>
        <div v-if="store.currentAnalysis" class="settings-toggle">
          <Popover>
            <PopoverTrigger as-child>
              <Button size="sm" variant="outline" title="Measurement settings">
                <Icon name="lucide:settings" size="1.1em" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" class="p-3">
              <DisplaySettingsControls :analysis-id="store.currentAnalysis.id"
                @settings-updated="handleSettingsUpdated" />
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>

    <div class="main-view-container">
      <!-- Main View -->
      <div class="main-view">
        <!-- Use v-show to keep video loaded when switching views -->
        <VideoPlayer v-show="viewMode === 'video'" v-model:show-canvas-overlay="showCanvasOverlay"
          :highlight-point-index="highlightedPointIndex"
          :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor" />
        <HeatmapViewer v-if="viewMode === 'heatmap' && store.currentAnalysis"
          :key="`main-heatmap-${store.currentAnalysis.id}`" :analysis-id="store.currentAnalysis.id"
          :current-frame="store.currentFrame" :show-contraction-overlays="showContractionOverlays"
          @frame-click="handleFrameClick" />
        <div v-else-if="viewMode === 'heatmap' && !store.currentAnalysis" class="no-heatmap">
          No analysis available. Run an analysis to view the heatmap.
        </div>
      </div>

      <!-- Overlay in upper-right corner (20% width) -->
      <div v-if="showOverlay" class="overlay-container">
        <div class="overlay-content">
          <!-- Mini Heatmap when viewing video -->
          <HeatmapViewer v-if="viewMode === 'video' && store.currentAnalysis"
            :key="`overlay-heatmap-${store.currentAnalysis.id}`" :analysis-id="store.currentAnalysis.id"
            :current-frame="store.currentFrame" compact @frame-click="handleFrameClick" />
          <!-- Mini Video when viewing heatmap -->
          <div v-else-if="viewMode === 'heatmap' && store.currentVideo" class="mini-video-wrapper">
            <VideoPlayer overlay :highlight-point-index="highlightedPointIndex"
              :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor" />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import VideoPlayer from './VideoPlayer.vue';
import HeatmapViewer from './HeatmapViewer.vue';
import DisplaySettingsControls from './DisplaySettingsControls.vue';
import { ButtonGroup } from './ui/button-group';
import { Button } from './ui/button';
import { Icon } from './ui/icon';
import { Popover, PopoverTrigger, PopoverContent } from './ui/popover';
import { getDisplaySettings, type DisplaySettings } from '../lib/api';

const store = useAnalysisStore();

const viewMode = ref<'video' | 'heatmap'>('video');
const highlightedPointIndex = ref<number | null>(null);
const showContractionOverlays = ref(false);
const showCanvasOverlay = ref(true);
const currentDisplaySettings = ref<DisplaySettings | null>(null);

const hasFrameData = computed(() => store.liveFrameData.size > 0);

const showOverlay = computed(() => {
  if (viewMode.value === 'video') {
    return store.currentAnalysis !== null;
  } else {
    return store.currentVideo !== null;
  }
});

async function handleFrameClick(frame: number, pointIndex: number) {
  // Store the highlighted point index for visualization
  highlightedPointIndex.value = pointIndex;

  // Seek to frame using centralized store action (which loads frame data automatically)
  store.seekToFrame(frame);
}

// Load display settings when analysis changes
watch(() => store.currentAnalysis?.id, async (id) => {
  if (id) {
    try {
      currentDisplaySettings.value = await getDisplaySettings(id);
    } catch (err) {
      console.error('Failed to load display settings:', err);
      // Fallback to defaults on error
      currentDisplaySettings.value = null;
    }
  } else {
    currentDisplaySettings.value = null;
  }
}, { immediate: true });

function handleSettingsUpdated(settings: DisplaySettings) {
  currentDisplaySettings.value = settings;
}
</script>

<style scoped>
.media-viewer {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.view-toggle-container {
  display: flex;
  justify-content: space-between;
  align-items: center;
  padding: 0.5rem;
}

.view-toggle {
  display: flex;
  gap: 0.5rem;
}

.view-toggle button {
  padding: 0.5rem 1rem;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  font-size: 0.875rem;
  transition: all 0.2s;
}

.view-toggle button:hover {
  background: var(--bg-tertiary);
}

.view-toggle button.active {
  background: var(--color-primary-600);
  color: white;
  border-color: var(--color-primary-600);
}

.contraction-overlay-toggle,
.overlay-toggle,
.settings-toggle {
  display: flex;
  align-items: center;
}

.main-view-container {
  position: relative;
  width: 100%;
}

.main-view {
  width: 100%;
}

.overlay-container {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  width: 25%;
  min-width: 200px;
  max-width: 400px;
  z-index: 10;
  pointer-events: none;
}

.overlay-content {
  background: var(--bg-primary);
  border-radius: 2px;
  box-shadow: 0 2px 8px rgba(0, 0, 0, 0.15);
  overflow: hidden;
  pointer-events: auto;
  aspect-ratio: 16 / 9;
  max-height: 30vh;
  display: flex;
  flex-direction: column;
}

.overlay-content :deep(.heatmap-container) {
  height: 100%;
  min-height: 200px;
  max-height: 30vh;
}

.mini-video-wrapper {
  width: 100%;
  aspect-ratio: 16 / 9;
  position: relative;
}

.no-heatmap {
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
  border: 1px solid var(--border-light);
  border-radius: 3px;
  background: var(--bg-primary);
}
</style>

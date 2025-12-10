<template>
  <div class="media-viewer">
    <div class="view-toggle-container">
      <div class="view-toggle">
        <button
          :class="{ active: viewMode === 'video' }"
          @click="viewMode = 'video'"
        >
          Video
        </button>
        <button
          :class="{ active: viewMode === 'heatmap' }"
          @click="viewMode = 'heatmap'"
        >
          Heatmap
        </button>
      </div>
    </div>

    <div class="main-view-container">
      <!-- Main View -->
      <div class="main-view">
        <!-- Use v-show to keep video loaded when switching views -->
        <VideoPlayer
          v-show="viewMode === 'video'"
          ref="videoPlayerRef"
        />
        <HeatmapViewer
          v-if="viewMode === 'heatmap' && store.currentAnalysis"
          :key="`main-heatmap-${store.currentAnalysis.id}`"
          :analysis-id="store.currentAnalysis.id"
          :current-frame="store.currentFrame"
          @frame-click="handleFrameClick"
        />
        <div v-else-if="viewMode === 'heatmap' && !store.currentAnalysis" class="no-heatmap">
          No analysis available. Run an analysis to view the heatmap.
        </div>
      </div>

      <!-- Overlay in upper-right corner (20% width) -->
      <div v-if="showOverlay" class="overlay-container">
        <div class="overlay-content">
          <!-- Mini Heatmap when viewing video -->
          <HeatmapViewer
            v-if="viewMode === 'video' && store.currentAnalysis"
            :key="`overlay-heatmap-${store.currentAnalysis.id}`"
            :analysis-id="store.currentAnalysis.id"
            :current-frame="store.currentFrame"
            compact
            @frame-click="handleFrameClick"
          />
          <!-- Mini Video when viewing heatmap -->
          <div v-else-if="viewMode === 'heatmap' && store.currentVideo" class="mini-video-wrapper">
            <VideoPlayer
              ref="miniVideoPlayerRef"
              overlay
              :highlight-frame="highlightedPoint?.frame ?? null"
              :highlight-point-index="highlightedPoint?.pointIndex ?? null"
            />
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import VideoPlayer from './VideoPlayer.vue';
import HeatmapViewer from './HeatmapViewer.vue';

const store = useAnalysisStore();

const viewMode = ref<'video' | 'heatmap'>('video');
const videoPlayerRef = ref<InstanceType<typeof VideoPlayer> | null>(null);
const miniVideoPlayerRef = ref<InstanceType<typeof VideoPlayer> | null>(null);
const highlightedPoint = ref<{ frame: number; pointIndex: number } | null>(null);

const showOverlay = computed(() => {
  if (viewMode.value === 'video') {
    return store.currentAnalysis !== null;
  } else {
    return store.currentVideo !== null;
  }
});

function handleFrameClick(frame: number, pointIndex: number) {
  // Store the highlighted point for the mini video overlay
  highlightedPoint.value = { frame, pointIndex };
  
  // Seek the main video player to the clicked frame (when in video mode)
  if (viewMode.value === 'video' && videoPlayerRef.value && 'seekToFrame' in videoPlayerRef.value) {
    (videoPlayerRef.value as any).seekToFrame(frame);
  }
  // Seek the mini video when in heatmap mode (overlay video)
  if (viewMode.value === 'heatmap' && miniVideoPlayerRef.value && 'seekToFrame' in miniVideoPlayerRef.value) {
    (miniVideoPlayerRef.value as any).seekToFrame(frame);
  }
}

// Expose seekToFrame method for external control (e.g., from MediaController)
function seekToFrame(frame: number) {
  // Seek the main video player if in video mode
  if (viewMode.value === 'video' && videoPlayerRef.value && 'seekToFrame' in videoPlayerRef.value) {
    (videoPlayerRef.value as any).seekToFrame(frame);
  }
  // Also seek mini video if in heatmap mode
  if (viewMode.value === 'heatmap' && miniVideoPlayerRef.value && 'seekToFrame' in miniVideoPlayerRef.value) {
    (miniVideoPlayerRef.value as any).seekToFrame(frame);
  }
}

defineExpose({
  seekToFrame,
});
</script>

<style scoped>
.media-viewer {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.view-toggle-container {
  display: flex;
  justify-content: flex-end;
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


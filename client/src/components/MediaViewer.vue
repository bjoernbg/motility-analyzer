<template>
  <div class="media-viewer">
    <!-- Tab navigation (only in combined mode) -->
    <AnalysisTabNavigation />

    <div class="view-toggle-container">
      <div class="view-toggle">
        <button :class="{ active: viewMode === 'video' }" @click="viewMode = 'video'">
          Video
        </button>
        <button :class="{ active: viewMode === 'heatmap' }" @click="viewMode = 'heatmap'">
          Heatmap
        </button>
        <button
          v-if="store.isInCombinedMode && store.combinedViewMode === 'combined'"
          :class="{ active: viewMode === 'heatmap_diff' }"
          @click="viewMode = 'heatmap_diff'"
        >
          Heatmap Diff
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
        <div v-if="canShowOverlay" class="preview-position-toggle">
          <ButtonGroup>
            <Button :variant="overlayPosition === 'left' ? 'default' : 'outline'"
              @click="overlayPosition = 'left'" size="sm" title="Preview on left">
              <Icon name="lucide:panel-left" size="1.1em" />
            </Button>
            <Button :variant="overlayPosition === 'right' ? 'default' : 'outline'"
              @click="overlayPosition = 'right'" size="sm" title="Preview on right">
              <Icon name="lucide:panel-right" size="1.1em" />
            </Button>
            <Button :variant="overlayPosition === 'off' ? 'default' : 'outline'"
              @click="overlayPosition = 'off'" size="sm" title="Hide preview">
              <Icon name="lucide:eye-off" size="1.1em" />
            </Button>
          </ButtonGroup>
        </div>
        <div v-if="store.activeAnalysis && store.activeVideo" class="settings-toggle">
          <Popover>
            <PopoverTrigger as-child>
              <Button size="sm" variant="outline" title="Measurement settings">
                <Icon name="lucide:settings" size="1.1em" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" class="p-3">
              <DisplaySettingsControls :analysis-id="store.activeAnalysis.id"
                :video-id="store.activeVideo.id"
                @settings-updated="handleSettingsUpdated"
                @calibration-result="handleCalibrationResult" />
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>

    <div class="main-view-container">
      <!-- Main View -->
      <div class="main-view">
        <!-- Single view mode (or individual tab in combined mode) -->
        <template v-if="!store.isInCombinedMode || store.combinedViewMode !== 'combined'">
          <!-- Use v-show to keep video loaded when switching views -->
          <VideoPlayer v-show="viewMode === 'video'" v-model:show-canvas-overlay="showCanvasOverlay"
            :highlight-point-index="highlightedPointIndex"
            :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor"
            :calibration-region="calibrationRegion" />
          <HeatmapViewer v-if="viewMode === 'heatmap' && store.activeAnalysis"
            :key="`main-heatmap-${store.activeAnalysis.id}`" :analysis-id="store.activeAnalysis.id"
            :current-frame="store.currentFrame" :show-contraction-overlays="showContractionOverlays"
            @frame-click="handleFrameClick" />
          <div v-else-if="viewMode === 'heatmap' && !store.activeAnalysis" class="no-heatmap">
            No analysis available. Run an analysis to view the heatmap.
          </div>
        </template>

        <!-- Combined stacked view -->
        <template v-else>
          <!-- Video mode: two videos stacked -->
          <div v-if="viewMode === 'video'" class="stacked-view">
            <div class="stacked-item">
              <div class="stacked-label">{{ video1Name }}</div>
              <VideoPlayer
                :analysis-id="store.analysis1?.id"
                v-model:show-canvas-overlay="showCanvasOverlay"
                :highlight-point-index="highlightedPointIndex"
                :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor"
                :calibration-region="calibrationRegion"
              />
            </div>
            <div class="stacked-item">
              <div class="stacked-label">{{ video2Name }}</div>
              <VideoPlayer
                :analysis-id="store.analysis2?.id"
                v-model:show-canvas-overlay="showCanvasOverlay"
                :highlight-point-index="highlightedPointIndex"
                :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor"
                :calibration-region="calibrationRegion"
              />
            </div>
          </div>

          <!-- Heatmap mode: two heatmaps stacked -->
          <div v-else-if="viewMode === 'heatmap'" class="stacked-view">
            <div class="stacked-item">
              <div class="stacked-label">{{ video1Name }}</div>
              <HeatmapViewer
                v-if="store.analysis1"
                :key="`heatmap-1-${store.analysis1.id}`"
                :analysis-id="store.analysis1.id"
                :current-frame="store.currentFrame"
                :show-contraction-overlays="showContractionOverlays"
                @frame-click="handleFrameClick"
              />
            </div>
            <div class="stacked-item">
              <div class="stacked-label">{{ video2Name }}</div>
              <HeatmapViewer
                v-if="store.analysis2"
                :key="`heatmap-2-${store.analysis2.id}`"
                :analysis-id="store.analysis2.id"
                :current-frame="store.currentFrame"
                :show-contraction-overlays="showContractionOverlays"
                @frame-click="handleFrameClick"
              />
            </div>
          </div>

          <!-- Heatmap diff mode: single diff heatmap -->
          <div v-else-if="viewMode === 'heatmap_diff'" class="diff-view">
            <HeatmapDiffViewer
              v-if="store.currentCombinedAnalysis"
              :combined-analysis-id="store.currentCombinedAnalysis.id"
              :current-frame="store.currentFrame"
              @frame-click="handleFrameClick"
            />
          </div>
        </template>
      </div>

      <!-- Overlay in upper-right corner (20% width) -->
      <div v-if="showOverlay" :class="['overlay-container', `overlay-${overlayPosition}`]">
        <div class="overlay-content">
          <!-- Mini Heatmap when viewing video -->
          <HeatmapViewer v-if="viewMode === 'video' && store.activeAnalysis"
            :key="`overlay-heatmap-${store.activeAnalysis.id}`" :analysis-id="store.activeAnalysis.id"
            :current-frame="store.currentFrame" compact @frame-click="handleFrameClick" />
          <!-- Mini Video when viewing heatmap -->
          <div v-else-if="viewMode === 'heatmap' && store.activeVideo" class="mini-video-wrapper">
            <VideoPlayer overlay :highlight-point-index="highlightedPointIndex"
              :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor"
              :calibration-region="calibrationRegion" />
          </div>
        </div>
      </div>

      <!-- Color scale sidebar -->
      <div v-if="showColorScale" class="color-scale-sidebar">
        <div class="color-scale-canvas-wrapper">
          <canvas ref="colorScaleCanvas" class="color-scale-canvas"></canvas>
        </div>
        <div class="color-scale-labels">
          <div
            v-for="label in colorScaleLabels"
            :key="label.value"
            class="color-scale-label"
            :style="{ bottom: label.percent + '%' }"
          >
            {{ label.value }}
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, onMounted, nextTick } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import VideoPlayer from './VideoPlayer.vue';
import HeatmapViewer from './HeatmapViewer.vue';
import HeatmapDiffViewer from './HeatmapDiffViewer.vue';
import AnalysisTabNavigation from './AnalysisTabNavigation.vue';
import DisplaySettingsControls from './DisplaySettingsControls.vue';
import { ButtonGroup } from './ui/button-group';
import { Button } from './ui/button';
import { Icon } from './ui/icon';
import { Popover, PopoverTrigger, PopoverContent } from './ui/popover';
import { getVideoDisplaySettings, type DisplaySettings, type CalibrationResult } from '../lib/api';
import { createColormap } from '../lib/colormap';

const store = useAnalysisStore();

const viewMode = ref<'video' | 'heatmap' | 'heatmap_diff'>('video');

const video1Name = computed(() => {
  if (!store.video1?.filename) return 'Analysis 1';
  return store.video1.filename.replace(/\.[^/.]+$/, '');
});

const video2Name = computed(() => {
  if (!store.video2?.filename) return 'Analysis 2';
  return store.video2.filename.replace(/\.[^/.]+$/, '');
});
const highlightedPointIndex = ref<number | null>(null);
const showContractionOverlays = ref(false);
const showCanvasOverlay = ref(true);
const overlayPosition = ref<'left' | 'right' | 'off'>('right');
const currentDisplaySettings = ref<DisplaySettings | null>(null);
const calibrationRegion = ref<CalibrationResult | null>(null);

const hasFrameData = computed(() => store.liveFrameData.size > 0);
const colorScaleCanvas = ref<HTMLCanvasElement | null>(null);
const colormapData = createColormap();

const canShowOverlay = computed(() => {
  if (store.isInCombinedMode && store.combinedViewMode === 'combined') return false;
  if (viewMode.value === 'heatmap_diff') return false;
  return viewMode.value === 'video' ? store.activeAnalysis !== null : store.activeVideo !== null;
});

const showOverlay = computed(() => {
  if (overlayPosition.value === 'off') return false;
  return canShowOverlay.value;
});

const showColorScale = computed(() => {
  if (!currentDisplaySettings.value) return false;
  return viewMode.value === 'heatmap' || viewMode.value === 'heatmap_diff';
});

const colorScaleLabels = computed(() => {
  if (!currentDisplaySettings.value) return [];
  const min = currentDisplaySettings.value.heatmap_min_mm;
  const max = currentDisplaySettings.value.heatmap_max_mm;
  const range = max - min;
  if (range <= 0) return [];

  const labels: { value: string; percent: number }[] = [];
  const startMm = Math.ceil(min);
  const endMm = Math.floor(max);
  for (let mm = startMm; mm <= endMm; mm++) {
    const percent = ((mm - min) / range) * 100;
    labels.push({ value: `${mm}`, percent });
  }
  return labels;
});

function renderColorScale() {
  const cvs = colorScaleCanvas.value;
  if (!cvs || !currentDisplaySettings.value) return;
  const ctx = cvs.getContext('2d');
  if (!ctx) return;

  const dpr = window.devicePixelRatio || 1;
  const cssWidth = 20;
  const cssHeight = cvs.parentElement?.clientHeight ?? 200;
  cvs.style.width = `${cssWidth}px`;
  cvs.style.height = `${cssHeight}px`;
  cvs.width = cssWidth * dpr;
  cvs.height = cssHeight * dpr;
  ctx.scale(dpr, dpr);

  // Draw gradient: bottom = red (index 0), top = violet (index 255)
  for (let y = 0; y < cssHeight; y++) {
    const t = 1 - y / cssHeight; // 0 at top → 1 at bottom, invert for red at bottom
    const ci = Math.floor(t * 255);
    // Invert: bottom of canvas = index 0 (red), top = index 255 (violet)
    // y=0 is top of canvas. We want top=violet(255), bottom=red(0)
    // So for y=0 → ci=255, y=cssHeight → ci=0
    const idx = 255 - ci;
    const r = colormapData[idx * 3 + 0] ?? 0;
    const g = colormapData[idx * 3 + 1] ?? 0;
    const b = colormapData[idx * 3 + 2] ?? 0;
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(0, y, cssWidth, 1);
  }
}

async function handleFrameClick(frame: number, pointIndex: number) {
  // Store the highlighted point index for visualization
  highlightedPointIndex.value = pointIndex;

  // Seek to frame using centralized store action (which loads frame data automatically)
  store.seekToFrame(frame);
}

// Load display settings when video changes
watch(() => store.activeVideo?.id, async (videoId) => {
  if (videoId) {
    try {
      currentDisplaySettings.value = await getVideoDisplaySettings(videoId);
    } catch (err) {
      console.error('Failed to load display settings:', err);
      currentDisplaySettings.value = null;
    }
  } else {
    currentDisplaySettings.value = null;
  }
}, { immediate: true });

// Re-render color scale when settings change or sidebar becomes visible
watch([currentDisplaySettings, showColorScale], async () => {
  if (showColorScale.value && currentDisplaySettings.value) {
    await nextTick();
    renderColorScale();
  }
}, { deep: true });

function handleSettingsUpdated(settings: DisplaySettings) {
  currentDisplaySettings.value = settings;
}

function handleCalibrationResult(result: CalibrationResult | null) {
  calibrationRegion.value = result;
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
.preview-position-toggle,
.settings-toggle {
  display: flex;
  align-items: center;
}

.main-view-container {
  position: relative;
  width: 100%;
  display: flex;
  flex-direction: row;
}

.main-view {
  flex: 1;
  min-width: 0;
}

.overlay-container {
  position: absolute;
  top: 0.5rem;
  width: 25%;
  min-width: 200px;
  max-width: 400px;
  z-index: 10;
  pointer-events: none;
}

.overlay-container.overlay-right {
  right: 0.5rem;
}

.overlay-container.overlay-left {
  left: 0.5rem;
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

/* Stacked views for combined mode */
.stacked-view {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.stacked-item {
  position: relative;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  overflow: hidden;
}

.stacked-label {
  position: absolute;
  top: 0.5rem;
  left: 0.5rem;
  background: rgba(0, 0, 0, 0.7);
  color: white;
  padding: 0.25rem 0.75rem;
  border-radius: 3px;
  font-size: 0.875rem;
  font-weight: 500;
  z-index: 10;
  pointer-events: none;
}

.diff-view {
  width: 100%;
}

.color-scale-sidebar {
  flex-shrink: 0;
  display: flex;
  flex-direction: row;
  width: 50px;
  padding: 4px 4px 4px 8px;
  align-self: stretch;
}

.color-scale-canvas-wrapper {
  width: 20px;
  flex-shrink: 0;
  position: relative;
}

.color-scale-canvas {
  width: 20px;
  height: 100%;
  border-radius: 2px;
  border: 1px solid var(--border-light);
}

.color-scale-labels {
  position: relative;
  flex: 1;
  min-width: 0;
}

.color-scale-label {
  position: absolute;
  left: 4px;
  transform: translateY(50%);
  font-size: 10px;
  color: var(--text-secondary);
  white-space: nowrap;
  line-height: 1;
}
</style>

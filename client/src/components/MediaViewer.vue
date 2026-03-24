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
              <DisplaySettingsControls :video-id="store.activeVideo.id"
                @settings-updated="handleSettingsUpdated"
                @calibration-result="handleCalibrationResult" />
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>

    <div class="main-view-container">
      <div class="main-view">
        <VideoPlayer v-show="viewMode === 'video'" v-model:show-canvas-overlay="showCanvasOverlay"
          :highlight-point-index="highlightedPointIndex"
          :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor"
          :calibration-region="calibrationRegion" />

        <HeatmapViewer v-if="viewMode === 'heatmap' && store.activeAnalysis"
          :key="`main-heatmap-${store.activeAnalysis.id}`" :analysis-id="store.activeAnalysis.id"
          :current-frame="store.currentFrame"
          :show-contraction-overlays="showContractionOverlays"
          :selected-contraction-id="props.selectedContractionId"
          @frame-click="handleFrameClick" />

        <div v-else-if="viewMode === 'heatmap' && !store.activeAnalysis" class="no-heatmap">
          No analysis available. Run an analysis to view the heatmap.
        </div>
      </div>

      <div v-if="showOverlay" :class="['overlay-container', `overlay-${overlayPosition}`]">
        <div class="overlay-content">
          <HeatmapViewer v-if="viewMode === 'video' && store.activeAnalysis"
            :key="`overlay-heatmap-${store.activeAnalysis.id}`" :analysis-id="store.activeAnalysis.id"
            :current-frame="store.currentFrame"
            :show-contraction-overlays="showContractionOverlays"
            :selected-contraction-id="props.selectedContractionId"
            compact
            @frame-click="handleFrameClick" />
          <div v-else-if="viewMode === 'heatmap' && store.activeVideo" class="mini-video-wrapper">
            <VideoPlayer overlay :highlight-point-index="highlightedPointIndex"
              :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor"
              :calibration-region="calibrationRegion" />
          </div>
        </div>
      </div>

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
import { ref, computed, watch, nextTick } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import VideoPlayer from './VideoPlayer.vue';
import HeatmapViewer from './HeatmapViewer.vue';
import DisplaySettingsControls from './DisplaySettingsControls.vue';
import { ButtonGroup } from './ui/button-group';
import { Button } from './ui/button';
import { Icon } from './ui/icon';
import { Popover, PopoverTrigger, PopoverContent } from './ui/popover';
import { getVideoDisplaySettings, type DisplaySettings, type CalibrationResult } from '../lib/api';
import { createColormap } from '../lib/colormap';

const props = defineProps<{
  selectedContractionId?: string | null;
}>();

const store = useAnalysisStore();

const viewMode = ref<'video' | 'heatmap'>('video');
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
  return viewMode.value === 'video' ? store.activeAnalysis !== null : store.activeVideo !== null;
});

const showOverlay = computed(() => {
  if (overlayPosition.value === 'off') return false;
  return canShowOverlay.value;
});

const showColorScale = computed(() => {
  if (!currentDisplaySettings.value) return false;
  return viewMode.value === 'heatmap';
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

  for (let y = 0; y < cssHeight; y++) {
    const t = 1 - y / cssHeight;
    const ci = Math.floor(t * 255);
    const idx = 255 - ci;
    const r = colormapData[idx * 3 + 0] ?? 0;
    const g = colormapData[idx * 3 + 1] ?? 0;
    const b = colormapData[idx * 3 + 2] ?? 0;
    ctx.fillStyle = `rgb(${r},${g},${b})`;
    ctx.fillRect(0, y, cssWidth, 1);
  }
}

async function handleFrameClick(frame: number, pointIndex: number) {
  highlightedPointIndex.value = pointIndex;
  store.seekToFrame(frame);
}

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

watch([currentDisplaySettings, showColorScale], async () => {
  if (showColorScale.value && currentDisplaySettings.value) {
    await nextTick();
    renderColorScale();
  }
}, { deep: true });

watch(
  () => props.selectedContractionId,
  (contractionId) => {
    if (contractionId) {
      showContractionOverlays.value = true;
    }
  }
);

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

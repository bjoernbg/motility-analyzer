<template>
  <div class="media-viewer">
    <div class="view-toggle-container">
      <div class="view-toggle">
        <button :class="{ active: viewMode === 'video' }" @click="viewMode = 'video'">Video</button>
        <button :class="{ active: viewMode === 'heatmap' }" @click="viewMode = 'heatmap'">
          Heatmap
        </button>
        <button :class="{ active: viewMode === 'topography' }" @click="viewMode = 'topography'">
          Topo 3D
        </button>
      </div>
      <div class="flex items-center gap-1">
        <div v-if="viewMode === 'video' && hasFrameData" class="overlay-toggle">
          <ButtonGroup>
            <Button
              :variant="showCanvasOverlay ? 'default' : 'outline'"
              @click="showCanvasOverlay = !showCanvasOverlay"
              size="sm"
              title="Display detected paths"
            >
              <Icon name="lucide:chart-scatter" size="1.1em" />
            </Button>
          </ButtonGroup>
        </div>
        <div
          v-if="viewMode === 'heatmap' && store.contractionEvents.length > 0"
          class="contraction-overlay-toggle"
        >
          <ButtonGroup>
            <Button
              :variant="showContractionOverlays ? 'default' : 'outline'"
              @click="showContractionOverlays = !showContractionOverlays"
              size="sm"
              title="Display detected contraction waves"
            >
              <Icon name="lucide:chart-scatter" size="1.1em" />
            </Button>
          </ButtonGroup>
        </div>
        <div v-if="viewMode === 'topography' && topographyClipRange" class="topography-clip-toggle">
          <ButtonGroup>
            <Button
              :variant="topographyClipEnabled ? 'default' : 'outline'"
              @click="toggleTopographyClipping"
              size="sm"
              title="Toggle horizontal clipping plane"
            >
              <Icon name="lucide:minus" size="1.1em" />
            </Button>
          </ButtonGroup>
        </div>
        <div v-if="canShowOverlay" class="preview-position-toggle">
          <ButtonGroup>
            <Button
              :variant="overlayPosition === 'left' ? 'default' : 'outline'"
              @click="overlayPosition = 'left'"
              size="sm"
              title="Preview on left"
            >
              <Icon name="lucide:panel-left" size="1.1em" />
            </Button>
            <Button
              :variant="overlayPosition === 'right' ? 'default' : 'outline'"
              @click="overlayPosition = 'right'"
              size="sm"
              title="Preview on right"
            >
              <Icon name="lucide:panel-right" size="1.1em" />
            </Button>
            <Button
              :variant="overlayPosition === 'off' ? 'default' : 'outline'"
              @click="overlayPosition = 'off'"
              size="sm"
              title="Hide preview"
            >
              <Icon name="lucide:eye-off" size="1.1em" />
            </Button>
          </ButtonGroup>
        </div>
        <div class="download-toggle">
          <Button
            size="sm"
            variant="outline"
            :disabled="isExportingCurrentView || !canDownloadCurrentView"
            :title="downloadButtonTitle"
            @click="handleDownloadCurrentView"
          >
            <Icon name="lucide:download" size="1.1em" />
          </Button>
        </div>
        <div v-if="store.activeAnalysis && store.activeVideo" class="settings-toggle">
          <Popover>
            <PopoverTrigger as-child>
              <Button size="sm" variant="outline" title="Measurement settings">
                <Icon name="lucide:settings" size="1.1em" />
              </Button>
            </PopoverTrigger>
            <PopoverContent align="end" class="p-3">
              <DisplaySettingsControls
                :video-id="store.activeVideo.id"
                @settings-updated="handleSettingsUpdated"
                @calibration-result="handleCalibrationResult"
              />
            </PopoverContent>
          </Popover>
        </div>
      </div>
    </div>

    <div class="main-view-container">
      <div class="main-view">
        <VideoPlayer
          ref="videoPlayerRef"
          v-show="viewMode === 'video'"
          v-model:show-canvas-overlay="showCanvasOverlay"
          :highlight-point-index="highlightedPointIndex"
          :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor"
          :calibration-region="calibrationRegion"
        />

        <HeatmapViewer
          v-if="viewMode === 'heatmap' && store.activeAnalysis"
          ref="mainHeatmapViewerRef"
          :key="`main-heatmap-${store.activeAnalysis.id}`"
          :analysis-id="store.activeAnalysis.id"
          :current-frame="store.currentFrame"
          :pixel-to-mm-factor-override="currentDisplaySettings?.pixel_to_mm_factor"
          :heatmap-min-mm-override="currentDisplaySettings?.heatmap_min_mm"
          :heatmap-max-mm-override="currentDisplaySettings?.heatmap_max_mm"
          :show-contraction-overlays="showContractionOverlays"
          :selected-contraction-id="props.selectedContractionId"
          @export-availability-change="handleHeatmapExportAvailabilityChange"
          @frame-click="handleFrameClick"
        />

        <HeatmapTopographyViewer
          v-else-if="viewMode === 'topography' && store.activeAnalysis"
          ref="mainTopographyViewerRef"
          :key="`main-topography-${store.activeAnalysis.id}`"
          :analysis-id="store.activeAnalysis.id"
          :current-frame="store.currentFrame"
          :pixel-to-mm-factor-override="currentDisplaySettings?.pixel_to_mm_factor"
          :heatmap-min-mm-override="currentDisplaySettings?.heatmap_min_mm"
          :heatmap-max-mm-override="currentDisplaySettings?.heatmap_max_mm"
          :clipping-enabled="topographyClipEnabled"
          :clip-plane-mm="topographyClipMm"
          @export-availability-change="handleTopographyExportAvailabilityChange"
          @frame-click="handleFrameClick"
        />

        <div v-else-if="viewMode === 'heatmap' && !store.activeAnalysis" class="no-heatmap">
          No analysis available. Run an analysis to view the heatmap.
        </div>
        <div v-else-if="viewMode === 'topography' && !store.activeAnalysis" class="no-heatmap">
          No analysis available. Run an analysis to view the topography.
        </div>
      </div>

      <div v-if="showOverlay" :class="['overlay-container', `overlay-${overlayPosition}`]">
        <div class="overlay-content">
          <HeatmapViewer
            v-if="viewMode === 'video' && store.activeAnalysis"
            :key="`overlay-heatmap-${store.activeAnalysis.id}`"
            :analysis-id="store.activeAnalysis.id"
            :current-frame="store.currentFrame"
            :pixel-to-mm-factor-override="currentDisplaySettings?.pixel_to_mm_factor"
            :heatmap-min-mm-override="currentDisplaySettings?.heatmap_min_mm"
            :heatmap-max-mm-override="currentDisplaySettings?.heatmap_max_mm"
            :show-contraction-overlays="showContractionOverlays"
            :selected-contraction-id="props.selectedContractionId"
            compact
            @frame-click="handleFrameClick"
          />
          <div
            v-else-if="(viewMode === 'heatmap' || viewMode === 'topography') && store.activeVideo"
            class="mini-video-wrapper"
          >
            <VideoPlayer
              overlay
              :highlight-point-index="highlightedPointIndex"
              :pixel-to-mm-factor="currentDisplaySettings?.pixel_to_mm_factor"
              :calibration-region="calibrationRegion"
            />
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
        <div
          v-if="showTopographyClipSlider && topographyClipRange"
          class="color-scale-clip-control"
        >
          <div class="color-scale-clip-value">
            {{ formatClipPlaneValue(resolvedTopographyClipMm) }}
          </div>
          <Slider
            v-model="topographyClipSliderModel"
            orientation="vertical"
            :min="topographyClipRange.min"
            :max="topographyClipRange.max"
            :step="0.1"
            class="topography-clip-slider"
          />
        </div>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, watch, nextTick } from 'vue'
import { useAnalysisStore } from '../stores/analysis'
import VideoPlayer from './VideoPlayer.vue'
import HeatmapViewer from './HeatmapViewer.vue'
import HeatmapTopographyViewer from './HeatmapTopographyViewer.vue'
import DisplaySettingsControls from './DisplaySettingsControls.vue'
import { Slider } from './ui/slider'
import { ButtonGroup } from './ui/button-group'
import { Button } from './ui/button'
import { Icon } from './ui/icon'
import { Popover, PopoverTrigger, PopoverContent } from './ui/popover'
import { getVideoDisplaySettings, type DisplaySettings, type CalibrationResult } from '../lib/api'
import { createColormap } from '../lib/colormap'
import { buildColorScaleLabels, resolveColorScaleColorIndex } from '../lib/colorScale'

const props = defineProps<{
  selectedContractionId?: string | null
}>()

interface VideoPlayerExportHandle {
  downloadCurrentFrame: () => Promise<void>
}

interface HeatmapViewerExportHandle {
  downloadCurrentView: () => Promise<void>
}

interface TopographyViewerExportHandle {
  downloadCurrentView: () => Promise<void>
}

interface MeasurementRange {
  min: number
  max: number
}

const store = useAnalysisStore()

const viewMode = ref<'video' | 'heatmap' | 'topography'>('video')
const highlightedPointIndex = ref<number | null>(null)
const showContractionOverlays = ref(false)
const showCanvasOverlay = ref(true)
const overlayPosition = ref<'left' | 'right' | 'off'>('right')
const currentDisplaySettings = ref<DisplaySettings | null>(null)
const calibrationRegion = ref<CalibrationResult | null>(null)
const videoPlayerRef = ref<VideoPlayerExportHandle | null>(null)
const mainHeatmapViewerRef = ref<HeatmapViewerExportHandle | null>(null)
const mainTopographyViewerRef = ref<TopographyViewerExportHandle | null>(null)
const isExportingCurrentView = ref(false)
const isHeatmapExportable = ref(false)
const isTopographyExportable = ref(false)
const topographyClipEnabled = ref(false)
const topographyClipMm = ref<number | null>(null)

const hasFrameData = computed(() => store.liveFrameData.size > 0)
const colorScaleCanvas = ref<HTMLCanvasElement | null>(null)
const colormapData = createColormap()
const topographyClipRange = computed(() => resolveMeasurementRange(currentDisplaySettings.value))
const canDownloadCurrentView = computed(() => {
  if (viewMode.value === 'video') {
    return Boolean(store.activeVideo && store.currentFrame !== null)
  }

  if (viewMode.value === 'heatmap') {
    return Boolean(store.activeAnalysis && isHeatmapExportable.value)
  }

  return Boolean(store.activeAnalysis && isTopographyExportable.value)
})

const canShowOverlay = computed(() => {
  return viewMode.value === 'video' ? store.activeAnalysis !== null : store.activeVideo !== null
})

const showOverlay = computed(() => {
  if (overlayPosition.value === 'off') return false
  return canShowOverlay.value
})

const showColorScale = computed(() => {
  if (!currentDisplaySettings.value) return false
  return viewMode.value === 'heatmap' || viewMode.value === 'topography'
})
const showTopographyClipSlider = computed(() => {
  return (
    viewMode.value === 'topography' &&
    showColorScale.value &&
    topographyClipRange.value !== null &&
    topographyClipEnabled.value
  )
})

const downloadButtonTitle = computed(() => {
  if (viewMode.value === 'video') {
    return 'Download current video frame'
  }

  if (viewMode.value === 'topography') {
    return 'Download current topography view'
  }

  return 'Download current heatmap view'
})

const colorScaleLabels = computed(() => {
  if (!currentDisplaySettings.value) return []
  return buildColorScaleLabels(
    currentDisplaySettings.value.heatmap_min_mm,
    currentDisplaySettings.value.heatmap_max_mm,
  )
})
const resolvedTopographyClipMm = computed(() => {
  const range = topographyClipRange.value
  if (!range) {
    return null
  }

  return clampMeasurementValue(
    topographyClipMm.value ?? resolveMeasurementRangeMidpoint(range),
    range,
  )
})
const topographyClipSliderModel = computed({
  get: () => {
    const range = topographyClipRange.value
    if (!range) {
      return [0]
    }

    return [resolvedTopographyClipMm.value ?? resolveMeasurementRangeMidpoint(range)]
  },
  set: (value: number[]) => {
    const range = topographyClipRange.value
    if (!range) {
      return
    }

    const nextValue = value[0]
    if (typeof nextValue !== 'number' || !Number.isFinite(nextValue)) {
      return
    }

    topographyClipMm.value = clampMeasurementValue(nextValue, range)
  },
})

function clampMeasurementValue(value: number, range: MeasurementRange): number {
  return Math.max(range.min, Math.min(range.max, value))
}

function resolveMeasurementRange(settings: DisplaySettings | null): MeasurementRange | null {
  if (!settings) {
    return null
  }

  const min = settings.heatmap_min_mm
  const max = settings.heatmap_max_mm
  if (!Number.isFinite(min) || !Number.isFinite(max) || max <= min) {
    return null
  }

  return { min, max }
}

function resolveMeasurementRangeMidpoint(range: MeasurementRange): number {
  return range.min + (range.max - range.min) / 2
}

function formatClipPlaneValue(value: number | null): string {
  if (value === null || !Number.isFinite(value)) {
    return '--'
  }

  const rounded = Math.round(value * 10) / 10
  return `${rounded.toFixed(1)} mm`
}

function renderColorScale() {
  const cvs = colorScaleCanvas.value
  if (!cvs || !currentDisplaySettings.value) return
  const ctx = cvs.getContext('2d')
  if (!ctx) return

  const dpr = window.devicePixelRatio || 1
  const cssWidth = 20
  const cssHeight = cvs.parentElement?.clientHeight ?? 200
  cvs.style.width = `${cssWidth}px`
  cvs.style.height = `${cssHeight}px`
  cvs.width = cssWidth * dpr
  cvs.height = cssHeight * dpr
  ctx.scale(dpr, dpr)

  for (let y = 0; y < cssHeight; y++) {
    const colorIndex = resolveColorScaleColorIndex(y, cssHeight)
    const r = colormapData[colorIndex * 3 + 0] ?? 0
    const g = colormapData[colorIndex * 3 + 1] ?? 0
    const b = colormapData[colorIndex * 3 + 2] ?? 0
    ctx.fillStyle = `rgb(${r},${g},${b})`
    ctx.fillRect(0, y, cssWidth, 1)
  }
}

function toggleTopographyClipping(): void {
  const nextEnabled = !topographyClipEnabled.value

  if (nextEnabled && topographyClipMm.value === null && topographyClipRange.value) {
    topographyClipMm.value = resolveMeasurementRangeMidpoint(topographyClipRange.value)
  }

  topographyClipEnabled.value = nextEnabled
}

async function handleFrameClick(frame: number, pointIndex: number) {
  highlightedPointIndex.value = pointIndex
  store.seekToFrame(frame)
}

function handleHeatmapExportAvailabilityChange(available: boolean) {
  isHeatmapExportable.value = available
}

function handleTopographyExportAvailabilityChange(available: boolean) {
  isTopographyExportable.value = available
}

async function handleDownloadCurrentView() {
  if (isExportingCurrentView.value || !canDownloadCurrentView.value) {
    return
  }

  isExportingCurrentView.value = true
  try {
    if (viewMode.value === 'video') {
      await videoPlayerRef.value?.downloadCurrentFrame()
      return
    }

    if (viewMode.value === 'heatmap') {
      await mainHeatmapViewerRef.value?.downloadCurrentView()
      return
    }

    await mainTopographyViewerRef.value?.downloadCurrentView()
  } catch (error) {
    console.error('Failed to download current view:', error)
  } finally {
    isExportingCurrentView.value = false
  }
}

watch(
  () => store.activeVideo?.id,
  async (videoId) => {
    if (videoId) {
      try {
        currentDisplaySettings.value = await getVideoDisplaySettings(videoId)
      } catch (err) {
        console.error('Failed to load display settings:', err)
        currentDisplaySettings.value = null
      }
    } else {
      currentDisplaySettings.value = null
    }
  },
  { immediate: true },
)

watch(
  [currentDisplaySettings, showColorScale],
  async () => {
    if (showColorScale.value && currentDisplaySettings.value) {
      await nextTick()
      renderColorScale()
    }
  },
  { deep: true },
)

watch(
  topographyClipRange,
  (range) => {
    if (!range || topographyClipMm.value === null) {
      return
    }

    topographyClipMm.value = clampMeasurementValue(topographyClipMm.value, range)
  },
  { immediate: true },
)

watch(
  () => props.selectedContractionId,
  (contractionId) => {
    if (contractionId) {
      showContractionOverlays.value = true
    }
  },
)

watch(
  () => store.activeAnalysis?.id,
  (analysisId) => {
    if (!analysisId) {
      isHeatmapExportable.value = false
      isTopographyExportable.value = false
    }
  },
)

function handleSettingsUpdated(settings: DisplaySettings) {
  currentDisplaySettings.value = settings
}

function handleCalibrationResult(result: CalibrationResult | null) {
  calibrationRegion.value = result
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
.download-toggle,
.topography-clip-toggle,
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
  gap: 0.5rem;
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
  width: 2.7rem;
  min-width: 2.7rem;
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

.color-scale-clip-control {
  width: 2rem;
  min-width: 2rem;
  display: flex;
  flex-direction: column;
  align-items: center;
  gap: 0.4rem;
}

.color-scale-clip-value {
  font-size: 10px;
  color: var(--text-secondary);
  writing-mode: vertical-rl;
  transform: rotate(180deg);
  line-height: 1;
}

.topography-clip-slider {
  flex: 1;
  min-height: 0;
  height: 100%;
}
</style>

<template>
  <div
    ref="containerRef"
    class="topography-container"
    @wheel.prevent="handleWheel"
    @mousedown.prevent="handleMouseDown"
  >
    <canvas
      ref="canvasRef"
      :class="['topography-canvas', { 'topography-canvas-hidden': !showCanvas }]"
      @click="handleCanvasClick"
    />

    <div v-if="isLoading" class="loading-state topography-overlay">
      Loading heatmap data...
    </div>
    <div v-else-if="displayError" class="error-state topography-overlay topography-error">
      {{ displayError }}
    </div>
    <div v-else-if="!hasSurface" class="no-data-state topography-overlay">
      No heatmap data available.
    </div>

    <div v-if="showCanvas" class="topography-hint">
      Drag to pan · Scroll to zoom
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import { useAnalysisHeatmap } from '../composables/useAnalysisHeatmap';
import { createColormap } from '../lib/colormap';
import { downloadCanvas } from '../lib/download';
import {
  buildHeatmapTopographyFrameLine,
  buildHeatmapTopographySurface,
  DEFAULT_TOPOGRAPHY_MAX_COLUMNS,
} from '../lib/heatmapTopography';
import {
  createHeatmapTopographyScene,
  type HeatmapTopographySceneController,
} from '../lib/heatmapTopographyScene';

const EXPORT_WIDTH = 1920;
const EXPORT_HEIGHT = 1080;

const props = defineProps<{
  analysisId: string;
  currentFrame?: number | null;
  pixelToMmFactorOverride?: number | null;
  heatmapMinMmOverride?: number | null;
  heatmapMaxMmOverride?: number | null;
}>();

const emit = defineEmits<{
  'frame-click': [frame: number, pointIndex: number];
  'export-availability-change': [available: boolean];
}>();

const canvasRef = ref<HTMLCanvasElement | null>(null);
const containerRef = ref<HTMLDivElement | null>(null);
const resizeObserver = ref<ResizeObserver | null>(null);
const sceneError = ref<string | null>(null);

let sceneController: HeatmapTopographySceneController | null = null;
let isDragging = false;
let hasDragged = false;
let mouseDownX = 0;
let mouseDownY = 0;

const {
  data,
  error,
  heatmapMaxMm,
  heatmapMinMm,
  isLoading,
  meta,
  pixelToMmFactor,
} = useAnalysisHeatmap({
  analysisId: computed(() => props.analysisId),
  pixelToMmFactorOverride: computed(() => props.pixelToMmFactorOverride ?? null),
  heatmapMinMmOverride: computed(() => props.heatmapMinMmOverride ?? null),
  heatmapMaxMmOverride: computed(() => props.heatmapMaxMmOverride ?? null),
});

const colormap = createColormap();

const surface = computed(() => {
  if (!meta.value || !data.value || meta.value.width === 0 || meta.value.height === 0) {
    return null;
  }

  return buildHeatmapTopographySurface({
    colormap,
    frameCount: meta.value.width,
    heatmapMaxMm: heatmapMaxMm.value,
    heatmapMinMm: heatmapMinMm.value,
    maxColumns: DEFAULT_TOPOGRAPHY_MAX_COLUMNS,
    pixelToMmFactor: pixelToMmFactor.value,
    pointCount: meta.value.height,
    values: data.value,
  });
});

const frameLine = computed(() => {
  if (!surface.value || !data.value) {
    return null;
  }

  return buildHeatmapTopographyFrameLine({
    frame: props.currentFrame,
    heatmapMaxMm: heatmapMaxMm.value,
    heatmapMinMm: heatmapMinMm.value,
    metrics: surface.value.metrics,
    pixelToMmFactor: pixelToMmFactor.value,
    values: data.value,
  });
});

const displayError = computed(() => error.value ?? sceneError.value);

const hasSurface = computed(() => {
  return Boolean(
    surface.value &&
    surface.value.positions.length > 0 &&
    surface.value.indices.length > 0 &&
    !displayError.value,
  );
});

const isExportable = computed(() => hasSurface.value);
const showCanvas = computed(() => !isLoading.value && !displayError.value && hasSurface.value);

watch(
  isExportable,
  (available) => {
    emit('export-availability-change', available);
  },
  { immediate: true },
);

watch(
  surface,
  () => {
    applySceneSurface();
  },
);

watch(
  frameLine,
  () => {
    applySceneFrameLine();
  },
);

onMounted(async () => {
  await nextTick();
  initializeScene();
});

onUnmounted(() => {
  teardownPointerListeners();
  resizeObserver.value?.disconnect();
  sceneController?.dispose();
  sceneController = null;
});

async function initializeScene(): Promise<void> {
  if (!canvasRef.value || !containerRef.value) {
    return;
  }

  try {
    sceneController = createHeatmapTopographyScene({
      canvas: canvasRef.value,
      container: containerRef.value,
    });
    setupResizeObserver();
    applySceneSurface();
    applySceneFrameLine();
  } catch (err) {
    sceneError.value = err instanceof Error ? err.message : 'Failed to initialize topography view';
    console.error('Failed to initialize topography view:', err);
  }
}

function setupResizeObserver(): void {
  if (!containerRef.value || !sceneController) {
    return;
  }

  resizeObserver.value = new ResizeObserver(() => {
    sceneController?.resize();
  });
  resizeObserver.value.observe(containerRef.value);
}

function applySceneSurface(): void {
  if (!sceneController) {
    return;
  }

  sceneController.setSurface(hasSurface.value ? surface.value : null);
}

function applySceneFrameLine(): void {
  if (!sceneController) {
    return;
  }

  sceneController.setFrameLine(hasSurface.value ? frameLine.value : null);
}

function handleWheel(e: WheelEvent): void {
  if (!showCanvas.value) {
    return;
  }

  sceneController?.zoom(e.deltaY);
}

function handleMouseDown(e: MouseEvent): void {
  if (!showCanvas.value || !sceneController) {
    return;
  }

  isDragging = true;
  hasDragged = false;
  mouseDownX = e.clientX;
  mouseDownY = e.clientY;
  sceneController.beginPan(e.clientX, e.clientY);
  window.addEventListener('mousemove', handleMouseMove);
  window.addEventListener('mouseup', handleMouseUp);
}

function handleMouseMove(e: MouseEvent): void {
  if (!isDragging || !sceneController) {
    return;
  }

  const totalDx = e.clientX - mouseDownX;
  const totalDy = e.clientY - mouseDownY;
  if (Math.abs(totalDx) <= 3 && Math.abs(totalDy) <= 3) {
    return;
  }

  hasDragged = true;
  sceneController.updatePan(e.clientX, e.clientY);
}

function handleMouseUp(): void {
  isDragging = false;
  sceneController?.endPan();
  teardownPointerListeners();
  setTimeout(() => {
    hasDragged = false;
  }, 10);
}

function teardownPointerListeners(): void {
  window.removeEventListener('mousemove', handleMouseMove);
  window.removeEventListener('mouseup', handleMouseUp);
}

function handleCanvasClick(e: MouseEvent): void {
  if (!sceneController || !showCanvas.value || hasDragged) {
    return;
  }

  const picked = sceneController.pick(e.clientX, e.clientY);
  if (picked) {
    emit('frame-click', picked.frame, picked.pointIndex);
  }
}

async function captureExportCanvas(): Promise<HTMLCanvasElement> {
  if (!sceneController || !isExportable.value) {
    throw new Error('No topography data available for export');
  }

  return sceneController.captureCanvas(EXPORT_WIDTH, EXPORT_HEIGHT);
}

async function downloadCurrentView(): Promise<void> {
  const exportCanvas = await captureExportCanvas();
  await downloadCanvas(exportCanvas, `topography_${props.analysisId}.png`);
}

defineExpose({
  captureExportCanvas,
  downloadCurrentView,
});
</script>

<style scoped>
.topography-container {
  position: relative;
  width: 100%;
  height: 500px;
  min-height: 300px;
  max-height: 800px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow: hidden;
  box-sizing: border-box;
  background:
    radial-gradient(circle at top left, rgba(143, 198, 255, 0.18), transparent 38%),
    linear-gradient(180deg, #0c1826 0%, #08111c 100%);
}

.topography-canvas {
  display: block;
  width: 100%;
  height: 100%;
  cursor: grab;
}

.topography-canvas-hidden {
  visibility: hidden;
}

.topography-overlay {
  position: absolute;
  inset: 0;
}

.topography-hint {
  position: absolute;
  right: 0.85rem;
  bottom: 0.7rem;
  font-size: 0.72rem;
  color: rgba(255, 255, 255, 0.58);
  pointer-events: none;
}

.loading-state,
.error-state,
.no-data-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary);
}

.topography-error {
  color: var(--color-error-600);
  background: var(--color-error-100);
}
</style>

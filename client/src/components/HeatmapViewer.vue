<template>
  <div
    ref="container"
    :class="['heatmap-container', { compact: compact }]"
    @wheel.prevent="onWheel"
    @mousedown.prevent="onMouseDown"
  >
    <div v-if="isLoading" class="loading-state">
      Loading heatmap data...
    </div>
    <div v-else-if="error" class="error-state">
      {{ error }}
    </div>
    <div v-else-if="!meta || !data || meta.width === 0 || meta.height === 0" class="no-data-state">
      No heatmap data available.
    </div>
    <div v-else class="heatmap-wrapper">
      <!-- Y-axis labels (left side) - aligned with heatmap only -->
      <div v-if="!compact" class="y-axis-wrapper">
        <canvas ref="yAxisCanvas" class="y-axis-canvas"></canvas>
        <div class="axis-corner"></div>
      </div>
      <!-- Main heatmap canvas -->
      <div class="heatmap-canvas-wrapper">
        <canvas
          ref="canvas"
          class="heatmap-canvas"
          @mousemove="onCanvasMouseMove"
          @mouseleave="onCanvasMouseLeave"
          @click="onCanvasClick"
        ></canvas>
        <!-- X-axis labels (bottom) -->
        <canvas v-if="!compact" ref="xAxisCanvas" class="x-axis-canvas"></canvas>
      </div>
    </div>
    <div v-if="hoverInfo && !isLoading && !error && !compact" class="tooltip" :style="tooltipStyle">
      Time: {{ formatTimestamp(hoverInfo.time) }}<br />
      Measured: {{ hoverInfo.valueMm.toFixed(3) }} mm
    </div>
  </div>
</template>

<script setup lang="ts">
import { computed, nextTick, onMounted, onUnmounted, ref, watch } from 'vue';

import { useAnalysisHeatmap } from '../composables/useAnalysisHeatmap';
import { createColormap } from '../lib/colormap';
import { downloadCanvas } from '../lib/download';
import {
  createHeatmapRasterCanvas,
  drawHeatmapOverlays,
  resolveHeatmapExportDimensions,
} from '../lib/heatmapRendering';
import { useAnalysisStore } from '../stores/analysis';

const props = defineProps<{
  analysisId: string;
  currentFrame?: number | null;
  compact?: boolean;
  showContractionOverlays?: boolean;
  selectedContractionId?: string | null;
  pixelToMmFactorOverride?: number | null;
  heatmapMinMmOverride?: number | null;
  heatmapMaxMmOverride?: number | null;
}>();

const store = useAnalysisStore();

const emit = defineEmits<{
  'frame-click': [frame: number, pointIndex: number];
  'export-availability-change': [available: boolean];
}>();

const canvas = ref<HTMLCanvasElement | null>(null);
const xAxisCanvas = ref<HTMLCanvasElement | null>(null);
const yAxisCanvas = ref<HTMLCanvasElement | null>(null);
const container = ref<HTMLDivElement | null>(null);
const resizeObserver = ref<ResizeObserver | null>(null);

const {
  data,
  error,
  hasExportableData,
  hasRenderableData,
  heatmapMaxMm,
  heatmapMinMm,
  isLoading,
  loadData,
  meta,
  pixelToMmFactor,
} = useAnalysisHeatmap({
  analysisId: computed(() => props.analysisId),
  pixelToMmFactorOverride: computed(() => props.pixelToMmFactorOverride ?? null),
  heatmapMinMmOverride: computed(() => props.heatmapMinMmOverride ?? null),
  heatmapMaxMmOverride: computed(() => props.heatmapMaxMmOverride ?? null),
});

const scale = ref(1);
const offsetX = ref(0);
const offsetY = ref(0);
const hoverInfo = ref<{ time: number; valueMm: number } | null>(null);
const mousePos = ref<{ x: number; y: number } | null>(null);
const initialScaleAnalysisId = ref<string | null>(null);

const tooltipStyle = computed(() => {
  if (!mousePos.value) {
    return {};
  }

  return {
    left: `${mousePos.value.x + 10}px`,
    top: `${mousePos.value.y + 10}px`,
  };
});

const AXIS_WIDTH = 60;
const AXIS_HEIGHT = 30;
const colormap = createColormap();

onMounted(() => {
  renderHeatmap();
  renderAxes();
  setupResizeObserver();
});

onUnmounted(() => {
  resizeObserver.value?.disconnect();
});

watch([meta, data, scale, offsetX, () => props.currentFrame], () => {
  renderHeatmap();
  if (!props.compact) {
    renderAxes();
  }
});

watch(
  () => [pixelToMmFactor.value, heatmapMinMm.value, heatmapMaxMm.value],
  () => {
    if (meta.value && data.value) {
      renderHeatmap();
    }
  },
);

watch(
  () => props.analysisId,
  (analysisId, previousAnalysisId) => {
    if (analysisId === previousAnalysisId) {
      return;
    }

    initialScaleAnalysisId.value = null;
    clearHoverInfo();
    scale.value = 1;
    offsetX.value = 0;
    offsetY.value = 0;
  },
);

watch(
  [hasRenderableData, () => meta.value?.width, () => meta.value?.height],
  async ([renderable]) => {
    if (!renderable || initialScaleAnalysisId.value === props.analysisId) {
      return;
    }

    await nextTick();
    calculateInitialScale();
    initialScaleAnalysisId.value = props.analysisId;
  },
);

watch(
  () => [props.showContractionOverlays, props.selectedContractionId, store.contractionEvents],
  () => {
    if (meta.value && data.value) {
      renderHeatmap();
    }
  },
  { deep: true },
);

watch(
  hasExportableData,
  (available) => {
    emit('export-availability-change', available);
  },
  { immediate: true },
);

function setupResizeObserver(): void {
  if (!container.value) {
    return;
  }

  resizeObserver.value = new ResizeObserver(() => {
    if (meta.value && data.value && container.value) {
      const axisWidth = props.compact ? 0 : AXIS_WIDTH;
      const containerWidth = container.value.clientWidth - axisWidth;
      const videoMeta = store.currentVideo?.metadata;
      const expectedTotalFrames = videoMeta
        ? Math.floor(videoMeta.total_frames / (videoMeta.frame_multiplier ?? 1))
        : 0;
      const dataWidth = expectedTotalFrames > meta.value.width
        ? expectedTotalFrames
        : meta.value.width;
      const minScale = containerWidth / dataWidth;

      if (scale.value <= minScale * 1.01) {
        calculateInitialScale();
      }
    }

    renderHeatmap();
    renderAxes();
  });

  resizeObserver.value.observe(container.value);
}

function calculateInitialScale(): void {
  if (!container.value || !meta.value) {
    return;
  }

  const axisWidth = props.compact ? 0 : AXIS_WIDTH;
  const containerWidth = container.value.clientWidth - axisWidth;
  const videoMeta = store.currentVideo?.metadata;
  const expectedTotalFrames = videoMeta
    ? Math.floor(videoMeta.total_frames / (videoMeta.frame_multiplier ?? 1))
    : 0;
  const dataWidth = expectedTotalFrames > meta.value.width
    ? expectedTotalFrames
    : meta.value.width;

  if (containerWidth <= 0 || dataWidth <= 0) {
    return;
  }

  scale.value = containerWidth / dataWidth;
  offsetX.value = 0;
  offsetY.value = 0;
}

function createBaseHeatmapCanvas(): HTMLCanvasElement | null {
  if (!meta.value || !data.value || meta.value.width === 0 || meta.value.height === 0) {
    return null;
  }

  return createHeatmapRasterCanvas({
    width: meta.value.width,
    height: meta.value.height,
    values: data.value,
    pixelToMmFactor: pixelToMmFactor.value,
    heatmapMinMm: heatmapMinMm.value,
    heatmapMaxMm: heatmapMaxMm.value,
    colormap,
  });
}

function renderHeatmap(): void {
  if (!canvas.value || !meta.value || !data.value || !container.value) {
    return;
  }

  const ctx = canvas.value.getContext('2d');
  if (!ctx) {
    return;
  }

  const axisWidth = props.compact ? 0 : AXIS_WIDTH;
  const axisHeight = props.compact ? 0 : AXIS_HEIGHT;
  const containerWidth = Math.max(1, container.value.clientWidth - axisWidth);
  const containerHeight = Math.max(1, container.value.clientHeight - axisHeight);
  const { width, height } = meta.value;
  const offCanvas = createBaseHeatmapCanvas();
  if (!offCanvas) {
    return;
  }

  canvas.value.style.width = `${containerWidth}px`;
  canvas.value.style.height = `${containerHeight}px`;

  const dpr = window.devicePixelRatio || 1;
  const internalWidth = containerWidth * dpr;
  const internalHeight = containerHeight * dpr;

  if (canvas.value.width !== internalWidth || canvas.value.height !== internalHeight) {
    canvas.value.width = internalWidth;
    canvas.value.height = internalHeight;
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, containerWidth, containerHeight);

  const scaledDataWidth = width * scale.value;
  const scaledDataHeight = containerHeight;

  ctx.save();
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(offCanvas, offsetX.value, 0, scaledDataWidth, scaledDataHeight);

  drawHeatmapOverlays(ctx, {
    width,
    height,
    currentFrame: props.currentFrame,
    showContractionOverlays: props.showContractionOverlays,
    selectedContractionId: props.selectedContractionId,
    contractionEvents: store.contractionEvents,
    scaleX: scale.value,
    scaledDataHeight,
    offsetX: offsetX.value,
  });

  ctx.restore();
}

async function captureExportCanvas(): Promise<HTMLCanvasElement> {
  if (!hasExportableData.value) {
    await loadData();
  }

  const baseCanvas = createBaseHeatmapCanvas();
  const resolvedMeta = meta.value;
  if (!baseCanvas || !resolvedMeta) {
    throw new Error('No heatmap data available for export');
  }

  const exportDimensions = resolveHeatmapExportDimensions(
    resolvedMeta.width,
    resolvedMeta.height,
  );
  const exportCanvas = document.createElement('canvas');
  exportCanvas.width = exportDimensions.width;
  exportCanvas.height = exportDimensions.height;
  const exportCtx = exportCanvas.getContext('2d');
  if (!exportCtx) {
    throw new Error('Failed to create heatmap export context');
  }

  exportCtx.imageSmoothingEnabled = false;
  exportCtx.drawImage(baseCanvas, 0, 0, exportCanvas.width, exportCanvas.height);

  drawHeatmapOverlays(exportCtx, {
    width: resolvedMeta.width,
    height: resolvedMeta.height,
    currentFrame: props.currentFrame,
    showContractionOverlays: props.showContractionOverlays,
    selectedContractionId: props.selectedContractionId,
    contractionEvents: store.contractionEvents,
    scaleX: exportDimensions.scaleX,
    scaledDataHeight: exportDimensions.height,
    frameMarkerLineWidth: Math.max(1, exportDimensions.scaleX),
  });

  return exportCanvas;
}

async function downloadCurrentView(): Promise<void> {
  const exportCanvas = await captureExportCanvas();
  await downloadCanvas(exportCanvas, `heatmap_${props.analysisId}.png`);
}

defineExpose({
  captureExportCanvas,
  downloadCurrentView,
});

function renderAxes(): void {
  if (props.compact) {
    return;
  }

  if (!meta.value || !xAxisCanvas.value || !yAxisCanvas.value || !canvas.value || !container.value) {
    return;
  }

  const { width, height, fps } = meta.value;
  const xCtx = xAxisCanvas.value.getContext('2d');
  const yCtx = yAxisCanvas.value.getContext('2d');
  if (!xCtx || !yCtx) {
    return;
  }

  const axisWidth = props.compact ? 0 : AXIS_WIDTH;
  const axisHeight = props.compact ? 0 : AXIS_HEIGHT;
  const heatmapWidth = container.value.clientWidth - axisWidth;
  const heatmapHeight = container.value.clientHeight - axisHeight;
  const dpr = window.devicePixelRatio || 1;

  xAxisCanvas.value.style.width = `${heatmapWidth}px`;
  xAxisCanvas.value.style.height = `${AXIS_HEIGHT}px`;
  xAxisCanvas.value.width = heatmapWidth * dpr;
  xAxisCanvas.value.height = AXIS_HEIGHT * dpr;
  xCtx.scale(dpr, dpr);
  xCtx.clearRect(0, 0, heatmapWidth, AXIS_HEIGHT);

  xCtx.fillStyle = '#000';
  xCtx.font = '12px sans-serif';
  xCtx.textAlign = 'center';
  xCtx.textBaseline = 'top';

  const startFrame = Math.max(0, Math.floor(-offsetX.value / scale.value));
  const endFrame = Math.min(width, Math.ceil((heatmapWidth - offsetX.value) / scale.value));
  const numTicks = 10;
  const tickSpacing = (endFrame - startFrame) / numTicks;

  for (let i = 0; i <= numTicks; i += 1) {
    const frame = Math.floor(startFrame + i * tickSpacing);
    if (frame < 0 || frame >= width) {
      continue;
    }

    const timeInSeconds = frame / fps;
    const xPos = frame * scale.value + offsetX.value;

    xCtx.beginPath();
    xCtx.moveTo(xPos, 0);
    xCtx.lineTo(xPos, 5);
    xCtx.strokeStyle = '#000';
    xCtx.stroke();
    xCtx.fillText(`${timeInSeconds.toFixed(1)}s`, xPos, 8);
  }

  yAxisCanvas.value.style.width = `${AXIS_WIDTH}px`;
  yAxisCanvas.value.style.height = `${heatmapHeight}px`;
  yAxisCanvas.value.width = AXIS_WIDTH * dpr;
  yAxisCanvas.value.height = heatmapHeight * dpr;
  yCtx.scale(dpr, dpr);
  yCtx.clearRect(0, 0, AXIS_WIDTH, heatmapHeight);

  yCtx.fillStyle = '#000';
  yCtx.font = '12px sans-serif';
  yCtx.textAlign = 'right';
  yCtx.textBaseline = 'middle';

  const pixelsPerTick = 30;
  const maxTicksBySpace = Math.floor(heatmapHeight / pixelsPerTick);
  const numYTicks = Math.min(maxTicksBySpace, height, 20);

  if (numYTicks <= 0 || height <= 0) {
    return;
  }

  for (let i = 0; i <= numYTicks; i += 1) {
    const pointIndex = Math.round((i / numYTicks) * height);
    if (pointIndex < 0 || pointIndex >= height) {
      continue;
    }

    const yPos = ((pointIndex + 0.5) / height) * heatmapHeight;
    yCtx.beginPath();
    yCtx.moveTo(AXIS_WIDTH - 5, yPos);
    yCtx.lineTo(AXIS_WIDTH, yPos);
    yCtx.strokeStyle = '#000';
    yCtx.stroke();
    yCtx.fillText(`${pointIndex}`, AXIS_WIDTH - 8, yPos);
  }
}

function onWheel(e: WheelEvent): void {
  if (!meta.value || !container.value) {
    return;
  }

  const delta = -e.deltaY;
  const zoomFactor = delta > 0 ? 1.1 : 0.9;
  const oldScale = scale.value;
  scale.value *= zoomFactor;

  const axisWidth = props.compact ? 0 : AXIS_WIDTH;
  const containerWidth = container.value.clientWidth - axisWidth;
  const dataWidth = meta.value.width;
  const minScale = containerWidth / dataWidth;
  const maxScale = 10;

  if (scale.value < minScale) {
    scale.value = minScale;
  }
  if (scale.value > maxScale) {
    scale.value = maxScale;
  }

  if (!canvas.value) {
    return;
  }

  const rect = canvas.value.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const zoomPointX = (mouseX - offsetX.value) / oldScale;
  offsetX.value = mouseX - zoomPointX * scale.value;

  const scaledDataWidth = dataWidth * scale.value;
  if (scaledDataWidth <= containerWidth) {
    offsetX.value = 0;
    return;
  }

  if (offsetX.value > 0) {
    offsetX.value = 0;
  }
  if (offsetX.value < containerWidth - scaledDataWidth) {
    offsetX.value = containerWidth - scaledDataWidth;
  }
}

let isDragging = false;
let hasDragged = false;
let mouseDownX = 0;
let mouseDownY = 0;
let lastX = 0;
let lastY = 0;

function onMouseDown(e: MouseEvent): void {
  hasDragged = false;
  isDragging = true;
  mouseDownX = e.clientX;
  mouseDownY = e.clientY;
  lastX = e.clientX;
  lastY = e.clientY;

  window.addEventListener('mousemove', onMouseMoveDrag);
  window.addEventListener('mouseup', onMouseUp);
}

function onMouseMoveDrag(e: MouseEvent): void {
  if (!isDragging) {
    return;
  }

  const dx = e.clientX - lastX;
  const totalDx = e.clientX - mouseDownX;
  const totalDy = e.clientY - mouseDownY;

  if (Math.abs(totalDx) <= 3 && Math.abs(totalDy) <= 3) {
    return;
  }

  hasDragged = true;
  lastX = e.clientX;
  lastY = e.clientY;
  offsetX.value += dx;
  offsetY.value = 0;
}

function onMouseUp(): void {
  isDragging = false;
  setTimeout(() => {
    hasDragged = false;
  }, 10);
  window.removeEventListener('mousemove', onMouseMoveDrag);
  window.removeEventListener('mouseup', onMouseUp);
}

function clearHoverInfo(): void {
  hoverInfo.value = null;
  mousePos.value = null;
}

function formatTimestamp(timeInSeconds: number): string {
  const totalMilliseconds = Math.max(0, Math.round(timeInSeconds * 1000));
  const minutes = Math.floor(totalMilliseconds / 60000);
  const seconds = Math.floor((totalMilliseconds % 60000) / 1000);
  const milliseconds = totalMilliseconds % 1000;
  return `${minutes}:${seconds.toString().padStart(2, '0')}.${milliseconds.toString().padStart(3, '0')}`;
}

function getFrameFromMouse(e: MouseEvent): { frame: number; index: number } | null {
  if (!canvas.value || !meta.value || !data.value || !container.value) {
    return null;
  }

  const rect = canvas.value.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;
  const containerHeight = container.value.clientHeight - (props.compact ? 0 : AXIS_HEIGHT);
  const xInImage = (mouseX - offsetX.value) / scale.value;
  const yInImage = (mouseY / containerHeight) * meta.value.height;
  const frame = Math.floor(xInImage);
  const index = Math.floor(yInImage);

  if (frame < 0 || index < 0 || frame >= meta.value.width || index >= meta.value.height) {
    return null;
  }

  return { frame, index };
}

function onCanvasMouseMove(e: MouseEvent): void {
  if (!canvas.value || !meta.value || !data.value || !container.value || isDragging) {
    clearHoverInfo();
    return;
  }

  const result = getFrameFromMouse(e);
  if (!result) {
    clearHoverInfo();
    return;
  }

  mousePos.value = { x: e.clientX, y: e.clientY };

  const { frame, index } = result;
  const dataIndex = frame * meta.value.height + index;
  const value = data.value[dataIndex] ?? 0;
  const valueMm = value / pixelToMmFactor.value;
  const timeInSeconds = frame / meta.value.fps;

  hoverInfo.value = { time: timeInSeconds, valueMm };
}

function onCanvasMouseLeave(): void {
  clearHoverInfo();
}

function onCanvasClick(e: MouseEvent): void {
  if (!canvas.value || !meta.value || !data.value || !container.value || hasDragged) {
    return;
  }

  const result = getFrameFromMouse(e);
  if (result) {
    emit('frame-click', result.frame, result.index);
  }
}
</script>

<style scoped>
.heatmap-container {
  position: relative;
  width: 100%;
  height: 500px;
  min-height: 300px;
  max-height: 800px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
  overflow: hidden;
  box-sizing: border-box;
}

.heatmap-wrapper {
  display: flex;
  width: 100%;
  height: 100%;
  min-width: 0;
  min-height: 0;
  overflow: hidden;
}

.y-axis-wrapper {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
  width: 60px;
}

.y-axis-canvas {
  flex: 1;
  border-right: 1px solid var(--border-light);
  background: var(--bg-secondary);
  width: 60px;
  min-height: 0;
}

.axis-corner {
  flex-shrink: 0;
  width: 60px;
  height: 30px;
  border-right: 1px solid var(--border-light);
  background: var(--bg-secondary);
}

.heatmap-canvas-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
  min-width: 0;
  min-height: 0;
}

.heatmap-canvas {
  flex: 1;
  display: block;
  cursor: crosshair;
  width: 100%;
  min-width: 0;
  min-height: 0;
  object-fit: contain;
}

.heatmap-container.compact {
  height: 100%;
  min-height: 0;
}

.x-axis-canvas {
  flex-shrink: 0;
  border-top: 1px solid var(--border-light);
  background: var(--bg-secondary);
  width: 100%;
  height: 30px;
}

.tooltip {
  position: fixed;
  background: rgba(0, 0, 0, 0.85);
  color: white;
  padding: 8px 12px;
  border-radius: 4px;
  font-size: 12px;
  pointer-events: none;
  z-index: 1000;
  white-space: pre-line;
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

.error-state {
  color: var(--color-error-600);
  background: var(--color-error-100);
  border-radius: 4px;
  margin: 1rem;
}

</style>

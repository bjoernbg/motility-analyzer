<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import type { HeatmapDiffMeta } from '../composables/useHeatmapDiff';

const props = defineProps<{
  meta: HeatmapDiffMeta | null;
  diffMm: Float32Array | null;
  leftAlignedMm: Float32Array | null;
  rightAlignedMm: Float32Array | null;
  currentSyncedTimeSec: number;
  isLoading: boolean;
  error: string | null;
}>();

const emit = defineEmits<{
  'frame-click': [frame: number, pointIndex: number];
}>();

const container = ref<HTMLDivElement | null>(null);
const canvas = ref<HTMLCanvasElement | null>(null);
const xAxisCanvas = ref<HTMLCanvasElement | null>(null);
const yAxisCanvas = ref<HTMLCanvasElement | null>(null);
const resizeObserver = ref<ResizeObserver | null>(null);

const scale = ref(1);
const offsetX = ref(0);
const offsetY = ref(0);

const hoverInfo = ref<{
  leftMm: number;
  rightMm: number;
  diffMm: number;
  syncedTimeSec: number;
} | null>(null);
const mousePos = ref<{ x: number; y: number } | null>(null);

const AXIS_WIDTH = 60;
const AXIS_HEIGHT = 30;

const tooltipStyle = computed(() => {
  if (!mousePos.value) {
    return {};
  }
  return {
    left: `${mousePos.value.x + 10}px`,
    top: `${mousePos.value.y + 10}px`,
  };
});

const currentFrame = computed(() => {
  if (!props.meta || props.meta.fps <= 0) {
    return null;
  }
  const frame = Math.round((props.currentSyncedTimeSec - props.meta.minTimeSec) * props.meta.fps);
  return Math.max(0, Math.min(props.meta.width - 1, frame));
});

function clearHover() {
  hoverInfo.value = null;
  mousePos.value = null;
}

function formatTimestamp(seconds: number): string {
  const totalMilliseconds = Math.max(0, Math.round(seconds * 1000));
  const minutes = Math.floor(totalMilliseconds / 60000);
  const secs = Math.floor((totalMilliseconds % 60000) / 1000);
  const millis = totalMilliseconds % 1000;
  return `${minutes}:${secs.toString().padStart(2, '0')}.${millis.toString().padStart(3, '0')}`;
}

function mapDivergingColor(value: number, absMax: number): [number, number, number] {
  const max = Math.max(absMax, 1e-6);
  const normalized = Math.max(-1, Math.min(1, value / max));

  if (normalized >= 0) {
    const t = normalized;
    const r = Math.round(255);
    const g = Math.round(255 - t * 185);
    const b = Math.round(255 - t * 255);
    return [r, g, b];
  }

  const t = Math.abs(normalized);
  const r = Math.round(255 - t * 255);
  const g = Math.round(255 - t * 177);
  const b = Math.round(255);
  return [r, g, b];
}

function calculateInitialScale() {
  if (!container.value || !props.meta) {
    return;
  }
  const containerWidth = Math.max(1, container.value.clientWidth - AXIS_WIDTH);
  const dataWidth = Math.max(1, props.meta.width);
  scale.value = containerWidth / dataWidth;
  offsetX.value = 0;
  offsetY.value = 0;
}

function renderHeatmap() {
  if (
    !container.value ||
    !canvas.value ||
    !props.meta ||
    !props.diffMm ||
    props.diffMm.length === 0
  ) {
    return;
  }

  const ctx = canvas.value.getContext('2d');
  if (!ctx) {
    return;
  }

  const containerWidth = Math.max(1, container.value.clientWidth - AXIS_WIDTH);
  const containerHeight = Math.max(1, container.value.clientHeight - AXIS_HEIGHT);
  const dpr = window.devicePixelRatio || 1;

  canvas.value.style.width = `${containerWidth}px`;
  canvas.value.style.height = `${containerHeight}px`;
  canvas.value.width = Math.round(containerWidth * dpr);
  canvas.value.height = Math.round(containerHeight * dpr);
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, containerWidth, containerHeight);

  const width = props.meta.width;
  const height = props.meta.height;

  const offscreen = document.createElement('canvas');
  offscreen.width = width;
  offscreen.height = height;
  const offCtx = offscreen.getContext('2d');
  if (!offCtx) {
    return;
  }

  const imageData = offCtx.createImageData(width, height);
  const pixels = imageData.data;
  const max = props.meta.diffAbsMaxMm;
  for (let frameIndex = 0; frameIndex < width; frameIndex++) {
    for (let pointIndex = 0; pointIndex < height; pointIndex++) {
      const sourceIndex = frameIndex * height + pointIndex;
      const diffValue = props.diffMm[sourceIndex] ?? 0;
      const [r, g, b] = mapDivergingColor(diffValue, max);
      const pixelIndex = (pointIndex * width + frameIndex) * 4;
      pixels[pixelIndex] = r;
      pixels[pixelIndex + 1] = g;
      pixels[pixelIndex + 2] = b;
      pixels[pixelIndex + 3] = 255;
    }
  }

  offCtx.putImageData(imageData, 0, 0);

  const scaledDataWidth = width * scale.value;
  ctx.save();
  ctx.translate(offsetX.value, 0);
  ctx.imageSmoothingEnabled = false;
  ctx.drawImage(offscreen, 0, 0, scaledDataWidth, containerHeight);

  if (currentFrame.value !== null) {
    const x = currentFrame.value * scale.value;
    ctx.strokeStyle = '#1f2937';
    ctx.lineWidth = 2;
    ctx.setLineDash([6, 4]);
    ctx.beginPath();
    ctx.moveTo(x, 0);
    ctx.lineTo(x, containerHeight);
    ctx.stroke();
    ctx.setLineDash([]);
  }

  ctx.restore();
}

function renderAxes() {
  if (!container.value || !xAxisCanvas.value || !yAxisCanvas.value || !props.meta) {
    return;
  }

  const xCtx = xAxisCanvas.value.getContext('2d');
  const yCtx = yAxisCanvas.value.getContext('2d');
  if (!xCtx || !yCtx) {
    return;
  }

  const heatmapWidth = Math.max(1, container.value.clientWidth - AXIS_WIDTH);
  const heatmapHeight = Math.max(1, container.value.clientHeight - AXIS_HEIGHT);
  const dpr = window.devicePixelRatio || 1;

  xAxisCanvas.value.style.width = `${heatmapWidth}px`;
  xAxisCanvas.value.style.height = `${AXIS_HEIGHT}px`;
  xAxisCanvas.value.width = Math.round(heatmapWidth * dpr);
  xAxisCanvas.value.height = Math.round(AXIS_HEIGHT * dpr);
  xCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  xCtx.clearRect(0, 0, heatmapWidth, AXIS_HEIGHT);
  xCtx.fillStyle = '#111827';
  xCtx.font = '12px sans-serif';
  xCtx.textAlign = 'center';
  xCtx.textBaseline = 'top';

  const startFrame = Math.max(0, Math.floor(-offsetX.value / scale.value));
  const endFrame = Math.min(props.meta.width, Math.ceil((heatmapWidth - offsetX.value) / scale.value));
  const tickCount = 10;
  const tickSpacing = Math.max(1, (endFrame - startFrame) / tickCount);

  for (let i = 0; i <= tickCount; i++) {
    const frame = Math.floor(startFrame + i * tickSpacing);
    if (frame < 0 || frame >= props.meta.width) {
      continue;
    }
    const time = props.meta.minTimeSec + frame / props.meta.fps;
    const x = frame * scale.value + offsetX.value;
    xCtx.beginPath();
    xCtx.moveTo(x, 0);
    xCtx.lineTo(x, 5);
    xCtx.strokeStyle = '#111827';
    xCtx.stroke();
    xCtx.fillText(`${time.toFixed(1)}s`, x, 8);
  }

  yAxisCanvas.value.style.width = `${AXIS_WIDTH}px`;
  yAxisCanvas.value.style.height = `${heatmapHeight}px`;
  yAxisCanvas.value.width = Math.round(AXIS_WIDTH * dpr);
  yAxisCanvas.value.height = Math.round(heatmapHeight * dpr);
  yCtx.setTransform(dpr, 0, 0, dpr, 0, 0);
  yCtx.clearRect(0, 0, AXIS_WIDTH, heatmapHeight);
  yCtx.fillStyle = '#111827';
  yCtx.font = '12px sans-serif';
  yCtx.textAlign = 'right';
  yCtx.textBaseline = 'middle';

  const pointCount = props.meta.height;
  const ticks = Math.min(20, pointCount);
  for (let i = 0; i <= ticks; i++) {
    const pointIndex = Math.round((i / Math.max(1, ticks)) * (pointCount - 1));
    const y = ((pointIndex + 0.5) / pointCount) * heatmapHeight;
    yCtx.beginPath();
    yCtx.moveTo(AXIS_WIDTH - 5, y);
    yCtx.lineTo(AXIS_WIDTH, y);
    yCtx.strokeStyle = '#111827';
    yCtx.stroke();
    yCtx.fillText(String(pointIndex), AXIS_WIDTH - 8, y);
  }
}

function getFrameIndexFromMouse(e: MouseEvent): { frame: number; pointIndex: number } | null {
  if (!canvas.value || !container.value || !props.meta) {
    return null;
  }

  const rect = canvas.value.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;
  const usableHeight = Math.max(1, container.value.clientHeight - AXIS_HEIGHT);

  const frameFloat = (mouseX - offsetX.value) / Math.max(scale.value, 1e-9);
  const pointFloat = (mouseY / usableHeight) * props.meta.height;
  const frame = Math.floor(frameFloat);
  const pointIndex = Math.floor(pointFloat);

  if (
    frame < 0 ||
    frame >= props.meta.width ||
    pointIndex < 0 ||
    pointIndex >= props.meta.height
  ) {
    return null;
  }

  return { frame, pointIndex };
}

function onCanvasMove(e: MouseEvent) {
  if (isDragging) {
    clearHover();
    return;
  }

  if (!props.meta || !props.diffMm || !props.leftAlignedMm || !props.rightAlignedMm) {
    clearHover();
    return;
  }

  const result = getFrameIndexFromMouse(e);
  if (!result) {
    clearHover();
    return;
  }

  const index = result.frame * props.meta.height + result.pointIndex;
  hoverInfo.value = {
    leftMm: props.leftAlignedMm[index] ?? 0,
    rightMm: props.rightAlignedMm[index] ?? 0,
    diffMm: props.diffMm[index] ?? 0,
    syncedTimeSec: props.meta.minTimeSec + result.frame / props.meta.fps,
  };
  mousePos.value = { x: e.clientX, y: e.clientY };
}

function onCanvasLeave() {
  clearHover();
}

function onCanvasClick(e: MouseEvent) {
  const result = getFrameIndexFromMouse(e);
  if (!result) {
    return;
  }
  emit('frame-click', result.frame, result.pointIndex);
}

let isDragging = false;
let lastMouseX = 0;
let movedDuringDrag = false;

function onMouseDown(e: MouseEvent) {
  isDragging = true;
  movedDuringDrag = false;
  lastMouseX = e.clientX;
  window.addEventListener('mousemove', onMouseMoveDrag);
  window.addEventListener('mouseup', onMouseUp);
}

function onMouseMoveDrag(e: MouseEvent) {
  if (!isDragging || !container.value || !props.meta) {
    return;
  }
  const deltaX = e.clientX - lastMouseX;
  lastMouseX = e.clientX;
  if (Math.abs(deltaX) > 0) {
    movedDuringDrag = true;
  }
  offsetX.value += deltaX;

  const width = props.meta.width;
  const viewportWidth = Math.max(1, container.value.clientWidth - AXIS_WIDTH);
  const scaledWidth = width * scale.value;
  if (scaledWidth <= viewportWidth) {
    offsetX.value = 0;
  } else {
    const minOffset = viewportWidth - scaledWidth;
    if (offsetX.value > 0) offsetX.value = 0;
    if (offsetX.value < minOffset) offsetX.value = minOffset;
  }
}

function onMouseUp() {
  isDragging = false;
  setTimeout(() => {
    movedDuringDrag = false;
  }, 10);
  window.removeEventListener('mousemove', onMouseMoveDrag);
  window.removeEventListener('mouseup', onMouseUp);
}

function onWheel(e: WheelEvent) {
  if (!props.meta || !container.value || !canvas.value) {
    return;
  }

  const oldScale = scale.value;
  const zoomFactor = e.deltaY < 0 ? 1.1 : 0.9;
  scale.value *= zoomFactor;

  const viewportWidth = Math.max(1, container.value.clientWidth - AXIS_WIDTH);
  const minScale = viewportWidth / Math.max(1, props.meta.width);
  const maxScale = 12;
  if (scale.value < minScale) scale.value = minScale;
  if (scale.value > maxScale) scale.value = maxScale;

  const rect = canvas.value.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const zoomPoint = (mouseX - offsetX.value) / oldScale;
  offsetX.value = mouseX - zoomPoint * scale.value;

  const scaledWidth = props.meta.width * scale.value;
  if (scaledWidth <= viewportWidth) {
    offsetX.value = 0;
  } else {
    const minOffset = viewportWidth - scaledWidth;
    if (offsetX.value > 0) offsetX.value = 0;
    if (offsetX.value < minOffset) offsetX.value = minOffset;
  }
}

function setupResizeObserver() {
  if (!container.value) {
    return;
  }
  resizeObserver.value = new ResizeObserver(() => {
    if (props.meta) {
      const viewportWidth = Math.max(1, container.value!.clientWidth - AXIS_WIDTH);
      const minScale = viewportWidth / Math.max(1, props.meta.width);
      if (scale.value < minScale) {
        scale.value = minScale;
        offsetX.value = 0;
      }
    }
    renderHeatmap();
    renderAxes();
  });
  resizeObserver.value.observe(container.value);
}

onMounted(() => {
  setupResizeObserver();
});

onUnmounted(() => {
  if (resizeObserver.value) {
    resizeObserver.value.disconnect();
  }
  window.removeEventListener('mousemove', onMouseMoveDrag);
  window.removeEventListener('mouseup', onMouseUp);
});

watch(
  () => [props.meta, props.diffMm, props.leftAlignedMm, props.rightAlignedMm, currentFrame.value],
  () => {
    if (props.meta) {
      const viewportWidth = Math.max(1, (container.value?.clientWidth ?? 1) - AXIS_WIDTH);
      const minScale = viewportWidth / Math.max(1, props.meta.width);
      if (scale.value < minScale) {
        scale.value = minScale;
      }
    }
    renderHeatmap();
    renderAxes();
  },
  { deep: true }
);

watch(
  () => props.meta?.width,
  () => {
    if (props.meta) {
      calculateInitialScale();
      renderHeatmap();
      renderAxes();
    }
  }
);
</script>

<template>
  <div
    ref="container"
    class="heatmap-diff-container"
    @wheel.prevent="onWheel"
    @mousedown.prevent="onMouseDown"
  >
    <div v-if="isLoading" class="state loading">Computing diff heatmap...</div>
    <div v-else-if="error" class="state error">{{ error }}</div>
    <div v-else-if="!meta || !diffMm || !leftAlignedMm || !rightAlignedMm" class="state empty">
      No diff data available.
    </div>
    <div v-else class="heatmap-wrapper">
      <div class="y-axis-wrapper">
        <canvas ref="yAxisCanvas" class="y-axis-canvas" />
        <div class="axis-corner" />
      </div>
      <div class="heatmap-canvas-wrapper">
        <canvas
          ref="canvas"
          class="heatmap-canvas"
          @mousemove="onCanvasMove"
          @mouseleave="onCanvasLeave"
          @click="(event) => { if (!movedDuringDrag) onCanvasClick(event) }"
        />
        <canvas ref="xAxisCanvas" class="x-axis-canvas" />
      </div>
    </div>

    <div v-if="hoverInfo && !isLoading && !error" class="tooltip" :style="tooltipStyle">
      Time: {{ formatTimestamp(hoverInfo.syncedTimeSec) }}<br />
      Left: {{ hoverInfo.leftMm.toFixed(3) }} mm<br />
      Right: {{ hoverInfo.rightMm.toFixed(3) }} mm<br />
      Diff: {{ hoverInfo.diffMm > 0 ? '+' : '' }}{{ hoverInfo.diffMm.toFixed(3) }} mm
    </div>
  </div>
</template>

<style scoped>
.heatmap-diff-container {
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
}

.y-axis-wrapper {
  display: flex;
  flex-direction: column;
  width: 60px;
  flex-shrink: 0;
}

.y-axis-canvas {
  flex: 1;
  width: 60px;
  border-right: 1px solid var(--border-light);
  background: var(--bg-secondary);
}

.axis-corner {
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
}

.heatmap-canvas {
  flex: 1;
  display: block;
  width: 100%;
  cursor: crosshair;
}

.x-axis-canvas {
  width: 100%;
  height: 30px;
  border-top: 1px solid var(--border-light);
  background: var(--bg-secondary);
  flex-shrink: 0;
}

.state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  text-align: center;
  color: var(--text-secondary);
  padding: 1rem;
}

.state.error {
  color: var(--color-error-600);
  background: var(--color-error-100);
}

.tooltip {
  position: fixed;
  z-index: 1000;
  pointer-events: none;
  background: rgba(0, 0, 0, 0.85);
  color: #fff;
  font-size: 12px;
  border-radius: 4px;
  padding: 8px 12px;
  white-space: pre-line;
}
</style>

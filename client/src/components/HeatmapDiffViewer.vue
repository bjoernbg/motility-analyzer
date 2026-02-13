<template>
  <div
    ref="container"
    :class="['heatmap-container', { compact: compact }]"
    @wheel.prevent="onWheel"
    @mousedown.prevent="onMouseDown"
  >
    <div v-if="isLoading" class="loading-state">
      Loading heatmap diff data...
    </div>
    <div v-else-if="error" class="error-state">
      {{ error }}
    </div>
    <div v-else-if="!meta || !data || meta.width === 0 || meta.height === 0" class="no-data-state">
      No heatmap diff data available.
    </div>
    <div v-else class="heatmap-wrapper">
      <!-- Y-axis labels (left side) -->
      <div v-if="!compact" class="y-axis-wrapper">
        <canvas ref="yAxisCanvas" class="y-axis-canvas"></canvas>
        <div class="axis-corner"></div>
      </div>
      <!-- Main heatmap canvas -->
      <div class="heatmap-canvas-wrapper">
        <canvas ref="canvas" class="heatmap-canvas"></canvas>
        <!-- X-axis labels (bottom) -->
        <canvas v-if="!compact" ref="xAxisCanvas" class="x-axis-canvas"></canvas>
      </div>
    </div>
    <div v-if="hoverInfo && !isLoading && !error && !compact" class="tooltip" :style="tooltipStyle">
      Frame: {{ hoverInfo.frame }}<br />
      Time: {{ hoverInfo.time.toFixed(2) }}s<br />
      Point: {{ hoverInfo.index }}<br />
      Difference: {{ hoverInfo.value.toFixed(3) }} px
    </div>
    <div v-if="!isLoading && !error && !compact" class="color-scale-info">
      <div class="color-scale-label">Diverging Color Scale:</div>
      <div class="color-scale-range">
        <span class="color-indicator blue"></span>
        <span>Negative (Analysis 2 > Analysis 1)</span>
        <span class="color-indicator white"></span>
        <span>Zero</span>
        <span class="color-indicator red"></span>
        <span>Positive (Analysis 1 > Analysis 2)</span>
      </div>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed } from "vue";
import { getHeatmapDiffMetadata, getHeatmapDiffRaw, type HeatmapMeta } from "../lib/api";
import { useAnalysisStore } from "../stores/analysis";

const props = defineProps<{
  combinedAnalysisId: string;
  currentFrame?: number | null;
  compact?: boolean;
  showContractionOverlays?: boolean;
}>();

const emit = defineEmits<{
  frameClick: [frame: number, pointIndex: number];
}>();

const store = useAnalysisStore();

const container = ref<HTMLDivElement | null>(null);
const canvas = ref<HTMLCanvasElement | null>(null);
const xAxisCanvas = ref<HTMLCanvasElement | null>(null);
const yAxisCanvas = ref<HTMLCanvasElement | null>(null);

const isLoading = ref(true);
const error = ref<string | null>(null);
const meta = ref<HeatmapMeta | null>(null);
const data = ref<Float32Array | null>(null);

// Viewport state (for panning/zooming)
const offsetX = ref(0);
const offsetY = ref(0);
const scale = ref(1);

// Hover state
const hoverInfo = ref<{
  frame: number;
  index: number;
  time: number;
  value: number;
  x: number;
  y: number;
} | null>(null);

const tooltipStyle = computed(() => {
  if (!hoverInfo.value) return {};
  return {
    left: `${hoverInfo.value.x + 10}px`,
    top: `${hoverInfo.value.y + 10}px`,
  };
});

/**
 * Convert value to diverging color (red for positive, blue for negative, white for zero)
 */
function getDivergingColor(value: number, min: number, max: number): string {
  // Calculate the absolute maximum for symmetric scaling
  const absMax = Math.max(Math.abs(min), Math.abs(max));

  if (absMax === 0) {
    return 'rgb(255, 255, 255)'; // All white if no variation
  }

  // Normalize to [-1, 1] range
  const normalized = value / absMax;

  if (normalized > 0) {
    // Positive: white (1,1,1) to red (1,0,0)
    const intensity = Math.min(normalized, 1);
    const r = 255;
    const g = Math.round(255 * (1 - intensity));
    const b = Math.round(255 * (1 - intensity));
    return `rgb(${r}, ${g}, ${b})`;
  } else {
    // Negative: white (1,1,1) to blue (0,0,1)
    const intensity = Math.min(Math.abs(normalized), 1);
    const r = Math.round(255 * (1 - intensity));
    const g = Math.round(255 * (1 - intensity));
    const b = 255;
    return `rgb(${r}, ${g}, ${b})`;
  }
}

async function loadHeatmapData() {
  isLoading.value = true;
  error.value = null;

  try {
    // Fetch metadata and raw data in parallel
    const [metaData, rawData] = await Promise.all([
      getHeatmapDiffMetadata(props.combinedAnalysisId),
      getHeatmapDiffRaw(props.combinedAnalysisId)
    ]);

    meta.value = metaData;
    data.value = rawData;

    // Draw the heatmap
    drawHeatmap();
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load heatmap diff data';
    console.error('Failed to load heatmap diff:', err);
  } finally {
    isLoading.value = false;
  }
}

function drawHeatmap() {
  if (!canvas.value || !meta.value || !data.value) return;

  const ctx = canvas.value.getContext('2d');
  if (!ctx) return;

  const width = meta.value.width;
  const height = meta.value.height;
  const minVal = meta.value.min;
  const maxVal = meta.value.max;

  // Set canvas size
  canvas.value.width = width;
  canvas.value.height = height;

  // Create image data
  const imageData = ctx.createImageData(width, height);

  for (let frame = 0; frame < width; frame++) {
    for (let point = 0; point < height; point++) {
      const dataIndex = frame * height + point;
      const value = data.value[dataIndex] ?? 0;

      const color = getDivergingColor(value, minVal, maxVal);
      const matches = color.match(/\d+/g);
      if (!matches || matches.length < 3) continue;
      const rgbValues = matches.map(Number);
      const r = rgbValues[0] ?? 0;
      const g = rgbValues[1] ?? 0;
      const b = rgbValues[2] ?? 0;

      const pixelIndex = (point * width + frame) * 4;
      imageData.data[pixelIndex] = r;
      imageData.data[pixelIndex + 1] = g;
      imageData.data[pixelIndex + 2] = b;
      imageData.data[pixelIndex + 3] = 255; // Alpha
    }
  }

  ctx.putImageData(imageData, 0, 0);

  // Draw current frame indicator
  if (props.currentFrame !== null && props.currentFrame !== undefined) {
    drawFrameIndicator(ctx, props.currentFrame, width, height);
  }

  // Draw axes
  if (!props.compact) {
    drawAxes();
  }
}

function drawFrameIndicator(ctx: CanvasRenderingContext2D, frame: number, width: number, height: number) {
  if (frame < 0 || frame >= width) return;

  ctx.strokeStyle = 'rgba(255, 255, 0, 0.8)';
  ctx.lineWidth = 2;
  ctx.beginPath();
  ctx.moveTo(frame + 0.5, 0);
  ctx.lineTo(frame + 0.5, height);
  ctx.stroke();
}

function drawAxes() {
  if (!meta.value) return;

  drawXAxis();
  drawYAxis();
}

function drawXAxis() {
  if (!xAxisCanvas.value || !meta.value) return;

  const ctx = xAxisCanvas.value.getContext('2d');
  if (!ctx) return;

  const width = meta.value.width;
  const height = 30; // Axis height

  xAxisCanvas.value.width = width;
  xAxisCanvas.value.height = height;

  ctx.fillStyle = '#f3f4f6';
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = '#d1d5db';
  ctx.beginPath();
  ctx.moveTo(0, 0);
  ctx.lineTo(width, 0);
  ctx.stroke();

  ctx.fillStyle = '#374151';
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'center';

  const step = Math.max(Math.floor(width / 10), 1);
  for (let frame = 0; frame < width; frame += step) {
    ctx.fillText(frame.toString(), frame, 15);
  }
}

function drawYAxis() {
  if (!yAxisCanvas.value || !meta.value) return;

  const ctx = yAxisCanvas.value.getContext('2d');
  if (!ctx) return;

  const width = 40; // Axis width
  const height = meta.value.height;

  yAxisCanvas.value.width = width;
  yAxisCanvas.value.height = height;

  ctx.fillStyle = '#f3f4f6';
  ctx.fillRect(0, 0, width, height);

  ctx.strokeStyle = '#d1d5db';
  ctx.beginPath();
  ctx.moveTo(width - 1, 0);
  ctx.lineTo(width - 1, height);
  ctx.stroke();

  ctx.fillStyle = '#374151';
  ctx.font = '10px sans-serif';
  ctx.textAlign = 'right';
  ctx.textBaseline = 'middle';

  const step = Math.max(Math.floor(height / 10), 1);
  for (let point = 0; point < height; point += step) {
    ctx.fillText(point.toString(), width - 5, point);
  }
}

function onWheel(event: WheelEvent) {
  // Zoom functionality (optional)
  const delta = event.deltaY > 0 ? 0.9 : 1.1;
  scale.value = Math.max(0.5, Math.min(scale.value * delta, 5));
  drawHeatmap();
}

function onMouseDown(event: MouseEvent) {
  // Handle click to seek
  if (!canvas.value || !meta.value) return;

  const rect = canvas.value.getBoundingClientRect();
  const x = event.clientX - rect.left;
  const y = event.clientY - rect.top;

  const frame = Math.floor(x * (meta.value.width / canvas.value.clientWidth));
  const pointIndex = Math.floor(y * (meta.value.height / canvas.value.clientHeight));

  if (frame >= 0 && frame < meta.value.width && pointIndex >= 0 && pointIndex < meta.value.height) {
    emit('frameClick', frame, pointIndex);
  }
}

// Watch for prop changes
watch(() => props.combinedAnalysisId, () => {
  loadHeatmapData();
}, { immediate: true });

watch(() => props.currentFrame, () => {
  drawHeatmap();
});

onMounted(() => {
  loadHeatmapData();
});
</script>

<style scoped>
.heatmap-container {
  position: relative;
  width: 100%;
  height: 100%;
  min-height: 400px;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
  border-radius: 4px;
  overflow: hidden;
}

.heatmap-container.compact {
  min-height: 200px;
}

.loading-state,
.error-state,
.no-data-state {
  display: flex;
  align-items: center;
  justify-content: center;
  height: 100%;
  color: var(--text-secondary);
  font-style: italic;
}

.error-state {
  color: var(--color-error-600);
}

.heatmap-wrapper {
  display: flex;
  width: 100%;
  height: 100%;
}

.y-axis-wrapper {
  display: flex;
  flex-direction: column;
  flex-shrink: 0;
}

.y-axis-canvas {
  width: 40px;
  flex: 1;
}

.axis-corner {
  width: 40px;
  height: 30px;
  background: #f3f4f6;
  border-top: 1px solid #d1d5db;
}

.heatmap-canvas-wrapper {
  flex: 1;
  display: flex;
  flex-direction: column;
  overflow: hidden;
}

.heatmap-canvas {
  width: 100%;
  flex: 1;
  cursor: crosshair;
  image-rendering: pixelated;
}

.x-axis-canvas {
  width: 100%;
  height: 30px;
  flex-shrink: 0;
}

.tooltip {
  position: absolute;
  background: rgba(0, 0, 0, 0.8);
  color: white;
  padding: 0.5rem;
  border-radius: 4px;
  font-size: 0.75rem;
  pointer-events: none;
  z-index: 100;
  white-space: nowrap;
}

.color-scale-info {
  position: absolute;
  bottom: 0.5rem;
  right: 0.5rem;
  background: rgba(255, 255, 255, 0.95);
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 0.5rem;
  font-size: 0.75rem;
  z-index: 10;
}

.color-scale-label {
  font-weight: 600;
  margin-bottom: 0.25rem;
}

.color-scale-range {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  flex-wrap: wrap;
}

.color-indicator {
  display: inline-block;
  width: 12px;
  height: 12px;
  border: 1px solid #ccc;
  border-radius: 2px;
}

.color-indicator.red {
  background: rgb(255, 0, 0);
}

.color-indicator.blue {
  background: rgb(0, 0, 255);
}

.color-indicator.white {
  background: rgb(255, 255, 255);
}
</style>

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
        <canvas ref="canvas" class="heatmap-canvas"></canvas>
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
import { ref, onMounted, onUnmounted, watch, computed } from "vue";
import { getHeatmapMeta, getHeatmapRaw, type HeatmapMeta } from "../lib/api";
import { useHeatmapCache } from "../composables/useHeatmapCache";
import { useAnalysisStore } from "../stores/analysis";
import { PIXEL_TO_MM_FACTOR, HEATMAP_MIN_MM, HEATMAP_MAX_MM } from "../lib/constants";
import { createColormap } from "../lib/colormap";

const props = defineProps<{
  analysisId: string;
  currentFrame?: number | null;
  compact?: boolean;
  showContractionOverlays?: boolean;
  heatmapMinMmOverride?: number | null;
  heatmapMaxMmOverride?: number | null;
}>();

const store = useAnalysisStore();

const emit = defineEmits<{
  'frame-click': [frame: number, pointIndex: number];
}>();

const canvas = ref<HTMLCanvasElement | null>(null);
const xAxisCanvas = ref<HTMLCanvasElement | null>(null);
const yAxisCanvas = ref<HTMLCanvasElement | null>(null);
const container = ref<HTMLDivElement | null>(null);

const meta = ref<HeatmapMeta | null>(null);
const data = ref<Float32Array | null>(null); // flattened [frame0 idx0..idxN, frame1 ...]

// Heatmap cache for instant analysis switching
const heatmapCache = useHeatmapCache();

// Loading and error states
const isLoading = ref(true);
const error = ref<string | null>(null);

// View transform
const scale = ref(1); // visual zoom factor (pixels per data cell) - will be calculated initially
const offsetX = ref(0);
const offsetY = ref(0);

// Hover info
const hoverInfo = ref<{ time: number; valueMm: number } | null>(null);
const mousePos = ref<{ x: number; y: number } | null>(null);

// Computed display settings from meta or fallback to constants
const pixelToMmFactor = computed(() => meta.value?.display_settings?.pixel_to_mm_factor ?? PIXEL_TO_MM_FACTOR);
const heatmapMinMm = computed(
  () =>
    props.heatmapMinMmOverride ??
    meta.value?.display_settings?.heatmap_min_mm ??
    HEATMAP_MIN_MM
);
const heatmapMaxMm = computed(
  () =>
    props.heatmapMaxMmOverride ??
    meta.value?.display_settings?.heatmap_max_mm ??
    HEATMAP_MAX_MM
);

// Live refresh during processing
const refreshTimer = ref<ReturnType<typeof setInterval> | null>(null);
const isRefreshing = ref(false);
const isAnalysisProcessing = computed(
  () => store.currentAnalysis?.id === props.analysisId && store.progressStatus === 'processing'
);

// Derived constants from display settings
const MIN_PX = computed(() => heatmapMinMm.value * pixelToMmFactor.value);
const MAX_PX = computed(() => heatmapMaxMm.value * pixelToMmFactor.value);

const tooltipStyle = computed(() => {
  if (!mousePos.value) return {};
  return {
    left: mousePos.value.x + 10 + "px",
    top: mousePos.value.y + 10 + "px",
  };
});

// Axis dimensions
const AXIS_WIDTH = 60;
const AXIS_HEIGHT = 30;

onMounted(async () => {
  await loadData();
  renderHeatmap();
  renderAxes();
  setupMouseMove();
  setupResizeObserver();
  // Start live refresh if analysis is already processing
  if (isAnalysisProcessing.value) {
    startLiveRefresh();
  }
});

onUnmounted(() => {
  stopLiveRefresh();
  cleanupMouseMove();
  if (resizeObserver.value) {
    resizeObserver.value.disconnect();
  }
});

watch([meta, data, scale, offsetX, () => props.currentFrame], () => {
  renderHeatmap();
  if (!props.compact) {
    renderAxes();
  }
});

watch(
  () => [props.heatmapMinMmOverride, props.heatmapMaxMmOverride],
  () => {
    if (meta.value && data.value) {
      renderHeatmap();
    }
  }
);

// Recalculate initial scale when container resizes
watch(() => container.value?.clientWidth, () => {
  if (meta.value && data.value) {
    calculateInitialScale();
  }
});

// Reload data when analysisId changes - properly handle async
watch(() => props.analysisId, async (newId, oldId) => {
  if (newId !== oldId) {
    // Clear current data immediately to show loading state
    meta.value = null;
    data.value = null;
    await loadData();
  }
}, { immediate: false });

// Re-render when contraction overlays toggle or contraction events change
watch(() => [props.showContractionOverlays, store.contractionEvents], () => {
  if (meta.value && data.value) {
    renderHeatmap();
  }
}, { deep: true });

// Watch for display settings changes and re-render
watch(() => meta.value?.display_settings, () => {
  if (meta.value && data.value) {
    renderHeatmap();
  }
}, { deep: true });

// Watch for processing state changes to start/stop live refresh
watch(isAnalysisProcessing, (processing, wasProcessing) => {
  if (processing) {
    startLiveRefresh();
  } else if (wasProcessing) {
    // Transitioned from processing to terminal state
    stopLiveRefresh();
    heatmapCache.invalidate(props.analysisId);
    // Do a final full load to cache the complete data
    loadData();
  }
});

const resizeObserver = ref<ResizeObserver | null>(null);

function setupResizeObserver() {
  if (!container.value) return;
  
    resizeObserver.value = new ResizeObserver(() => {
      // Recalculate scale if needed to maintain fit-to-width behavior
      if (meta.value && data.value && container.value) {
        const axisWidth = props.compact ? 0 : AXIS_WIDTH;
        const containerWidth = container.value.clientWidth - axisWidth;
        // Use expected total frames (same logic as calculateInitialScale) for min scale check
        const videoMeta = store.currentVideo?.metadata;
        const expectedTotalFrames = videoMeta
          ? Math.floor(videoMeta.total_frames / (videoMeta.frame_multiplier ?? 1))
          : 0;
        const dataWidth = (expectedTotalFrames > meta.value.width)
          ? expectedTotalFrames
          : meta.value.width;
        const minScale = containerWidth / dataWidth;

        // If zoomed out beyond fit-to-width, adjust to new container size
        if (scale.value <= minScale * 1.01) {
          calculateInitialScale();
        }
      }
      renderHeatmap();
      renderAxes();
    });
  
  resizeObserver.value.observe(container.value);
}

async function loadData(skipCache = false) {
  const analysisId = props.analysisId;

  try {
    // Don't show loading spinner for background refreshes
    if (!skipCache) {
      isLoading.value = true;
    }
    error.value = null;

    // Check client-side cache first for instant switching (skip during live refresh)
    if (!skipCache) {
      const cached = heatmapCache.getCached(analysisId);
      if (cached) {
        meta.value = cached.meta;
        data.value = cached.data;
        isLoading.value = false;

        // Calculate scale after setting data
        await new Promise(resolve => setTimeout(resolve, 0));
        calculateInitialScale();
        return;
      }
    }

    // 1. Fetch meta (for fps, display_settings, min/max)
    const metaResp = await getHeatmapMeta(analysisId);

    // Check if analysis ID changed during fetch (user switched again)
    if (props.analysisId !== analysisId) {
      return; // Abort, another load is in progress
    }

    // Check if we have data
    if (metaResp.width === 0 || metaResp.height === 0) {
      // During live refresh, don't set error or update meta - keep showing current partial heatmap
      if (!skipCache) {
        meta.value = metaResp;
        error.value = "No heatmap data available. The analysis may not have measurement point pairs (mpp) data.";
        isLoading.value = false;
      }
      return;
    }

    // 2. Fetch raw data (returns authoritative dimensions in headers)
    const rawResult = await getHeatmapRaw(analysisId);

    // Check if analysis ID changed during fetch
    if (props.analysisId !== analysisId) {
      return; // Abort, another load is in progress
    }

    // Use Float32Array directly from binary response (zero-copy view)
    const dataArray = new Float32Array(rawResult.buffer);

    // Use dimensions from raw response headers (authoritative, avoids race with meta)
    const actualWidth = rawResult.width;
    const actualHeight = rawResult.height;

    if (actualWidth === 0 || actualHeight === 0) {
      if (!skipCache) {
        meta.value = metaResp;
        error.value = "No heatmap data available.";
        isLoading.value = false;
      }
      return;
    }

    // Verify data size matches the raw response's own dimensions
    const expectedSize = actualWidth * actualHeight;
    if (dataArray.length !== expectedSize) {
      throw new Error(`Data size mismatch: expected ${expectedSize}, got ${dataArray.length}`);
    }

    // Update meta with authoritative width from raw response (may differ during processing)
    const resolvedMeta: HeatmapMeta = { ...metaResp, width: actualWidth, height: actualHeight };

    // Store in cache for future instant access (skip during live refresh to avoid caching partial data)
    if (!skipCache) {
      heatmapCache.setCache(analysisId, resolvedMeta, dataArray);
    }

    // Track whether this is the first time we're getting data
    const hadNoData = !data.value;

    // Update refs
    meta.value = resolvedMeta;
    data.value = dataArray;

    // Calculate initial scale on first load, or when data first arrives during live refresh
    // (skip subsequent live refreshes to preserve user zoom/pan)
    if (!skipCache || hadNoData) {
      await new Promise(resolve => setTimeout(resolve, 0));
      calculateInitialScale();
    }
  } catch (err) {
    // Don't set error if request was aborted (e.g., user switched analyses)
    if (err instanceof Error && err.name === 'AbortError') {
      // Silently ignore abort errors - they're expected when switching analyses
      return;
    }

    // Only set error if we're still loading this analysis (and not a background refresh)
    if (props.analysisId === analysisId && !skipCache) {
      error.value = err instanceof Error ? err.message : "Failed to load heatmap data";
      console.error("Failed to load heatmap data:", err);
    }
  } finally {
    // Only clear loading if we're still on this analysis
    if (props.analysisId === analysisId) {
      isLoading.value = false;
    }
  }
}

function startLiveRefresh() {
  if (refreshTimer.value) return; // Already running
  refreshTimer.value = setInterval(async () => {
    if (isRefreshing.value) return; // Skip if previous refresh still in progress
    isRefreshing.value = true;
    try {
      await loadData(true);
    } finally {
      isRefreshing.value = false;
    }
  }, 5000);
}

function stopLiveRefresh() {
  if (refreshTimer.value) {
    clearInterval(refreshTimer.value);
    refreshTimer.value = null;
  }
  isRefreshing.value = false;
}

function calculateInitialScale() {
  if (!container.value || !meta.value) return;

  const axisWidth = props.compact ? 0 : AXIS_WIDTH;
  const containerWidth = container.value.clientWidth - axisWidth;

  // Calculate expected total frames from video metadata (accounting for frame multiplier)
  const videoMeta = store.currentVideo?.metadata;
  const expectedTotalFrames = videoMeta
    ? Math.floor(videoMeta.total_frames / (videoMeta.frame_multiplier ?? 1))
    : 0;

  // When data is partial (fewer frames than expected), use total expected width
  // so the heatmap builds up from the left instead of stretching to fill the container
  const dataWidth = (expectedTotalFrames > meta.value.width)
    ? expectedTotalFrames
    : meta.value.width;

  if (containerWidth > 0 && dataWidth > 0) {
    // Calculate scale so entire width fits: containerWidth = dataWidth * scale
    // Allow fractional scale when there's more data than pixels
    scale.value = containerWidth / dataWidth;

    // Reset offset
    offsetX.value = 0;
    offsetY.value = 0;
  }
}

const colormap = createColormap();

function renderHeatmap() {
  if (!canvas.value || !meta.value || !data.value || !container.value) return;

  const ctx = canvas.value.getContext("2d");
  if (!ctx) return;
  
  // Get container dimensions first
  const axisWidth = props.compact ? 0 : AXIS_WIDTH;
  const axisHeight = props.compact ? 0 : AXIS_HEIGHT;
  const containerWidth = Math.max(1, container.value.clientWidth - axisWidth);
  const containerHeight = Math.max(1, container.value.clientHeight - axisHeight);

  const { width, height } = meta.value;
  const values = data.value;

  // We create an offscreen canvas at data resolution
  const offCanvas = document.createElement("canvas");
  offCanvas.width = width;
  offCanvas.height = height;

  const offCtx = offCanvas.getContext("2d");
  if (!offCtx) return;

  const imageData = offCtx.createImageData(width, height);
  const pixels = imageData.data; // Uint8ClampedArray

  // Fixed scale: Red = heatmapMinMm, Violet = heatmapMaxMm
  // Convert pixel distances to mm and map to fixed scale
  const mmRange = Math.max(1e-9, heatmapMaxMm.value - heatmapMinMm.value);

  // Note: We'll treat x = frame, y = index
  // Flatten index = x * height + y (because values are [frame][index])
  for (let x = 0; x < width; x++) {
    for (let y = 0; y < height; y++) {
      const dataIndex = x * height + y;
      const vPx = values[dataIndex] ?? 0; // value in pixels

      // Convert to mm
      const vMm = vPx / pixelToMmFactor.value;

      // Map to fixed scale
      // Clamp values outside the range
      let t = (vMm - heatmapMinMm.value) / mmRange;
      if (t < 0) t = 0; // Values < HEATMAP_MIN_MM map to red
      if (t > 1) t = 1; // Values > HEATMAP_MAX_MM map to violet
      const ci = Math.floor(t * 255);

      const r = colormap[ci * 3 + 0] ?? 0;
      const g = colormap[ci * 3 + 1] ?? 0;
      const b = colormap[ci * 3 + 2] ?? 0;

      // ImageData is row-major: (y * width + x) * 4
      const pixelIndex = (y * width + x) * 4;
      pixels[pixelIndex + 0] = r;
      pixels[pixelIndex + 1] = g;
      pixels[pixelIndex + 2] = b;
      pixels[pixelIndex + 3] = 255;
    }
  }

  offCtx.putImageData(imageData, 0, 0);

  // Set canvas display size (CSS pixels) - always constrain to container
  canvas.value.style.width = `${containerWidth}px`;
  canvas.value.style.height = `${containerHeight}px`;
  
  // Set canvas internal resolution (device pixels for crisp rendering)
  const dpr = window.devicePixelRatio || 1;
  const internalWidth = containerWidth * dpr;
  const internalHeight = containerHeight * dpr;
  
  // Only resize if dimensions changed to avoid unnecessary redraws
  if (canvas.value.width !== internalWidth || canvas.value.height !== internalHeight) {
    canvas.value.width = internalWidth;
    canvas.value.height = internalHeight;
  }
  
  // Reset transform and scale context to match device pixel ratio
  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  
  ctx.clearRect(0, 0, containerWidth, containerHeight);

  // Calculate the scaled size of the data (for drawing)
  // X-axis uses scale, Y-axis always fits to container height
  const scaledDataWidth = width * scale.value;
  const scaledDataHeight = containerHeight; // Always fit height to container

  ctx.save();
  ctx.translate(offsetX.value, 0); // No y-offset, always show full height
  ctx.imageSmoothingEnabled = false; // keep pixel crispness
  // Draw the offscreen canvas at the scaled size
  ctx.drawImage(offCanvas, 0, 0, scaledDataWidth, scaledDataHeight);
  
  // Draw contraction event overlays if enabled
  if (props.showContractionOverlays && store.contractionEvents.length > 0 && meta.value) {
    const fps = meta.value.fps;
    const numPoints = meta.value.height;
    
    for (const event of store.contractionEvents) {
      const [tStart, tEnd] = event.t_range_frames;
      const [yStart, yEnd] = event.y_range_idx;
      
      // Calculate positions in canvas coordinates
      const xStart = tStart * scale.value;
      const xEnd = tEnd * scale.value;
      const yStartPx = (yStart / numPoints) * scaledDataHeight;
      const yEndPx = (yEnd / numPoints) * scaledDataHeight;
      
      // Draw bounding box
      ctx.strokeStyle = 'rgba(255, 255, 0, 0.8)';
      ctx.lineWidth = 2;
      ctx.setLineDash([]);
      ctx.strokeRect(xStart, yStartPx, xEnd - xStart, yEndPx - yStartPx);
      
      // Draw fitted line
      const { a_idx_per_frame, b } = event.line_fit;
      ctx.strokeStyle = 'rgba(255, 0, 0, 0.8)';
      ctx.lineWidth = 2;
      ctx.beginPath();
      
      // Calculate line endpoints
      const yAtStart = a_idx_per_frame * tStart + b;
      const yAtEnd = a_idx_per_frame * tEnd + b;
      
      const yAtStartPx = (yAtStart / numPoints) * scaledDataHeight;
      const yAtEndPx = (yAtEnd / numPoints) * scaledDataHeight;
      
      ctx.moveTo(xStart, yAtStartPx);
      ctx.lineTo(xEnd, yAtEndPx);
      ctx.stroke();
      
      // Draw direction arrow
      const arrowLength = 20;
      const arrowX = xEnd;
      const arrowY = yAtEndPx;
      const angle = Math.atan2(yAtEndPx - yAtStartPx, xEnd - xStart);
      
      ctx.beginPath();
      ctx.moveTo(arrowX, arrowY);
      ctx.lineTo(
        arrowX - arrowLength * Math.cos(angle - Math.PI / 6),
        arrowY - arrowLength * Math.sin(angle - Math.PI / 6)
      );
      ctx.moveTo(arrowX, arrowY);
      ctx.lineTo(
        arrowX - arrowLength * Math.cos(angle + Math.PI / 6),
        arrowY - arrowLength * Math.sin(angle + Math.PI / 6)
      );
      ctx.stroke();
    }
  }
  
  // Draw current frame marker if provided
  if (props.currentFrame !== null && props.currentFrame !== undefined && props.currentFrame >= 0 && props.currentFrame < width) {
    const frameX = props.currentFrame * scale.value;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = 2;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(frameX, 0);
    ctx.lineTo(frameX, containerHeight);
    ctx.stroke();
    ctx.setLineDash([]);
  }
  
  ctx.restore();
}

function renderAxes() {
  if (props.compact) return; // Skip axes in compact mode
  if (!meta.value || !xAxisCanvas.value || !yAxisCanvas.value || !canvas.value || !container.value) return;

  const { width, height, fps } = meta.value;
  const xCtx = xAxisCanvas.value.getContext("2d");
  const yCtx = yAxisCanvas.value.getContext("2d");
  if (!xCtx || !yCtx) return;

  // Resize axis canvases to match the display size (CSS pixels)
  const axisWidth = props.compact ? 0 : AXIS_WIDTH;
  const axisHeight = props.compact ? 0 : AXIS_HEIGHT;
  const heatmapWidth = container.value.clientWidth - axisWidth;
  const heatmapHeight = container.value.clientHeight - axisHeight;

  // X-axis (bottom) - use display size
  const dpr = window.devicePixelRatio || 1;
  xAxisCanvas.value.style.width = `${heatmapWidth}px`;
  xAxisCanvas.value.style.height = `${AXIS_HEIGHT}px`;
  xAxisCanvas.value.width = heatmapWidth * dpr;
  xAxisCanvas.value.height = AXIS_HEIGHT * dpr;
  xCtx.scale(dpr, dpr);
  xCtx.clearRect(0, 0, heatmapWidth, AXIS_HEIGHT);

  xCtx.fillStyle = "#000";
  xCtx.font = "12px sans-serif";
  xCtx.textAlign = "center";
  xCtx.textBaseline = "top";

  // Calculate visible frame range
  const startFrame = Math.max(0, Math.floor(-offsetX.value / scale.value));
  const endFrame = Math.min(width, Math.ceil((heatmapWidth - offsetX.value) / scale.value));

  // Draw ticks and labels
  const numTicks = 10;
  const tickSpacing = (endFrame - startFrame) / numTicks;

  for (let i = 0; i <= numTicks; i++) {
    const frame = Math.floor(startFrame + i * tickSpacing);
    if (frame < 0 || frame >= width) continue;

    const timeInSeconds = frame / fps;
    const xPos = (frame * scale.value) + offsetX.value;

    // Draw tick
    xCtx.beginPath();
    xCtx.moveTo(xPos, 0);
    xCtx.lineTo(xPos, 5);
    xCtx.strokeStyle = "#000";
    xCtx.stroke();

    // Draw label
    xCtx.fillText(`${timeInSeconds.toFixed(1)}s`, xPos, 8);
  }

  // Y-axis (left) - use display size (same height as heatmap canvas)
  yAxisCanvas.value.style.width = `${AXIS_WIDTH}px`;
  yAxisCanvas.value.style.height = `${heatmapHeight}px`;
  yAxisCanvas.value.width = AXIS_WIDTH * dpr;
  yAxisCanvas.value.height = heatmapHeight * dpr;
  yCtx.scale(dpr, dpr);
  yCtx.clearRect(0, 0, AXIS_WIDTH, heatmapHeight);

  yCtx.fillStyle = "#000";
  yCtx.font = "12px sans-serif";
  yCtx.textAlign = "right";
  yCtx.textBaseline = "middle";

  // Y-axis always shows all points (no scaling/offset on y-axis)
  // Choose a reasonable number of ticks based on available space
  const pixelsPerTick = 30; // Minimum pixels between ticks for readability
  const maxTicksBySpace = Math.floor(heatmapHeight / pixelsPerTick);
  const numYTicks = Math.min(maxTicksBySpace, height, 20);
  
  if (numYTicks > 0 && height > 0) {
    for (let i = 0; i <= numYTicks; i++) {
      // Calculate point index for this tick (evenly distributed from 0 to height-1)
      const pointIndex = numYTicks > 0 
        ? Math.round((i / numYTicks) * (height))
        : 0;
      
      if (pointIndex < 0 || pointIndex >= height) continue;

      // Map point index to y position in container
      // Add 0.5 to center the tick on the pixel row for that data point
      const yPos = ((pointIndex + 0.5) / height) * heatmapHeight;

      // Draw tick
      yCtx.beginPath();
      yCtx.moveTo(AXIS_WIDTH - 5, yPos);
      yCtx.lineTo(AXIS_WIDTH, yPos);
      yCtx.strokeStyle = "#000";
      yCtx.stroke();

      // Draw label - show actual point index
      yCtx.fillText(`${pointIndex}`, AXIS_WIDTH - 8, yPos);
    }
  }
}

/** Zoom with mouse wheel - only on x-axis */
function onWheel(e: WheelEvent) {
  if (!meta.value || !container.value) return;
  
  const delta = -e.deltaY;
  const zoomFactor = delta > 0 ? 1.1 : 0.9;
  const oldScale = scale.value;
  scale.value *= zoomFactor;
  
  // Clamp scale
  const axisWidth = props.compact ? 0 : AXIS_WIDTH;
  const containerWidth = container.value.clientWidth - axisWidth;
  const dataWidth = meta.value.width;
  // Allow zooming out to fit entire heatmap, and zooming in up to 10 pixels per data point
  const minScale = containerWidth / dataWidth; // Fit-to-width scale
  const maxScale = 10; // 10 pixels per data point maximum
  
  if (scale.value < minScale) scale.value = minScale;
  if (scale.value > maxScale) scale.value = maxScale;
  
  // Adjust offset to zoom towards mouse position (x-axis only)
  if (canvas.value) {
    const rect = canvas.value.getBoundingClientRect();
    const mouseX = e.clientX - rect.left;
    const zoomPointX = (mouseX - offsetX.value) / oldScale;
    offsetX.value = mouseX - (zoomPointX * scale.value);
    
    // Clamp offset to prevent panning beyond data bounds
    const scaledDataWidth = dataWidth * scale.value;
    if (scaledDataWidth <= containerWidth) {
      // If data fits in view, center it or align left
      offsetX.value = 0;
    } else {
      // Prevent scrolling past the edges
      if (offsetX.value > 0) offsetX.value = 0;
      if (offsetX.value < containerWidth - scaledDataWidth) {
        offsetX.value = containerWidth - scaledDataWidth;
      }
    }
  }
}

/** Pan with mouse drag */
let isDragging = false;
let hasDragged = false; // Track if mouse actually moved during drag
let mouseDownX = 0;
let mouseDownY = 0;
let lastX = 0;
let lastY = 0;

function onMouseDown(e: MouseEvent) {
  hasDragged = false; // Reset drag flag on mousedown
  isDragging = true;
  mouseDownX = e.clientX;
  mouseDownY = e.clientY;
  lastX = e.clientX;
  lastY = e.clientY;

  window.addEventListener("mousemove", onMouseMoveDrag);
  window.addEventListener("mouseup", onMouseUp);
}

function onMouseMoveDrag(e: MouseEvent) {
  if (!isDragging) return;
  const dx = e.clientX - lastX;
  const dy = e.clientY - lastY;
  
  // Check total distance from initial mousedown position
  const totalDx = e.clientX - mouseDownX;
  const totalDy = e.clientY - mouseDownY;
  
  // Only consider it a drag if mouse moved more than a few pixels from initial position
  if (Math.abs(totalDx) > 3 || Math.abs(totalDy) > 3) {
    hasDragged = true;
    // Only allow panning on x-axis
    lastX = e.clientX;
    lastY = e.clientY;

    offsetX.value += dx;
    // Keep y offset at 0 (no vertical panning)
    offsetY.value = 0;
  }
}

function onMouseUp() {
  isDragging = false;
  // Don't reset hasDragged here - let the click handler check it
  // Reset after a short delay to allow click handler to run first
  setTimeout(() => {
    hasDragged = false;
  }, 10);
  window.removeEventListener("mousemove", onMouseMoveDrag);
  window.removeEventListener("mouseup", onMouseUp);
}

function clearHoverInfo() {
  hoverInfo.value = null;
  mousePos.value = null;
}

function formatTimestamp(timeInSeconds: number): string {
  const totalMilliseconds = Math.max(0, Math.round(timeInSeconds * 1000));
  const minutes = Math.floor(totalMilliseconds / 60000);
  const seconds = Math.floor((totalMilliseconds % 60000) / 1000);
  const milliseconds = totalMilliseconds % 1000;
  return `${minutes}:${seconds.toString().padStart(2, "0")}.${milliseconds.toString().padStart(3, "0")}`;
}

/** Convert mouse position to frame/index */
function getFrameFromMouse(e: MouseEvent): { frame: number; index: number } | null {
  if (!canvas.value || !meta.value || !data.value || !container.value) return null;

  const rect = canvas.value.getBoundingClientRect();
  const mouseX = e.clientX - rect.left;
  const mouseY = e.clientY - rect.top;

  // Undo the transform to get into data-space
  // X-axis uses scale and offset, Y-axis is always scaled to fit container height
  const containerHeight = container.value.clientHeight - (props.compact ? 0 : AXIS_HEIGHT);
  const xInImage = (mouseX - offsetX.value) / scale.value;
  const yInImage = (mouseY / containerHeight) * meta.value.height;

  const frame = Math.floor(xInImage);
  const index = Math.floor(yInImage);

  if (
    frame < 0 ||
    index < 0 ||
    frame >= meta.value.width ||
    index >= meta.value.height
  ) {
    return null;
  }

  return { frame, index };
}

/** Hover logic (convert mouse position to frame/index) */
function onCanvasMouseMove(e: MouseEvent) {
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

function onCanvasMouseLeave() {
  clearHoverInfo();
}

function onCanvasClick(e: MouseEvent) {
  if (!canvas.value || !meta.value || !data.value || !container.value) {
    return;
  }

  // Don't emit click if user was dragging
  if (hasDragged) {
    return;
  }

  const result = getFrameFromMouse(e);
  if (result) {
    emit('frame-click', result.frame, result.index);
  }
}

function setupMouseMove() {
  if (!canvas.value || !container.value) return;
  canvas.value.addEventListener("mousemove", onCanvasMouseMove);
  canvas.value.addEventListener("mouseleave", onCanvasMouseLeave);
  canvas.value.addEventListener("click", onCanvasClick);
}

function cleanupMouseMove() {
  if (!canvas.value) return;
  canvas.value.removeEventListener("mousemove", onCanvasMouseMove);
  canvas.value.removeEventListener("mouseleave", onCanvasMouseLeave);
  canvas.value.removeEventListener("click", onCanvasClick);
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

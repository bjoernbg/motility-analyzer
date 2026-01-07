<script setup lang="ts">
import { ref, onMounted, onUnmounted, watch, computed, nextTick } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import { detectHorizontalWindow, getFrameImageUrl } from '../lib/api';
import type { FrameData, AnalysisParameters } from '../lib/api';
import { Slider } from './ui/slider';
import { ButtonGroup } from './ui/button-group';
import { Button } from './ui/button';
import { Icon } from './ui/icon';
import { debounce } from '../lib/utils';

const props = defineProps<{
  overlay?: boolean;
  highlightFrame?: number | null;
  highlightPointIndex?: number | null;
  showCanvasOverlay?: boolean;
}>();

const emit = defineEmits<{
  'update:showCanvasOverlay': [value: boolean];
}>();

const store = useAnalysisStore();

const imageRef = ref<HTMLImageElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const ctx = ref<CanvasRenderingContext2D | null>(null);
const videoFps = computed(() => store.currentVideo?.metadata?.fps ?? 30);
const currentParameters = ref<AnalysisParameters | null>(null);

// Debounced analysis function for parameter changes
const debouncedAnalyzeParams = debounce(async (params: AnalysisParameters) => {
  if (!params || !store.currentVideo || store.isProcessing) {
    return;
  }

  // Trigger analysis for current frame
  if (store.currentFrame !== null) {
    await store.analyzeCurrentFrame(params);
  }
}, 500); // 500ms debounce delay

// Watch for parameter changes from store (set by AnalysisParams or from analysis)
watch(() => store.currentParameters, (params) => {
  if (!params || !store.currentVideo || store.isProcessing) {
    return;
  }

  // Skip during analysis switch to avoid unnecessary requests
  if (store.isAnalysisSwitching) {
    return;
  }

  // params is already the value (not a ref), so use it directly
  currentParameters.value = params;

  // Trigger debounced analysis for current frame
  debouncedAnalyzeParams(params);
}, { immediate: true });


watch(() => canvasRef.value, () => { 
  if (canvasRef.value) { 
    ctx.value = canvasRef.value.getContext('2d');
    // Update canvas size when canvas ref is set
    if (imageRef.value) {
      updateCanvasSize();
    }
  } 
});

// Watch image ref to update canvas size when image loads
watch(() => imageRef.value, () => {
  if (imageRef.value && canvasRef.value) {
    // Wait for image to load
    if (imageRef.value.complete) {
      updateCanvasSize();
    }
  }
});

// Watch for changes to highlighted point in overlay mode to update canvas
watch([() => props.highlightFrame, () => props.highlightPointIndex], () => {
  if (props.overlay) {
    // Canvas will update on next animation frame
  }
});

// Watch for frame data to become available for the highlighted frame
watch(() => {
  if (props.overlay && props.highlightFrame !== null && props.highlightFrame !== undefined) {
    return store.liveFrameData.get(props.highlightFrame);
  }
  return null;
}, () => {
  // Canvas will update on next animation frame when frame data becomes available
}, { immediate: true });

onMounted(() => {
  startUpdateCanvasLoop();
});

onUnmounted(() => {
  // Cleanup requestAnimationFrame
  // if (rafId !== null) {
  //   cancelAnimationFrame(rafId);
  //   rafId = null;
  // }
  // pendingUpdate = false;
});

// Handle when frame image loads
function onFrameLoaded() {
  // Update canvas size when image loads
  if (imageRef.value && canvasRef.value) {
    updateCanvasSize();
  }
  // Automatically analyze the current frame when image loads
  analyzeCurrentFrameIfReady();
}

// Update canvas size to match image
function updateCanvasSize() {
  if (!canvasRef.value || !imageRef.value) return;
  canvasRef.value.width = imageRef.value.naturalWidth || imageRef.value.clientWidth;
  canvasRef.value.height = imageRef.value.naturalHeight || imageRef.value.clientHeight;
}

// Analyze current frame if video is ready and parameters are available
async function analyzeCurrentFrameIfReady() {
  if (!store.currentVideo || store.isProcessing || store.isAnalysisSwitching) {
    return;
  }

  // Get parameters from store or use defaults
  const params = currentParameters.value || store.currentParameters || getDefaultParameters();

  if (!params) {
    return;
  }

  // Update currentParameters if not set
  if (!currentParameters.value) {
    currentParameters.value = params;
  }

  // Analyze frame 0 (initial frame) when video loads
  const frameNum = store.currentFrame ?? 0;
  if (frameNum !== null) {
    store.currentFrame = frameNum;
    await store.analyzeCurrentFrame(params);
  }
}

// Get default parameters for analysis
function getDefaultParameters(): AnalysisParameters {
  return {
    alpha: 1.5,
    band: 20,
    smoothing_factor: 0.2,
    threshold_percentile: 80.0,
    horizontal_window_x_left: null,
    horizontal_window_x_right: null,
    num_tracking_points: 30,
    distribution_method: "center_line_projection",
  };
}

// Watch for video changes
watch(() => store.currentVideo, async (newVideo, oldVideo) => {
  // Skip if video hasn't actually changed
  if (newVideo?.id === oldVideo?.id) {
    return;
  }

  // Skip during analysis switch to avoid unnecessary requests
  if (store.isAnalysisSwitching) {
    return;
  }

  // Only reset to frame 0 if we're actually switching videos (not on initial mount)
  // On initial mount, oldVideo will be undefined, so we should preserve the current frame
  if (oldVideo !== undefined && newVideo?.id !== oldVideo?.id) {
    store.currentFrame = 0;
  }

  // Automatically analyze when video is ready (has metadata)
  await analyzeCurrentFrameIfReady();
}, { immediate: true });

// Watch for metadata updates separately (when video ID hasn't changed)
watch(() => store.currentVideo?.metadata, async (newMetadata, oldMetadata) => {
  // Skip if metadata hasn't actually changed
  if (newMetadata === oldMetadata) {
    return;
  }

  // Skip during analysis switch to avoid unnecessary requests
  if (store.isAnalysisSwitching) {
    return;
  }

  // Automatically analyze when metadata is available
  await analyzeCurrentFrameIfReady();
}, { immediate: true });

function startUpdateCanvasLoop() {
  updateCanvas();
  requestAnimationFrame(startUpdateCanvasLoop);
}
function drawPath(ctx: CanvasRenderingContext2D, scaleX: number, scaleY: number, points: Array<[number, number]>) {
  if (points && points.length > 0) {
    ctx.beginPath();
    const firstPoint = points[0]!;
    ctx.moveTo(firstPoint[0] * scaleX, firstPoint[1] * scaleY);
    for (let i = 1; i < points.length; i++) {
      const point = points[i]!;
      ctx.lineTo(point[0] * scaleX, point[1] * scaleY);
    }
    ctx.stroke();
  }
}
function updateCanvas() {
  const canvas = canvasRef.value;
  const image = imageRef.value;
  if (!canvas || !image) {
    return;
  }

  // Match canvas size to image
  const imageWidth = image.naturalWidth || image.clientWidth;
  const imageHeight = image.naturalHeight || image.clientHeight;

  if (imageWidth === 0 || imageHeight === 0 || !ctx.value) {
    return; // Image not ready yet
  }

  // Update canvas size if it doesn't match
  if (canvas.width !== imageWidth || canvas.height !== imageHeight) {
    canvas.width = imageWidth;
    canvas.height = imageHeight;
  }

  // Clear canvas
  ctx.value.clearRect(0, 0, canvas.width, canvas.height);

  // Get video metadata for scaling
  const metadata = store.currentVideo?.metadata;
  if (!metadata) {
    return; // Metadata not available yet
  }
  const videoPixelWidth = metadata.width;
  const videoPixelHeight = metadata.height;

  // Scale factors: from video pixel coordinates to canvas display coordinates
  const scaleX = canvas.width / videoPixelWidth;
  const scaleY = canvas.height / videoPixelHeight;

  // In overlay mode, only draw the highlighted point line
  if (props.overlay && props.highlightFrame !== null && props.highlightFrame !== undefined && 
      props.highlightPointIndex !== null && props.highlightPointIndex !== undefined) {
    const frameData = store.liveFrameData.get(props.highlightFrame);
    if (frameData && frameData.mpp && frameData.mpp.length > props.highlightPointIndex) {
      const pair = frameData.mpp[props.highlightPointIndex];
      if (pair) {
        const [cx, cy, tx, ty, bx, by] = pair;
        
        // Draw the vertical line connecting top and bottom points
        ctx.value.strokeStyle = '#ff8000';
        ctx.value.globalAlpha = 1;
        ctx.value.lineWidth = 15;
        ctx.value.beginPath();
        ctx.value.moveTo(tx * scaleX, ty * scaleY);
        ctx.value.lineTo(bx * scaleX, by * scaleY);
        ctx.value.stroke();
        
        // Draw points
        ctx.value.fillStyle = '#ff8000';
        ctx.value.beginPath();
        ctx.value.arc(tx * scaleX, ty * scaleY, 20, 0, 2 * Math.PI);
        ctx.value.fill();
        ctx.value.beginPath();
        ctx.value.arc(bx * scaleX, by * scaleY, 20, 0, 2 * Math.PI);
        ctx.value.fill();
      }
    }
  } else if (!props.overlay) {
    // Normal mode: draw all overlays if we have frame data for current frame
    const frameNum = store.currentFrame;
    if (frameNum !== null) {
      const frameData = store.liveFrameData.get(frameNum);
      if (frameData) {
        // Draw paths (using pixel coordinates, scaled to canvas)
        ctx.value.strokeStyle = '#000000';
        ctx.value.globalAlpha = .2;
        ctx.value.lineWidth = 7;

        // Draw top and bottom paths (shadow)
        drawPath(ctx.value, scaleX, scaleY, frameData.pt);
        drawPath(ctx.value, scaleX, scaleY, frameData.pb);

        // Draw top and bottom paths (foreground)
        ctx.value.strokeStyle = '#00c490';
        ctx.value.globalAlpha = 1;
        ctx.value.lineWidth = 3;

        drawPath(ctx.value, scaleX, scaleY, frameData.pt);
        drawPath(ctx.value, scaleX, scaleY, frameData.pb);




        // Draw measurement point pairs if available
        if (frameData.mpp && frameData.mpp.length > 0) {
          // Determine distribution method from current parameters
          const distMethod = currentParameters.value?.distribution_method || "center_line_projection";

          if (distMethod === "center_line_projection") {
            // Draw center path (foreground) with distinct color
            ctx.value.strokeStyle = '#ff8000';
            ctx.value.globalAlpha = 1;
            ctx.value.lineWidth = 2;
            drawPath(ctx.value, scaleX, scaleY, frameData.pc);

            // Method a: Draw center points, projection lines, and projected points
            // Format: [cx, cy, tx, ty, bx, by, distance]
            for (const pair of frameData.mpp) {
              const [cx, cy, tx, ty, bx, by] = pair;
              // Draw projection lines (dashed, light color)
              ctx.value.strokeStyle = '#0033ff';
              ctx.value.globalAlpha = 0.6;
              ctx.value.lineWidth = 1;
              ctx.value.setLineDash([10, 8]);

              // Line from bottom to top
              ctx.value.beginPath();
              ctx.value.moveTo(bx * scaleX, by * scaleY);
              ctx.value.lineTo(tx * scaleX, ty * scaleY);
              ctx.value.stroke();

              ctx.value.setLineDash([]);

              // Draw center point
              ctx.value.fillStyle = '#ff8000';
              ctx.value.globalAlpha = 1;
              ctx.value.beginPath();
              ctx.value.arc(cx * scaleX, cy * scaleY, 3, 0, 2 * Math.PI);
              ctx.value.fill();

              // Draw top projected point (green circle)
              ctx.value.fillStyle = '#00c490';
              ctx.value.beginPath();
              ctx.value.arc(tx * scaleX, ty * scaleY, 4, 0, 2 * Math.PI);
              ctx.value.fill();

              // Draw bottom projected point
              ctx.value.fillStyle = '#00c490';
              ctx.value.beginPath();
              ctx.value.arc(bx * scaleX, by * scaleY, 4, 0, 2 * Math.PI);
              ctx.value.fill();
            }
          } else if (distMethod === "x_axis_even") {
            // Method b: Draw top and bottom points with optional connecting line
            // Format: [cx, cy, tx, ty, bx, by, distance]
            for (const pair of frameData.mpp) {
              const [cx, cy, tx, ty, bx, by] = pair;
              // Draw connecting line (dashed, light color)
              ctx.value.strokeStyle = '#0033ff';
              ctx.value.globalAlpha = 0.6;
              ctx.value.lineWidth = 1;
              ctx.value.setLineDash([10, 8]);

              ctx.value.beginPath();
              ctx.value.moveTo(tx * scaleX, ty * scaleY);
              ctx.value.lineTo(bx * scaleX, by * scaleY);
              ctx.value.stroke();

              ctx.value.setLineDash([]);

              // Draw top point (green circle)
              ctx.value.fillStyle = '#00c490';
              ctx.value.globalAlpha = 1;
              ctx.value.beginPath();
              ctx.value.arc(tx * scaleX, ty * scaleY, 4, 0, 2 * Math.PI);
              ctx.value.fill();

              // Draw bottom point
              ctx.value.fillStyle = '#00c490';
              ctx.value.beginPath();
              ctx.value.arc(bx * scaleX, by * scaleY, 4, 0, 2 * Math.PI);
              ctx.value.fill();
            }
          }
        }

      }
    }
  }

  // Draw horizontal window borders if set (only in non-overlay mode)
  if (!props.overlay && currentParameters.value) {
    const xLeft = currentParameters.value.horizontal_window_x_left;
    const xRight = currentParameters.value.horizontal_window_x_right;

    if (xLeft !== null && xLeft !== undefined && xLeft >= 0) {
      ctx.value.strokeStyle = '#ffd700'; // Yellow
      ctx.value.lineWidth = 2;
      ctx.value.setLineDash([5, 5]); // Dashed line
      ctx.value.beginPath();
      const canvasX = xLeft * scaleX;
      ctx.value.moveTo(canvasX, 0);
      ctx.value.lineTo(canvasX, canvas.height);
      ctx.value.stroke();
      ctx.value.setLineDash([]); // Reset dash
    }

    if (xRight !== null && xRight !== undefined && xRight >= 0) {
      ctx.value.strokeStyle = '#ffd700'; // Yellow
      ctx.value.lineWidth = 2;
      ctx.value.setLineDash([5, 5]); // Dashed line
      ctx.value.beginPath();
      const canvasX = xRight * scaleX;
      ctx.value.moveTo(canvasX, 0);
      ctx.value.lineTo(canvasX, canvas.height);
      ctx.value.stroke();
      ctx.value.setLineDash([]); // Reset dash
    }
  }
}


// Computed property for frame image URL
const frameImageUrl = computed(() => {
  if (!store.currentVideo || store.currentFrame === null) {
    return null;
  }
  return getFrameImageUrl(store.currentVideo.id, store.currentFrame);
});

// Computed property for aspect ratio from video metadata
// Uses display_aspect_ratio if available (handles non-square pixels), falls back to width/height
const aspectRatio = computed(() => {
  const metadata = store.currentVideo?.metadata;
  if (!metadata) {
    return null;
  }
  // Prefer display_aspect_ratio for correct display with non-square pixels
  if (metadata.display_aspect_ratio) {
    return metadata.display_aspect_ratio;
  }
  // Fallback to pixel dimensions
  if (metadata.width && metadata.height) {
    return metadata.width / metadata.height;
  }
  return null;
});


const hasFrameData = computed(() => { return store.liveFrameData.size > 0; });
const isDetectingWindow = ref(false); // horizontal window detection
const showCanvasOverlay = computed({
  get: () => props.showCanvasOverlay ?? true,
  set: (value: boolean) => emit('update:showCanvasOverlay', value),
});

// Debounced function to save settings when window changes
const debouncedSaveSettings = debounce(async () => {
  if (store.currentVideo && store.currentParameters) {
    await store.saveCurrentSettings();
  }
}, 1000); // 1 second debounce for saving

// Debounced analysis function for horizontal window changes
const debouncedAnalyzeWindow = debounce(() => {
  if (store.currentVideo && !store.isProcessing && store.currentFrame !== null) {
    store.analyzeCurrentFrame(store.currentParameters!);
  }
}, 500); // 500ms debounce delay

// Computed property for dual-input slider (left and right window edges)
const windowSliderModel = computed({
  get: () => {
    const params = store.currentParameters;
    const videoWidth = store.currentVideo?.metadata?.width ?? 1920;
    const left = params?.horizontal_window_x_left ?? null;
    const right = params?.horizontal_window_x_right ?? null;

    // If both values are set, return them; otherwise return default range
    if (left !== null && left !== undefined && left >= 0 &&
      right !== null && right !== undefined && right >= 0) {
      return [left, right];
    }
    // Default to 10% and 90% of video width if not set
    return [Math.floor(videoWidth * 0.1), Math.floor(videoWidth * 0.9)];
  },
  set: (value: number[]) => {
    if (value.length >= 2) {
      const left = Math.max(0, Math.floor(value[0] ?? 0));
      const right = Math.max(left, Math.floor(value[1] ?? 0));

      // Get current values to check if they actually changed
      const currentParams = store.currentParameters || getDefaultParameters();
      const currentLeft = currentParams.horizontal_window_x_left;
      const currentRight = currentParams.horizontal_window_x_right;

      // Only update if values actually changed (avoid setting defaults on initial render)
      if (currentLeft !== left || currentRight !== right) {
        // Update store's current parameters
        store.currentParameters = {
          ...currentParams,
          horizontal_window_x_left: left,
          horizontal_window_x_right: right,
        };

        // Trigger debounced analysis with updated parameters
        debouncedAnalyzeWindow();
        // Save settings
        debouncedSaveSettings();
      }
    }
  }
});

// Get video width for slider max
const videoWidth = computed(() => {
  return store.currentVideo?.metadata?.width ?? 1920;
});

async function detectWindow() {
  if (!store.currentVideo) {
    return;
  }

  // Get current frame number from store
  const currentFrame = store.currentFrame ?? 0;

  isDetectingWindow.value = true;
  try {
    const result = await detectHorizontalWindow(store.currentVideo.id, currentFrame);
    const left = result.x_left >= 0 ? result.x_left : null;
    const right = result.x_right >= 0 ? result.x_right : null;

    // Update store's current parameters
    const currentParams = store.currentParameters || getDefaultParameters();
    store.currentParameters = {
      ...currentParams,
      horizontal_window_x_left: left,
      horizontal_window_x_right: right,
    };

    // Trigger single-frame analysis with new window values
    if (!store.isProcessing && store.currentFrame !== null) {
      await store.analyzeCurrentFrame(store.currentParameters);
    }

    // Save settings after window detection
    await store.saveCurrentSettings();
  } catch (error) {
    console.error('Failed to detect window:', error);
  } finally {
    isDetectingWindow.value = false;
  }
}
</script>

<template>
  <div class="video-player">
    <!-- Horizontal Window Slider (hidden in overlay mode) -->
    <div v-if="!overlay" class="window-slider-container">
      <!-- <div class="window-slider-controls">
        <button type="button" class="detect-window-button" @click="detectWindow"
          :disabled="isDetectingWindow || store.isProcessing || !store.currentVideo"
          title="Detect window boundaries on current frame">
          <span v-if="isDetectingWindow">Detecting...</span>
          <span v-else>Detect Window</span>
        </button>
      </div> -->
      <Slider v-model="windowSliderModel" :min="0" :max="videoWidth" :step="1" class="window-slider"
        track-class="!bg-transparent" range-class="!bg-white" thumb-class="!bg-white !border-white/80" />
    </div>
    <div v-if="!store.currentVideo" class="no-video">
      Please select a video to display.
    </div>
    <div v-else class="player-container">
      <div class="video-wrapper">
        <img
          v-if="frameImageUrl"
          ref="imageRef"
          :src="frameImageUrl"
          :alt="`Frame ${store.currentFrame}`"
          class="frame-image"
          @load="onFrameLoaded"
        />
        <canvas v-if="showCanvasOverlay" ref="canvasRef" class="overlay-canvas" />
        <!-- Badge showing when no analysis data is available for current frame -->
        <div v-if="!hasFrameData && store.currentFrame !== null && store.currentVideo" class="no-data-badge">
          No analysis data for this frame
        </div>
      </div>

    </div>
  </div>
</template>

<style scoped>
.video-player {
  padding: 4px;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
  position: relative;
}


h2 {
  margin-top: 0;
  margin-bottom: 1rem;
}

.no-video {
  padding: 2rem;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
}

.player-container {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.video-wrapper {
  position: relative;
  width: 100%;
  max-width: 1920px;
  margin: 0 auto;
  aspect-ratio: v-bind(aspectRatio);
}

.video-wrapper .frame-image {
  width: 100%;
  object-fit: fill;
  aspect-ratio: v-bind(aspectRatio);
  display: block;
  border-radius: 4px;
}

.overlay-canvas {
  position: absolute;
  top: 0;
  left: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
  z-index: 2;
}

.no-data-badge {
  position: absolute;
  top: 10px;
  right: 10px;
  background: color-mix(in oklch, var(--color-error-400) 75%, transparent);
  color: var(--text-inverted);
  padding: 0.3rem 0.5rem;
  border-radius: 3px;
  font-size: 0.7rem;
  font-weight: 500;
  pointer-events: none;
  z-index: 10;
  backdrop-filter: blur(4px);
}

.overlay-info {
  text-align: center;
  font-size: 0.85rem;
  color: var(--text-secondary);
  padding: 0.5rem;
}

.overlay-toolbar {
  display: flex;
  align-items: center;
  justify-content: end;
  gap: 1rem;
  padding: 0.5rem;
  flex-wrap: wrap;
}

.toolbar-loading {
  font-size: 0.75rem;
  color: var(--text-secondary);
  font-style: italic;
  margin-left: 0.25rem;
}

.processing-status {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 1rem;
  flex-wrap: wrap;
}

.resume-auto-seek-button {
  padding: 0.4rem 0.8rem;
  background: var(--color-primary-500);
  color: var(--text-inverted);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: background 0.2s;
}

.resume-auto-seek-button:hover {
  background: var(--color-primary-600);
}

.window-slider-container {
  position: absolute;
  top: 0;
  left: 0;
  right: 0;
  padding-block: 1rem;
  /* background: linear-gradient(to bottom, rgba(0, 0, 0, 0.8), rgba(0, 0, 0, 0.4), transparent); */
  pointer-events: none;
  z-index: 5;
}

.window-slider-controls {
  display: flex;
  justify-content: flex-end;
  margin-bottom: 0.5rem;
  pointer-events: auto;
}

.detect-window-button {
  padding: 0.4rem 0.8rem;
  background: var(--color-primary-500);
  color: var(--text-inverted);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.85rem;
  font-weight: 500;
  transition: background 0.2s;
  pointer-events: auto;
}

.detect-window-button:hover:not(:disabled) {
  background: var(--color-primary-600);
}

.detect-window-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.window-slider {
  pointer-events: auto;
  width: 100%;
}
</style>

<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import {
  getAnalysisFrame,
  getFrameImageUrl,
  getVideoDisplaySettings,
  type FrameData,
} from '../lib/api';
import HeatmapViewer from './HeatmapViewer.vue';
import { Slider } from './ui/slider';

const store = useAnalysisStore();

const isDragging = ref(false);
const sliderValue = ref([0]);
const highlightedPointIndex = ref<number | null>(null);

const leftFrameData = ref<FrameData | null>(null);
const rightFrameData = ref<FrameData | null>(null);

const leftPixelToMmFactor = ref(11);
const rightPixelToMmFactor = ref(11);

const leftImageRef = ref<HTMLImageElement | null>(null);
const rightImageRef = ref<HTMLImageElement | null>(null);
const leftOverlayCanvasRef = ref<HTMLCanvasElement | null>(null);
const rightOverlayCanvasRef = ref<HTMLCanvasElement | null>(null);

let loadFrameDataRequestId = 0;

const leftFps = computed(() => store.leftVideo?.metadata?.fps ?? 1);
const rightFps = computed(() => store.rightVideo?.metadata?.fps ?? 1);

const leftTotalFrames = computed(() => store.leftVideo?.metadata?.total_frames ?? 0);
const rightTotalFrames = computed(() => store.rightVideo?.metadata?.total_frames ?? 0);
const leftAspectRatio = computed(() => {
  const metadata = store.leftVideo?.metadata;
  if (!metadata) return 16 / 9;
  if (metadata.display_aspect_ratio && metadata.display_aspect_ratio > 0) {
    return metadata.display_aspect_ratio;
  }
  if (metadata.width > 0 && metadata.height > 0) {
    return metadata.width / metadata.height;
  }
  return 16 / 9;
});
const rightAspectRatio = computed(() => {
  const metadata = store.rightVideo?.metadata;
  if (!metadata) return 16 / 9;
  if (metadata.display_aspect_ratio && metadata.display_aspect_ratio > 0) {
    return metadata.display_aspect_ratio;
  }
  if (metadata.width > 0 && metadata.height > 0) {
    return metadata.width / metadata.height;
  }
  return 16 / 9;
});

const sliderStep = computed(() => {
  const fps = Math.max(leftFps.value, rightFps.value, 1);
  return 1 / fps;
});

function clampFrame(frame: number, totalFrames: number): number {
  if (totalFrames <= 0) return 0;
  return Math.max(0, Math.min(frame, totalFrames - 1));
}

const leftFrame = computed(() => {
  return clampFrame(Math.round(store.syncedTimeSec * leftFps.value), leftTotalFrames.value);
});

const rightFrame = computed(() => {
  return clampFrame(Math.round(store.syncedTimeSec * rightFps.value), rightTotalFrames.value);
});

const leftFrameImageUrl = computed(() => {
  if (!store.leftVideo) return null;
  return getFrameImageUrl(store.leftVideo.id, leftFrame.value);
});

const rightFrameImageUrl = computed(() => {
  if (!store.rightVideo) return null;
  return getFrameImageUrl(store.rightVideo.id, rightFrame.value);
});

watch(() => store.syncedTimeSec, (newTime) => {
  if (!isDragging.value) {
    sliderValue.value = [newTime];
  }
}, { immediate: true });

watch(
  () => store.leftVideo?.id,
  async (videoId) => {
    if (!videoId) {
      leftPixelToMmFactor.value = 11;
      return;
    }

    try {
      const settings = await getVideoDisplaySettings(videoId);
      leftPixelToMmFactor.value = settings.pixel_to_mm_factor;
    } catch {
      leftPixelToMmFactor.value = 11;
    }
  },
  { immediate: true }
);

watch(
  () => store.rightVideo?.id,
  async (videoId) => {
    if (!videoId) {
      rightPixelToMmFactor.value = 11;
      return;
    }

    try {
      const settings = await getVideoDisplaySettings(videoId);
      rightPixelToMmFactor.value = settings.pixel_to_mm_factor;
    } catch {
      rightPixelToMmFactor.value = 11;
    }
  },
  { immediate: true }
);

watch(
  () => [
    highlightedPointIndex.value,
    leftFrame.value,
    rightFrame.value,
    store.leftAnalysis?.id,
    store.rightAnalysis?.id,
  ],
  async () => {
    if (
      highlightedPointIndex.value === null ||
      !store.leftAnalysis?.id ||
      !store.rightAnalysis?.id
    ) {
      leftFrameData.value = null;
      rightFrameData.value = null;
      drawAllOverlays();
      return;
    }

    const requestId = ++loadFrameDataRequestId;

    try {
      const [leftData, rightData] = await Promise.all([
        getAnalysisFrame(store.leftAnalysis.id, leftFrame.value),
        getAnalysisFrame(store.rightAnalysis.id, rightFrame.value),
      ]);

      if (requestId !== loadFrameDataRequestId) {
        return;
      }

      leftFrameData.value = leftData;
      rightFrameData.value = rightData;
      drawAllOverlays();
    } catch {
      if (requestId !== loadFrameDataRequestId) {
        return;
      }
      leftFrameData.value = null;
      rightFrameData.value = null;
      drawAllOverlays();
    }
  },
  { immediate: true }
);

watch(
  () => [
    highlightedPointIndex.value,
    leftFrameData.value,
    rightFrameData.value,
    leftPixelToMmFactor.value,
    rightPixelToMmFactor.value,
  ],
  () => {
    drawAllOverlays();
  },
  { deep: true }
);

function setDragging(value: boolean) {
  isDragging.value = value;
}

function commitSliderValue() {
  const next = sliderValue.value[0] ?? 0;
  store.setSyncedTime(next);
}

function handleHeatmapClick(side: 'left' | 'right', frame: number, pointIndex: number) {
  highlightedPointIndex.value = pointIndex;

  const fps = side === 'left' ? leftFps.value : rightFps.value;
  if (fps <= 0) {
    return;
  }

  store.setSyncedTime(frame / fps);
}

function formatTime(seconds: number): string {
  const total = Math.max(0, seconds);
  const minutes = Math.floor(total / 60);
  const secs = Math.floor(total % 60);
  const millis = Math.floor((total - Math.floor(total)) * 1000);
  return `${minutes}:${secs.toString().padStart(2, '0')}.${millis.toString().padStart(3, '0')}`;
}

function getVideoDisplayName(video: { filename: string; display_name?: string | null }): string {
  const customName = video.display_name?.trim();
  return customName && customName.length > 0 ? customName : video.filename;
}

function hasCustomVideoName(video: { filename: string; display_name?: string | null }): boolean {
  const customName = video.display_name?.trim();
  return Boolean(customName && customName.length > 0);
}

function drawAllOverlays() {
  drawOverlay(
    leftOverlayCanvasRef.value,
    leftImageRef.value,
    store.leftVideo?.metadata?.width,
    store.leftVideo?.metadata?.height,
    leftFrameData.value,
    leftPixelToMmFactor.value,
  );

  drawOverlay(
    rightOverlayCanvasRef.value,
    rightImageRef.value,
    store.rightVideo?.metadata?.width,
    store.rightVideo?.metadata?.height,
    rightFrameData.value,
    rightPixelToMmFactor.value,
  );
}

function drawOverlay(
  canvas: HTMLCanvasElement | null,
  image: HTMLImageElement | null,
  videoWidth: number | undefined,
  videoHeight: number | undefined,
  frameData: FrameData | null,
  pixelToMmFactor: number,
) {
  if (!canvas || !image) {
    return;
  }

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return;
  }

  const cssWidth = image.clientWidth;
  const cssHeight = image.clientHeight;
  if (cssWidth <= 0 || cssHeight <= 0) {
    return;
  }

  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  if (
    highlightedPointIndex.value === null ||
    !frameData ||
    !frameData.mpp ||
    !videoWidth ||
    !videoHeight ||
    frameData.mpp.length <= highlightedPointIndex.value
  ) {
    return;
  }

  const pair = frameData.mpp[highlightedPointIndex.value];
  if (!pair || pair.length < 7) {
    return;
  }

  const [, , tx, ty, bx, by, distancePx] = pair;

  const scaleX = cssWidth / videoWidth;
  const scaleY = cssHeight / videoHeight;

  const topX = tx * scaleX;
  const topY = ty * scaleY;
  const bottomX = bx * scaleX;
  const bottomY = by * scaleY;

  ctx.strokeStyle = '#ff8a00';
  ctx.fillStyle = '#ff8a00';
  ctx.lineWidth = 2.5;

  ctx.beginPath();
  ctx.moveTo(topX, topY);
  ctx.lineTo(bottomX, bottomY);
  ctx.stroke();

  ctx.beginPath();
  ctx.arc(topX, topY, 4, 0, Math.PI * 2);
  ctx.fill();

  ctx.beginPath();
  ctx.arc(bottomX, bottomY, 4, 0, Math.PI * 2);
  ctx.fill();

  const distanceMm = distancePx / pixelToMmFactor;
  const label = `${distanceMm.toFixed(2)} mm`;
  const centerX = (topX + bottomX) / 2;
  const centerY = (topY + bottomY) / 2;

  ctx.font = 'bold 12px sans-serif';
  const textWidth = ctx.measureText(label).width;
  const textHeight = 18;

  const textX = centerX - textWidth / 2 - 6;
  const textY = centerY - textHeight - 6;

  ctx.fillStyle = 'rgba(0, 0, 0, 0.75)';
  ctx.fillRect(textX, textY, textWidth + 12, textHeight);

  ctx.fillStyle = '#ffffff';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, textX + 6, textY + textHeight / 2);
}
</script>

<template>
  <div class="workspace">
    <div class="workspace-header">
      <div>
        <h2>{{ store.currentMultiViewSession?.name ?? 'Combined Analysis' }}</h2>
        <p class="subtitle">Synchronized dual-angle playback and heatmap comparison</p>
      </div>
    </div>

    <div v-if="!store.leftVideo || !store.rightVideo || !store.leftAnalysis || !store.rightAnalysis" class="empty-state">
      Select a multi-view session to begin.
    </div>

    <div v-else class="workspace-body">
      <div class="sync-controls">
        <div class="time-values">
          <span>{{ formatTime(store.syncedTimeSec) }}</span>
          <span>/</span>
          <span>{{ formatTime(store.maxSyncedTimeSec) }}</span>
        </div>
        <Slider
          v-model="sliderValue"
          :min="0"
          :max="store.maxSyncedTimeSec"
          :step="sliderStep"
          class="sync-slider"
          @pointerdown="setDragging(true)"
          @pointerup="setDragging(false); commitSliderValue()"
          @pointercancel="setDragging(false)"
        />
      </div>

      <div class="comparison-grid">
        <section class="comparison-column">
          <div class="comparison-heading">
            <h3>{{ getVideoDisplayName(store.leftVideo) }}</h3>
            <p class="video-original-name" :class="{ 'video-original-name-hidden': !hasCustomVideoName(store.leftVideo) }">
              {{ hasCustomVideoName(store.leftVideo) ? `File: ${store.leftVideo.filename}` : ' ' }}
            </p>
          </div>
          <div class="video-frame-wrapper" :style="{ aspectRatio: `${leftAspectRatio}` }">
            <img
              v-if="leftFrameImageUrl"
              ref="leftImageRef"
              :src="leftFrameImageUrl"
              :alt="`Left frame ${leftFrame}`"
              class="video-frame"
              :style="{ aspectRatio: `${leftAspectRatio}` }"
              @load="drawAllOverlays"
            />
            <canvas ref="leftOverlayCanvasRef" class="overlay-canvas" />
          </div>
          <HeatmapViewer
            :key="`left-heatmap-${store.leftAnalysis.id}`"
            :analysis-id="store.leftAnalysis.id"
            :current-frame="leftFrame"
            @frame-click="(frame, pointIndex) => handleHeatmapClick('left', frame, pointIndex)"
          />
        </section>

        <section class="comparison-column">
          <div class="comparison-heading">
            <h3>{{ getVideoDisplayName(store.rightVideo) }}</h3>
            <p class="video-original-name" :class="{ 'video-original-name-hidden': !hasCustomVideoName(store.rightVideo) }">
              {{ hasCustomVideoName(store.rightVideo) ? `File: ${store.rightVideo.filename}` : ' ' }}
            </p>
          </div>
          <div class="video-frame-wrapper" :style="{ aspectRatio: `${rightAspectRatio}` }">
            <img
              v-if="rightFrameImageUrl"
              ref="rightImageRef"
              :src="rightFrameImageUrl"
              :alt="`Right frame ${rightFrame}`"
              class="video-frame"
              :style="{ aspectRatio: `${rightAspectRatio}` }"
              @load="drawAllOverlays"
            />
            <canvas ref="rightOverlayCanvasRef" class="overlay-canvas" />
          </div>
          <HeatmapViewer
            :key="`right-heatmap-${store.rightAnalysis.id}`"
            :analysis-id="store.rightAnalysis.id"
            :current-frame="rightFrame"
            @frame-click="(frame, pointIndex) => handleHeatmapClick('right', frame, pointIndex)"
          />
        </section>
      </div>
    </div>
  </div>
</template>

<style scoped>
.workspace {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
  padding: 1rem;
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.workspace-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
}

.workspace-header h2 {
  margin: 0;
  font-size: 1.1rem;
}

.subtitle {
  margin: 0.2rem 0 0;
  color: var(--text-secondary);
  font-size: 0.85rem;
}

.empty-state {
  color: var(--text-secondary);
  font-style: italic;
}

.workspace-body {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.sync-controls {
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.time-values {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.sync-slider {
  width: 100%;
}

.comparison-grid {
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 1rem;
}

.comparison-column {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.comparison-heading {
  min-height: 2.5rem;
  display: flex;
  flex-direction: column;
  justify-content: flex-start;
}

.comparison-column h3 {
  margin: 0;
  font-size: 0.95rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.video-original-name {
  margin: 0;
  font-size: 0.75rem;
  color: var(--text-secondary);
  line-height: 1.1;
  min-height: 0.9rem;
}

.video-original-name-hidden {
  visibility: hidden;
}

.video-frame-wrapper {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  overflow: hidden;
  background: var(--bg-secondary);
  position: relative;
}

.video-frame {
  width: 100%;
  display: block;
  object-fit: fill;
  background: black;
}

.overlay-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

@media (max-width: 1024px) {
  .comparison-grid {
    grid-template-columns: 1fr;
  }

  .workspace-header {
    flex-direction: column;
    align-items: flex-start;
  }
}
</style>

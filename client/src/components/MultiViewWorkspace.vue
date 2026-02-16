<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import {
  getHeatmapMeta,
  getAnalysisFrame,
  getFrameImageUrl,
  getVideoDisplaySettings,
  type FrameData,
  type HeatmapMeta,
} from '../lib/api';
import HeatmapViewer from './HeatmapViewer.vue';
import { Slider } from './ui/slider';
import { ButtonGroup } from './ui/button-group';
import { Button } from './ui/button';
import { Icon } from './ui/icon';

const store = useAnalysisStore();

const isDragging = ref(false);
const sliderValue = ref([0]);
const highlightedPointIndex = ref<number | null>(null);
const showDetectedEdges = ref(true);

const leftFrameData = ref<FrameData | null>(null);
const rightFrameData = ref<FrameData | null>(null);

const leftPixelToMmFactor = ref(11);
const rightPixelToMmFactor = ref(11);
const leftHeatmapMeta = ref<HeatmapMeta | null>(null);
const rightHeatmapMeta = ref<HeatmapMeta | null>(null);

let loadHeatmapMetaRequestId = 0;

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

const leftTimeSec = computed(() => store.syncedTimeSec);
const rightTimeSec = computed(() => store.syncedTimeSec + store.rightTimeShiftSec);

function clampFrame(frame: number, totalFrames: number): number {
  if (totalFrames <= 0) return 0;
  return Math.max(0, Math.min(frame, totalFrames - 1));
}

const leftFrame = computed(() => {
  return clampFrame(Math.round(leftTimeSec.value * leftFps.value), leftTotalFrames.value);
});

const rightFrame = computed(() => {
  return clampFrame(Math.round(rightTimeSec.value * rightFps.value), rightTotalFrames.value);
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
    showDetectedEdges.value,
    highlightedPointIndex.value,
    leftFrame.value,
    rightFrame.value,
    store.leftAnalysis?.id,
    store.rightAnalysis?.id,
  ],
  async () => {
    const shouldLoadFrameData = showDetectedEdges.value || highlightedPointIndex.value !== null;
    if (
      !shouldLoadFrameData ||
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
    showDetectedEdges.value,
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

watch(
  () => [
    store.leftAnalysis?.id,
    store.rightAnalysis?.id,
    leftPixelToMmFactor.value,
    rightPixelToMmFactor.value,
  ],
  async () => {
    if (!store.leftAnalysis?.id || !store.rightAnalysis?.id) {
      leftHeatmapMeta.value = null;
      rightHeatmapMeta.value = null;
      return;
    }

    const requestId = ++loadHeatmapMetaRequestId;
    try {
      const [leftMeta, rightMeta] = await Promise.all([
        getHeatmapMeta(store.leftAnalysis.id),
        getHeatmapMeta(store.rightAnalysis.id),
      ]);
      if (requestId !== loadHeatmapMetaRequestId) {
        return;
      }
      leftHeatmapMeta.value = leftMeta;
      rightHeatmapMeta.value = rightMeta;
    } catch {
      if (requestId !== loadHeatmapMetaRequestId) {
        return;
      }
      leftHeatmapMeta.value = null;
      rightHeatmapMeta.value = null;
    }
  },
  { immediate: true }
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

  const clickedTime = frame / fps;
  if (side === 'right') {
    store.setSyncedTime(clickedTime - store.rightTimeShiftSec);
    return;
  }
  store.setSyncedTime(clickedTime);
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

function getAnalysisDisplayName(analysis: { display_name?: string | null; created_at: string }): string {
  const customName = analysis.display_name?.trim();
  if (customName && customName.length > 0) {
    return customName;
  }
  return `Analysis ${new Date(analysis.created_at).toLocaleString()}`;
}

function getDistributionLabel(rawMethod: unknown): string {
  return rawMethod === 'center_line_projection' ? 'Center line' : 'X-axis even';
}

function getTrackingPointsLabel(params: Record<string, unknown>): string {
  const raw = params.num_tracking_points;
  const points = typeof raw === 'number' ? raw : 30;
  return `${points} points`;
}

function getWindowLabel(params: Record<string, unknown>): string | null {
  const left = params.horizontal_window_x_left;
  const right = params.horizontal_window_x_right;
  if (typeof left === 'number' && typeof right === 'number') {
    return `Window ${left} ↔ ${right}`;
  }
  return null;
}

function toMm(valuePx: number, meta: HeatmapMeta | null, fallbackFactor: number): number {
  const factor = meta?.display_settings?.pixel_to_mm_factor ?? fallbackFactor;
  if (factor <= 0) {
    return 0;
  }
  return valuePx / factor;
}

const leftScaleMinMm = computed(() => {
  if (!leftHeatmapMeta.value) {
    return null;
  }
  return toMm(leftHeatmapMeta.value.min, leftHeatmapMeta.value, leftPixelToMmFactor.value);
});

const rightScaleMinMm = computed(() => {
  if (!rightHeatmapMeta.value) {
    return null;
  }
  return toMm(
    rightHeatmapMeta.value.min,
    rightHeatmapMeta.value,
    rightPixelToMmFactor.value
  );
});

const leftScaleMaxMm = computed(() => {
  if (!leftHeatmapMeta.value) {
    return null;
  }
  return toMm(leftHeatmapMeta.value.max, leftHeatmapMeta.value, leftPixelToMmFactor.value);
});

const rightScaleMaxMm = computed(() => {
  if (!rightHeatmapMeta.value) {
    return null;
  }
  return toMm(
    rightHeatmapMeta.value.max,
    rightHeatmapMeta.value,
    rightPixelToMmFactor.value
  );
});

const combinedScaleMinMm = computed(() => {
  if (leftScaleMinMm.value === null || rightScaleMinMm.value === null) {
    return null;
  }
  return Math.min(leftScaleMinMm.value, rightScaleMinMm.value);
});

const combinedScaleMaxMm = computed(() => {
  if (leftScaleMaxMm.value === null || rightScaleMaxMm.value === null) {
    return null;
  }
  return Math.max(leftScaleMaxMm.value, rightScaleMaxMm.value);
});

const hasCombinedScale = computed(() => {
  return (
    combinedScaleMinMm.value !== null &&
    combinedScaleMaxMm.value !== null &&
    combinedScaleMaxMm.value > combinedScaleMinMm.value
  );
});

function hasCustomVideoName(video: { filename: string; display_name?: string | null }): boolean {
  const customName = video.display_name?.trim();
  return Boolean(customName && customName.length > 0);
}

function drawPath(
  ctx: CanvasRenderingContext2D,
  scaleX: number,
  scaleY: number,
  points: Array<[number, number]>
) {
  if (points.length === 0) {
    return;
  }

  const firstPoint = points[0];
  if (!firstPoint) {
    return;
  }

  ctx.beginPath();
  ctx.moveTo(firstPoint[0] * scaleX, firstPoint[1] * scaleY);
  for (let i = 1; i < points.length; i++) {
    const point = points[i];
    if (!point) {
      continue;
    }
    ctx.lineTo(point[0] * scaleX, point[1] * scaleY);
  }
  ctx.stroke();
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

  if (!frameData || !videoWidth || !videoHeight) {
    return;
  }

  const scaleX = cssWidth / videoWidth;
  const scaleY = cssHeight / videoHeight;

  if (showDetectedEdges.value) {
    ctx.strokeStyle = '#000000';
    ctx.globalAlpha = 0.2;
    ctx.lineWidth = 7;
    drawPath(ctx, scaleX, scaleY, frameData.pt);
    drawPath(ctx, scaleX, scaleY, frameData.pb);

    ctx.strokeStyle = '#00c490';
    ctx.globalAlpha = 1;
    ctx.lineWidth = 3;
    drawPath(ctx, scaleX, scaleY, frameData.pt);
    drawPath(ctx, scaleX, scaleY, frameData.pb);
  }

  if (
    highlightedPointIndex.value === null ||
    !frameData.mpp ||
    frameData.mpp.length <= highlightedPointIndex.value
  ) {
    return;
  }

  const pair = frameData.mpp[highlightedPointIndex.value];
  if (!pair || pair.length < 7) {
    return;
  }

  const [, , tx, ty, bx, by, distancePx] = pair;

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
          <span>{{ formatTime(store.minSyncedTimeSec) }} - {{ formatTime(store.maxSyncedTimeSec) }}</span>
        </div>
        <p v-if="hasCombinedScale" class="scale-summary">
          Combined color scale: {{ combinedScaleMinMm?.toFixed(2) }} - {{ combinedScaleMaxMm?.toFixed(2) }} mm
        </p>
        <Slider
          v-model="sliderValue"
          :min="store.minSyncedTimeSec"
          :max="store.maxSyncedTimeSec"
          :step="sliderStep"
          class="sync-slider"
          @pointerdown="setDragging(true)"
          @pointerup="setDragging(false); commitSliderValue()"
          @pointercancel="setDragging(false)"
        />
        <div class="sync-actions">
          <div class="overlay-toggle">
            <ButtonGroup>
              <Button
                :variant="showDetectedEdges ? 'default' : 'outline'"
                @click="showDetectedEdges = !showDetectedEdges"
                size="sm"
                title="Display detected paths"
              >
                <Icon name="lucide:chart-scatter" size="1.1em" />
              </Button>
            </ButtonGroup>
          </div>
        </div>
      </div>

      <div class="comparison-grid">
        <section class="comparison-column">
          <div class="comparison-heading">
            <h3>{{ getVideoDisplayName(store.leftVideo) }}</h3>
            <p class="video-original-name" :class="{ 'video-original-name-hidden': !hasCustomVideoName(store.leftVideo) }">
              {{ hasCustomVideoName(store.leftVideo) ? `File: ${store.leftVideo.filename}` : ' ' }}
            </p>
            <div class="analysis-meta-card">
              <p class="analysis-meta-title">{{ getAnalysisDisplayName(store.leftAnalysis) }}</p>
              <p class="analysis-meta-subtitle">{{ new Date(store.leftAnalysis.created_at).toLocaleString() }}</p>
              <div class="analysis-meta-tags">
                <span class="analysis-meta-tag">{{ getTrackingPointsLabel(store.leftAnalysis.parameters) }}</span>
                <span class="analysis-meta-tag">
                  {{ getDistributionLabel(store.leftAnalysis.parameters.distribution_method) }}
                </span>
                <span v-if="getWindowLabel(store.leftAnalysis.parameters)" class="analysis-meta-tag">
                  {{ getWindowLabel(store.leftAnalysis.parameters) }}
                </span>
                <span class="analysis-meta-tag">px/mm {{ leftPixelToMmFactor.toFixed(2) }}</span>
                <span class="analysis-meta-tag">fps {{ leftFps.toFixed(2) }}</span>
                <span class="analysis-meta-tag">frame {{ leftFrame }} / {{ leftTotalFrames }}</span>
              </div>
            </div>
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
            :heatmap-min-mm-override="hasCombinedScale ? combinedScaleMinMm : null"
            :heatmap-max-mm-override="hasCombinedScale ? combinedScaleMaxMm : null"
            @frame-click="(frame, pointIndex) => handleHeatmapClick('left', frame, pointIndex)"
          />
        </section>

        <section class="comparison-column">
          <div class="comparison-heading">
            <h3>{{ getVideoDisplayName(store.rightVideo) }}</h3>
            <p class="video-original-name" :class="{ 'video-original-name-hidden': !hasCustomVideoName(store.rightVideo) }">
              {{ hasCustomVideoName(store.rightVideo) ? `File: ${store.rightVideo.filename}` : ' ' }}
            </p>
            <div class="analysis-meta-card">
              <p class="analysis-meta-title">{{ getAnalysisDisplayName(store.rightAnalysis) }}</p>
              <p class="analysis-meta-subtitle">{{ new Date(store.rightAnalysis.created_at).toLocaleString() }}</p>
              <div class="analysis-meta-tags">
                <span class="analysis-meta-tag">{{ getTrackingPointsLabel(store.rightAnalysis.parameters) }}</span>
                <span class="analysis-meta-tag">
                  {{ getDistributionLabel(store.rightAnalysis.parameters.distribution_method) }}
                </span>
                <span v-if="getWindowLabel(store.rightAnalysis.parameters)" class="analysis-meta-tag">
                  {{ getWindowLabel(store.rightAnalysis.parameters) }}
                </span>
                <span class="analysis-meta-tag">px/mm {{ rightPixelToMmFactor.toFixed(2) }}</span>
                <span class="analysis-meta-tag">fps {{ rightFps.toFixed(2) }}</span>
                <span class="analysis-meta-tag">frame {{ rightFrame }} / {{ rightTotalFrames }}</span>
              </div>
            </div>
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
            :heatmap-min-mm-override="hasCombinedScale ? combinedScaleMinMm : null"
            :heatmap-max-mm-override="hasCombinedScale ? combinedScaleMaxMm : null"
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

.scale-summary {
  margin: 0;
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.sync-slider {
  width: 100%;
}

.sync-actions {
  display: flex;
  justify-content: flex-end;
}

.overlay-toggle {
  display: flex;
  align-items: center;
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
  gap: 0.35rem;
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

.analysis-meta-card {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
  padding: 0.5rem;
}

.analysis-meta-title {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 600;
}

.analysis-meta-subtitle {
  margin: 0.15rem 0 0;
  font-size: 0.72rem;
  color: var(--text-secondary);
}

.analysis-meta-tags {
  display: flex;
  flex-wrap: wrap;
  gap: 0.2rem;
  margin-top: 0.35rem;
}

.analysis-meta-tag {
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: var(--bg-primary);
  color: var(--text-secondary);
  font-size: 0.68rem;
  line-height: 1;
  padding: 0.2rem 0.4rem;
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

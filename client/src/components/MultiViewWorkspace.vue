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
import MultiViewDiffPanel from './MultiViewDiffPanel.vue';
import IntestineViewer3D from './IntestineViewer3D.vue';
import { Slider } from './ui/slider';
import { ButtonGroup } from './ui/button-group';
import { Button } from './ui/button';
import { Icon } from './ui/icon';
import { DEFAULT_NUM_TRACKING_POINTS, PIXEL_TO_MM_FACTOR } from '../lib/constants';
import { getVideoDisplayName, hasCustomDisplayName } from '../lib/domain/displayNames';
import { formatMultiViewDirection } from '../lib/domain/multiViewDirections';
import {
  formatDistributionMethod,
  formatTimestampWithMilliseconds,
  formatTrackingPoints,
  formatWindowRange,
} from '../lib/domain/formatting';

const store = useAnalysisStore();

type ComparisonViewMode = 'side-by-side' | 'diff' | '3d';
interface OverlayAlignmentContext {
  isReady: boolean;
  reason: string;
  leftAnchorXPx?: number | null;
  rightAnchorXPx?: number | null;
  targetOffsetMm?: number | null;
  targetWindowWidthMm?: number | null;
  leftTubeEndXLeftPx?: number | null;
  leftTubeEndXRightPx?: number | null;
  leftTubeEndYTopPx?: number | null;
  leftTubeEndYBottomPx?: number | null;
  rightTubeEndXLeftPx?: number | null;
  rightTubeEndXRightPx?: number | null;
  rightTubeEndYTopPx?: number | null;
  rightTubeEndYBottomPx?: number | null;
}

const isDragging = ref(false);
const sliderValue = ref([0]);
const highlightedPointIndex = ref<number | null>(null);
const showDetectedEdges = ref(true);
const comparisonMode = ref<ComparisonViewMode>('side-by-side');

const leftFrameData = ref<FrameData | null>(null);
const rightFrameData = ref<FrameData | null>(null);

const leftPixelToMmFactor = ref(PIXEL_TO_MM_FACTOR);
const rightPixelToMmFactor = ref(PIXEL_TO_MM_FACTOR);
const leftHeatmapMeta = ref<HeatmapMeta | null>(null);
const rightHeatmapMeta = ref<HeatmapMeta | null>(null);

let loadHeatmapMetaRequestId = 0;

const leftImageRef = ref<HTMLImageElement | null>(null);
const rightImageRef = ref<HTMLImageElement | null>(null);
const leftOverlayCanvasRef = ref<HTMLCanvasElement | null>(null);
const rightOverlayCanvasRef = ref<HTMLCanvasElement | null>(null);

const leftSidebarImageRef = ref<HTMLImageElement | null>(null);
const rightSidebarImageRef = ref<HTMLImageElement | null>(null);
const leftSidebarCanvasRef = ref<HTMLCanvasElement | null>(null);
const rightSidebarCanvasRef = ref<HTMLCanvasElement | null>(null);

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

const leftDirectionLabel = computed(() =>
  formatMultiViewDirection(store.currentMultiViewDirections.leftDirection)
);
const rightDirectionLabel = computed(() =>
  formatMultiViewDirection(store.currentMultiViewDirections.rightDirection)
);

watch(() => store.syncedTimeSec, (newTime) => {
  if (!isDragging.value) {
    sliderValue.value = [newTime];
  }
}, { immediate: true });

watch(
  () => store.leftVideo?.id,
  async (videoId) => {
    if (!videoId) {
      leftPixelToMmFactor.value = PIXEL_TO_MM_FACTOR;
      return;
    }

    try {
      const settings = await getVideoDisplaySettings(videoId);
      leftPixelToMmFactor.value = settings.pixel_to_mm_factor;
    } catch {
      leftPixelToMmFactor.value = PIXEL_TO_MM_FACTOR;
    }
  },
  { immediate: true }
);

watch(
  () => store.rightVideo?.id,
  async (videoId) => {
    if (!videoId) {
      rightPixelToMmFactor.value = PIXEL_TO_MM_FACTOR;
      return;
    }

    try {
      const settings = await getVideoDisplaySettings(videoId);
      rightPixelToMmFactor.value = settings.pixel_to_mm_factor;
    } catch {
      rightPixelToMmFactor.value = PIXEL_TO_MM_FACTOR;
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
    const shouldLoadFrameData =
      comparisonMode.value === 'diff' ||
      comparisonMode.value === '3d' ||
      showDetectedEdges.value ||
      highlightedPointIndex.value !== null;
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

async function handleAnalyzeAlignmentForDiffOverlay() {
  try {
    await store.computeMultiViewAlignment({
      applyTimeShift: true,
      sampleFrames: 7,
      maxShiftSec: 3.0,
    });
  } catch {
    // Store-level error state already captures backend failures.
  }
}

function formatTime(seconds: number): string {
  return formatTimestampWithMilliseconds(seconds);
}

function getAnalysisDisplayName(analysis: { display_name?: string | null; created_at: string }): string {
  const customName = analysis.display_name?.trim();
  if (customName && customName.length > 0) {
    return customName;
  }
  return `Analysis ${new Date(analysis.created_at).toLocaleString()}`;
}

function getDistributionLabel(rawMethod: unknown): string {
  return formatDistributionMethod(rawMethod);
}

function getTrackingPointsLabel(params: Record<string, unknown>): string {
  return formatTrackingPoints(params.num_tracking_points ?? DEFAULT_NUM_TRACKING_POINTS);
}

function getWindowLabel(params: Record<string, unknown>): string | null {
  return formatWindowRange(params.horizontal_window_x_left, params.horizontal_window_x_right);
}

function getWindowBounds(params: Record<string, unknown>): { left: number; right: number } | null {
  const left = params.horizontal_window_x_left;
  const right = params.horizontal_window_x_right;
  if (typeof left !== 'number' || typeof right !== 'number') {
    return null;
  }
  if (right <= left) {
    return null;
  }
  return { left, right };
}

function sidebarInnerStyle(
  analysis: { parameters: Record<string, unknown> },
  video: { metadata?: { width?: number; height?: number } } | null,
): Record<string, string> {
  const params = analysis.parameters;
  const xLeft = params.horizontal_window_x_left;
  const xRight = params.horizontal_window_x_right;
  const vw = video?.metadata?.width;
  if (typeof xLeft !== 'number' || typeof xRight !== 'number' || !vw || xRight <= xLeft) {
    return {};
  }
  const windowWidth = xRight - xLeft;
  const padding = windowWidth * 0.05;
  const padLeft = Math.max(0, xLeft - padding);
  const padRight = Math.min(vw, xRight + padding);
  const padWidth = padRight - padLeft;
  const scaleRatio = vw / padWidth;
  const offsetPercent = (padLeft / padWidth) * 100;
  return {
    width: `${(scaleRatio * 100).toFixed(1)}%`,
    marginLeft: `${(-offsetPercent).toFixed(1)}%`,
  };
}

const overlayAlignmentContext = computed<OverlayAlignmentContext>(() => {
  const suggestion = store.latestAlignmentSuggestion;
  const leftAnalysis = store.leftAnalysis;
  const rightAnalysis = store.rightAnalysis;

  if (!suggestion || !leftAnalysis || !rightAnalysis) {
    return {
      isReady: false,
      reason: 'Run Analyze Alignment to generate tube-anchor metadata for the current analysis pair.',
    };
  }

  if (
    suggestion.left_analysis_id !== leftAnalysis.id ||
    suggestion.right_analysis_id !== rightAnalysis.id
  ) {
    return {
      isReady: false,
      reason: 'The latest alignment suggestion is stale for this analysis pair. Run Analyze Alignment again.',
    };
  }

  const leftWindow = getWindowBounds(leftAnalysis.parameters);
  const rightWindow = getWindowBounds(rightAnalysis.parameters);
  if (!leftWindow || !rightWindow) {
    return {
      isReady: false,
      reason: 'Both analyses need valid horizontal window bounds to anchor the diff overlay.',
    };
  }

  const leftAnchorXPx = suggestion.window.left_anchor_x_px;
  const rightAnchorXPx = suggestion.window.right_anchor_x_px;
  const targetOffsetMm = suggestion.window.target_offset_mm;
  const targetWindowWidthMm = suggestion.window.target_window_width_mm;

  if (
    typeof leftAnchorXPx !== 'number' ||
    typeof rightAnchorXPx !== 'number' ||
    typeof targetOffsetMm !== 'number' ||
    typeof targetWindowWidthMm !== 'number' ||
    targetWindowWidthMm <= 0
  ) {
    return {
      isReady: false,
      reason: 'Alignment suggestion is missing anchor normalization data. Re-run Analyze Alignment.',
    };
  }

  if (targetWindowWidthMm < 0.5) {
    return {
      isReady: false,
      reason: 'Alignment suggestion produced an implausibly narrow target window. Re-run Analyze Alignment.',
    };
  }

  return {
    isReady: true,
    reason: '',
    leftAnchorXPx,
    rightAnchorXPx,
    targetOffsetMm,
    targetWindowWidthMm,
    leftTubeEndXLeftPx: suggestion.window.left_tube_end_x_left_px,
    leftTubeEndXRightPx: suggestion.window.left_tube_end_x_right_px,
    leftTubeEndYTopPx: suggestion.window.left_tube_end_y_top_px,
    leftTubeEndYBottomPx: suggestion.window.left_tube_end_y_bottom_px,
    rightTubeEndXLeftPx: suggestion.window.right_tube_end_x_left_px,
    rightTubeEndXRightPx: suggestion.window.right_tube_end_x_right_px,
    rightTubeEndYTopPx: suggestion.window.right_tube_end_y_top_px,
    rightTubeEndYBottomPx: suggestion.window.right_tube_end_y_bottom_px,
  };
});

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

  drawOverlay(
    leftSidebarCanvasRef.value,
    leftSidebarImageRef.value,
    store.leftVideo?.metadata?.width,
    store.leftVideo?.metadata?.height,
    leftFrameData.value,
    leftPixelToMmFactor.value,
  );

  drawOverlay(
    rightSidebarCanvasRef.value,
    rightSidebarImageRef.value,
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
      <div class="view-mode-tabs">
        <ButtonGroup>
          <Button
            size="sm"
            :variant="comparisonMode === 'side-by-side' ? 'default' : 'outline'"
            @click="comparisonMode = 'side-by-side'"
          >
            Side by Side
          </Button>
          <Button
            size="sm"
            :variant="comparisonMode === 'diff' ? 'default' : 'outline'"
            @click="comparisonMode = 'diff'"
          >
            Diff
          </Button>
          <Button
            size="sm"
            :variant="comparisonMode === '3d' ? 'default' : 'outline'"
            @click="comparisonMode = '3d'"
          >
            3D
          </Button>
        </ButtonGroup>
      </div>

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

      <div v-if="comparisonMode === 'side-by-side'" class="comparison-grid">
        <section class="comparison-column">
          <div class="comparison-heading">
            <h3>{{ getVideoDisplayName(store.leftVideo) }}</h3>
            <p class="video-original-name" :class="{ 'video-original-name-hidden': !hasCustomDisplayName(store.leftVideo) }">
              {{ hasCustomDisplayName(store.leftVideo) ? `File: ${store.leftVideo.filename}` : ' ' }}
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
            <p class="video-original-name" :class="{ 'video-original-name-hidden': !hasCustomDisplayName(store.rightVideo) }">
              {{ hasCustomDisplayName(store.rightVideo) ? `File: ${store.rightVideo.filename}` : ' ' }}
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

      <div v-else-if="comparisonMode === 'diff'" class="diff-mode-layout">
        <MultiViewDiffPanel
          :left-frame-image-url="leftFrameImageUrl"
          :right-frame-image-url="rightFrameImageUrl"
          :left-frame-data="leftFrameData"
          :right-frame-data="rightFrameData"
          :left-video-width="store.leftVideo.metadata?.width"
          :left-video-height="store.leftVideo.metadata?.height"
          :right-video-width="store.rightVideo.metadata?.width"
          :right-video-height="store.rightVideo.metadata?.height"
          :left-pixel-to-mm-factor="leftPixelToMmFactor"
          :right-pixel-to-mm-factor="rightPixelToMmFactor"
          :left-aspect-ratio="leftAspectRatio"
          :show-detected-edges="showDetectedEdges"
          :highlighted-point-index="highlightedPointIndex"
          :overlay-alignment-context="overlayAlignmentContext"
          :is-computing-alignment="store.isComputingAlignment"
          @update:show-detected-edges="showDetectedEdges = $event"
          @request-analyze-alignment="handleAnalyzeAlignmentForDiffOverlay"
        />

        <div class="comparison-grid">
          <section class="comparison-column">
            <div class="comparison-heading">
              <h3>{{ getVideoDisplayName(store.leftVideo) }}</h3>
            </div>
            <HeatmapViewer
              :key="`left-diff-heatmap-${store.leftAnalysis.id}`"
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
            </div>
            <HeatmapViewer
              :key="`right-diff-heatmap-${store.rightAnalysis.id}`"
              :analysis-id="store.rightAnalysis.id"
              :current-frame="rightFrame"
              :heatmap-min-mm-override="hasCombinedScale ? combinedScaleMinMm : null"
              :heatmap-max-mm-override="hasCombinedScale ? combinedScaleMaxMm : null"
              @frame-click="(frame, pointIndex) => handleHeatmapClick('right', frame, pointIndex)"
            />
          </section>
        </div>
      </div>

      <div v-else-if="comparisonMode === '3d'" class="viewer-3d-layout">
        <div class="viewer-3d-main">
          <div class="viewer-3d-summary">
            <span class="viewer-3d-chip">First Analysis: {{ leftDirectionLabel }}</span>
            <span class="viewer-3d-chip">Second Analysis: {{ rightDirectionLabel }}</span>
          </div>
          <IntestineViewer3D
            :left-frame-data="leftFrameData"
            :right-frame-data="rightFrameData"
            :left-pixel-to-mm-factor="leftPixelToMmFactor"
            :right-pixel-to-mm-factor="rightPixelToMmFactor"
            :heatmap-min-mm="hasCombinedScale ? combinedScaleMinMm : null"
            :heatmap-max-mm="hasCombinedScale ? combinedScaleMaxMm : null"
            :left-direction="store.currentMultiViewDirections.leftDirection"
            :right-direction="store.currentMultiViewDirections.rightDirection"
          />
        </div>
        <div class="viewer-3d-sidebar">
          <div class="sidebar-panel">
            <div class="sidebar-label-row">
              <div class="sidebar-label">First Analysis</div>
              <span class="viewer-3d-chip">{{ leftDirectionLabel }}</span>
            </div>
            <div class="sidebar-label-meta">{{ getVideoDisplayName(store.leftVideo) }}</div>
            <div class="sidebar-frame-clip">
              <div class="sidebar-frame-inner" :style="sidebarInnerStyle(store.leftAnalysis, store.leftVideo)">
                <img
                  v-if="leftFrameImageUrl"
                  ref="leftSidebarImageRef"
                  :src="leftFrameImageUrl"
                  :alt="`Left frame ${leftFrame}`"
                  class="sidebar-frame-img"
                  @load="drawAllOverlays"
                />
                <canvas ref="leftSidebarCanvasRef" class="overlay-canvas" />
              </div>
            </div>
          </div>
          <div class="sidebar-panel">
            <div class="sidebar-label-row">
              <div class="sidebar-label">Second Analysis</div>
              <span class="viewer-3d-chip">{{ rightDirectionLabel }}</span>
            </div>
            <div class="sidebar-label-meta">{{ getVideoDisplayName(store.rightVideo) }}</div>
            <div class="sidebar-frame-clip">
              <div class="sidebar-frame-inner" :style="sidebarInnerStyle(store.rightAnalysis, store.rightVideo)">
                <img
                  v-if="rightFrameImageUrl"
                  ref="rightSidebarImageRef"
                  :src="rightFrameImageUrl"
                  :alt="`Right frame ${rightFrame}`"
                  class="sidebar-frame-img"
                  @load="drawAllOverlays"
                />
                <canvas ref="rightSidebarCanvasRef" class="overlay-canvas" />
              </div>
            </div>
          </div>
          <div class="sidebar-panel sidebar-heatmap-panel">
            <div class="sidebar-label-row">
              <div class="sidebar-label">First Analysis Heatmap</div>
              <span class="viewer-3d-chip">{{ leftDirectionLabel }}</span>
            </div>
            <div class="sidebar-label-meta">{{ getVideoDisplayName(store.leftVideo) }}</div>
            <HeatmapViewer
              :key="`left-3d-heatmap-${store.leftAnalysis.id}`"
              :analysis-id="store.leftAnalysis.id"
              :current-frame="leftFrame"
              :compact="true"
              :heatmap-min-mm-override="hasCombinedScale ? combinedScaleMinMm : null"
              :heatmap-max-mm-override="hasCombinedScale ? combinedScaleMaxMm : null"
            />
          </div>
          <div class="sidebar-panel sidebar-heatmap-panel">
            <div class="sidebar-label-row">
              <div class="sidebar-label">Second Analysis Heatmap</div>
              <span class="viewer-3d-chip">{{ rightDirectionLabel }}</span>
            </div>
            <div class="sidebar-label-meta">{{ getVideoDisplayName(store.rightVideo) }}</div>
            <HeatmapViewer
              :key="`right-3d-heatmap-${store.rightAnalysis.id}`"
              :analysis-id="store.rightAnalysis.id"
              :current-frame="rightFrame"
              :compact="true"
              :heatmap-min-mm-override="hasCombinedScale ? combinedScaleMinMm : null"
              :heatmap-max-mm-override="hasCombinedScale ? combinedScaleMaxMm : null"
            />
          </div>
        </div>
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

.view-mode-tabs {
  display: flex;
  align-items: center;
  justify-content: flex-start;
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

.diff-mode-layout {
  display: flex;
  flex-direction: column;
  gap: 1rem;
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

.viewer-3d-layout {
  display: flex;
  gap: 0.75rem;
  height: 750px;
}

.viewer-3d-main {
  flex: 3;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  border-radius: 8px;
  overflow: hidden;
}

.viewer-3d-summary {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
}

.viewer-3d-chip {
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 0.7rem;
  font-weight: 600;
  line-height: 1;
  padding: 0.22rem 0.45rem;
}

.viewer-3d-sidebar {
  flex: 1;
  min-width: 0;
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  overflow: hidden;
}

.sidebar-panel {
  flex: 1;
  min-height: 0;
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
  overflow: hidden;
}

.sidebar-label-row {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

.sidebar-label {
  font-size: 0.72rem;
  color: var(--text-secondary);
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
}

.sidebar-label-meta {
  font-size: 0.82rem;
  font-weight: 600;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
  flex-shrink: 0;
}

.sidebar-frame-clip {
  flex: 1;
  min-height: 0;
  overflow: hidden;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  background: black;
  position: relative;
}

.sidebar-frame-inner {
  position: absolute;
  top: 50%;
  left: 0;
  transform: translateY(-50%);
}

.sidebar-frame-img {
  display: block;
  width: 100%;
  height: auto;
}

.sidebar-heatmap-panel :deep(.heatmap-container) {
  flex: 1;
  min-height: 0;
}

@media (max-width: 1024px) {
  .comparison-grid {
    grid-template-columns: 1fr;
  }

  .workspace-header {
    flex-direction: column;
    align-items: flex-start;
  }

  .viewer-3d-layout {
    flex-direction: column;
    height: auto;
  }

  .viewer-3d-main {
    min-height: 400px;
  }

  .viewer-3d-sidebar {
    flex-direction: row;
    flex-wrap: wrap;
    gap: 0.5rem;
    height: 200px;
  }

  .sidebar-panel {
    flex: 1 1 45%;
    min-width: 0;
  }
}
</style>

<script setup lang="ts">
import { computed } from 'vue';
import type { FrameData } from '../lib/api';
import { useHeatmapDiff } from '../composables/useHeatmapDiff';
import FrameDiffOverlay from './FrameDiffOverlay.vue';
import HeatmapDiffViewer from './HeatmapDiffViewer.vue';
import { Slider } from './ui/slider';
import { Button } from './ui/button';
import { ButtonGroup } from './ui/button-group';
import { Icon } from './ui/icon';

const props = defineProps<{
  leftAnalysisId: string;
  rightAnalysisId: string;
  leftFrameImageUrl: string | null;
  rightFrameImageUrl: string | null;
  leftFrameData: FrameData | null;
  rightFrameData: FrameData | null;
  leftVideoWidth?: number;
  leftVideoHeight?: number;
  rightVideoWidth?: number;
  rightVideoHeight?: number;
  leftFps: number;
  rightFps: number;
  minSyncedTimeSec: number;
  maxSyncedTimeSec: number;
  currentSyncedTimeSec: number;
  rightTimeShiftSec: number;
  leftPixelToMmFactor: number;
  rightPixelToMmFactor: number;
  leftAspectRatio: number;
  showDetectedEdges: boolean;
  highlightedPointIndex: number | null;
}>();

const emit = defineEmits<{
  'frame-click': [syncedTimeSec: number, pointIndex: number];
  'update:show-detected-edges': [value: boolean];
}>();

const leftAnalysisIdRef = computed(() => props.leftAnalysisId);
const rightAnalysisIdRef = computed(() => props.rightAnalysisId);
const minSyncedTimeRef = computed(() => props.minSyncedTimeSec);
const maxSyncedTimeRef = computed(() => props.maxSyncedTimeSec);
const rightShiftRef = computed(() => props.rightTimeShiftSec);
const leftFpsRef = computed(() => props.leftFps);
const rightFpsRef = computed(() => props.rightFps);

const {
  meta,
  leftAlignedMm,
  rightAlignedMm,
  diffMm,
  isLoading,
  error,
  blurSigma,
  deadbandMm,
  overlayAlpha,
  recompute,
} = useHeatmapDiff({
  leftAnalysisId: leftAnalysisIdRef,
  rightAnalysisId: rightAnalysisIdRef,
  minSyncedTimeSec: minSyncedTimeRef,
  maxSyncedTimeSec: maxSyncedTimeRef,
  rightTimeShiftSec: rightShiftRef,
  leftFps: leftFpsRef,
  rightFps: rightFpsRef,
});

const overlayAlphaModel = computed({
  get: () => [overlayAlpha.value],
  set: (value: number[]) => {
    const next = value[0] ?? 0.45;
    overlayAlpha.value = Math.max(0.1, Math.min(1, next));
  },
});

const blurSigmaModel = computed({
  get: () => [blurSigma.value],
  set: (value: number[]) => {
    const next = value[0] ?? 1;
    blurSigma.value = Math.max(0, Math.min(4, next));
  },
});

const deadbandModel = computed({
  get: () => [deadbandMm.value],
  set: (value: number[]) => {
    const next = value[0] ?? 0.15;
    deadbandMm.value = Math.max(0, Math.min(2, next));
  },
});

function handleDiffFrameClick(frame: number, pointIndex: number) {
  if (!meta.value || meta.value.fps <= 0) {
    return;
  }
  const syncedTimeSec = meta.value.minTimeSec + frame / meta.value.fps;
  emit('frame-click', syncedTimeSec, pointIndex);
}
</script>

<template>
  <div class="diff-panel">
    <div class="diff-controls">
      <div class="control-group">
        <span class="control-label">Detected edges</span>
        <ButtonGroup>
          <Button
            size="sm"
            :variant="showDetectedEdges ? 'default' : 'outline'"
            title="Display detected paths"
            @click="emit('update:show-detected-edges', !showDetectedEdges)"
          >
            <Icon name="lucide:chart-scatter" size="1.1em" />
          </Button>
        </ButtonGroup>
      </div>

      <div class="control-group slider-group">
        <span class="control-label">Overlay alpha</span>
        <div class="slider-row">
          <Slider v-model="overlayAlphaModel" :min="0.1" :max="1" :step="0.01" />
          <span class="control-value">{{ overlayAlpha.toFixed(2) }}</span>
        </div>
      </div>

      <div class="control-group slider-group">
        <span class="control-label">Blur sigma</span>
        <div class="slider-row">
          <Slider v-model="blurSigmaModel" :min="0" :max="4" :step="0.05" />
          <span class="control-value">{{ blurSigma.toFixed(2) }}</span>
        </div>
      </div>

      <div class="control-group slider-group">
        <span class="control-label">Deadband (mm)</span>
        <div class="slider-row">
          <Slider v-model="deadbandModel" :min="0" :max="2" :step="0.01" />
          <span class="control-value">{{ deadbandMm.toFixed(2) }}</span>
        </div>
      </div>

      <div class="control-group">
        <Button size="sm" variant="outline" :disabled="isLoading" @click="recompute">
          {{ isLoading ? 'Computing...' : 'Recompute diff' }}
        </Button>
      </div>
    </div>

    <div class="diff-legend">
      <span><span class="legend-dot left" /> Left edges</span>
      <span><span class="legend-dot right" /> Right edges</span>
      <span><span class="legend-dot pair" /> Highlighted measurement</span>
      <span class="scale-label">
        Signed diff scale: +/-{{ meta?.diffAbsMaxMm.toFixed(2) ?? '0.00' }} mm
      </span>
    </div>

    <FrameDiffOverlay
      :left-frame-image-url="leftFrameImageUrl"
      :right-frame-image-url="rightFrameImageUrl"
      :left-frame-data="leftFrameData"
      :right-frame-data="rightFrameData"
      :left-video-width="leftVideoWidth"
      :left-video-height="leftVideoHeight"
      :right-video-width="rightVideoWidth"
      :right-video-height="rightVideoHeight"
      :left-pixel-to-mm-factor="leftPixelToMmFactor"
      :right-pixel-to-mm-factor="rightPixelToMmFactor"
      :show-detected-edges="showDetectedEdges"
      :highlighted-point-index="highlightedPointIndex"
      :overlay-alpha="overlayAlpha"
      :aspect-ratio="leftAspectRatio"
    />

    <HeatmapDiffViewer
      :meta="meta"
      :diff-mm="diffMm"
      :left-aligned-mm="leftAlignedMm"
      :right-aligned-mm="rightAlignedMm"
      :current-synced-time-sec="currentSyncedTimeSec"
      :is-loading="isLoading"
      :error="error"
      @frame-click="handleDiffFrameClick"
    />
  </div>
</template>

<style scoped>
.diff-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.diff-controls {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-secondary);
  padding: 0.65rem;
  display: grid;
  grid-template-columns: repeat(2, minmax(0, 1fr));
  gap: 0.55rem 0.8rem;
}

.control-group {
  display: flex;
  align-items: center;
  gap: 0.6rem;
}

.slider-group {
  flex-direction: column;
  align-items: flex-start;
  gap: 0.25rem;
}

.slider-row {
  width: 100%;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.slider-row :deep(.slider) {
  flex: 1;
}

.control-label {
  font-size: 0.76rem;
  color: var(--text-secondary);
  font-weight: 600;
}

.control-value {
  min-width: 2.8rem;
  text-align: right;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.diff-legend {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
  padding: 0.45rem 0.55rem;
  display: flex;
  gap: 0.8rem;
  flex-wrap: wrap;
  font-size: 0.74rem;
  color: var(--text-secondary);
}

.legend-dot {
  display: inline-block;
  width: 10px;
  height: 10px;
  border-radius: 999px;
  margin-right: 0.28rem;
}

.legend-dot.left {
  background: rgba(34, 211, 238, 0.95);
}

.legend-dot.right {
  background: rgba(251, 146, 60, 0.95);
}

.legend-dot.pair {
  background: #ffbf00;
}

.scale-label {
  font-weight: 600;
}

@media (max-width: 1024px) {
  .diff-controls {
    grid-template-columns: 1fr;
  }
}
</style>

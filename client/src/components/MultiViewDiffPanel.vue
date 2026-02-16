<script setup lang="ts">
import { computed, ref } from 'vue';
import type { FrameData } from '../lib/api';
import FrameDiffOverlay from './FrameDiffOverlay.vue';
import { Slider } from './ui/slider';
import { Button } from './ui/button';
import { ButtonGroup } from './ui/button-group';
import { Icon } from './ui/icon';

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

const props = defineProps<{
  leftFrameImageUrl: string | null;
  rightFrameImageUrl: string | null;
  leftFrameData: FrameData | null;
  rightFrameData: FrameData | null;
  leftVideoWidth?: number;
  leftVideoHeight?: number;
  rightVideoWidth?: number;
  rightVideoHeight?: number;
  leftPixelToMmFactor: number;
  rightPixelToMmFactor: number;
  leftAspectRatio: number;
  showDetectedEdges: boolean;
  highlightedPointIndex: number | null;
  overlayAlignmentContext: OverlayAlignmentContext;
  isComputingAlignment: boolean;
}>();

const emit = defineEmits<{
  'update:show-detected-edges': [value: boolean];
  'request-analyze-alignment': [];
}>();

const overlayAlpha = ref(0.45);

const overlayAlphaModel = computed({
  get: () => [overlayAlpha.value],
  set: (value: number[]) => {
    const next = value[0] ?? 0.45;
    overlayAlpha.value = Math.max(0.1, Math.min(1, next));
  },
});

const frameAlignmentData = computed(() => {
  if (!props.overlayAlignmentContext.isReady) {
    return null;
  }

  const leftAnchor = props.overlayAlignmentContext.leftAnchorXPx;
  const rightAnchor = props.overlayAlignmentContext.rightAnchorXPx;
  const targetOffsetMm = props.overlayAlignmentContext.targetOffsetMm;
  const targetWindowWidthMm = props.overlayAlignmentContext.targetWindowWidthMm;

  if (
    typeof leftAnchor !== 'number' ||
    typeof rightAnchor !== 'number' ||
    typeof targetOffsetMm !== 'number' ||
    typeof targetWindowWidthMm !== 'number' ||
    targetWindowWidthMm <= 0
  ) {
    return null;
  }

  return {
    leftAnchorXPx: leftAnchor,
    rightAnchorXPx: rightAnchor,
    targetOffsetMm,
    targetWindowWidthMm,
    leftTubeEndXLeftPx: props.overlayAlignmentContext.leftTubeEndXLeftPx ?? null,
    leftTubeEndXRightPx: props.overlayAlignmentContext.leftTubeEndXRightPx ?? null,
    leftTubeEndYTopPx: props.overlayAlignmentContext.leftTubeEndYTopPx ?? null,
    leftTubeEndYBottomPx: props.overlayAlignmentContext.leftTubeEndYBottomPx ?? null,
    rightTubeEndXLeftPx: props.overlayAlignmentContext.rightTubeEndXLeftPx ?? null,
    rightTubeEndXRightPx: props.overlayAlignmentContext.rightTubeEndXRightPx ?? null,
    rightTubeEndYTopPx: props.overlayAlignmentContext.rightTubeEndYTopPx ?? null,
    rightTubeEndYBottomPx: props.overlayAlignmentContext.rightTubeEndYBottomPx ?? null,
  };
});

const alignmentStatusLabel = computed(() =>
  frameAlignmentData.value ? 'Anchor alignment ready' : 'Anchor alignment required'
);
</script>

<template>
  <div class="diff-panel">
    <div class="alignment-status" :class="{ ready: !!frameAlignmentData, blocked: !frameAlignmentData }">
      {{ alignmentStatusLabel }}
    </div>

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
    </div>

    <div class="diff-legend">
      <span><span class="legend-dot left" /> Left edges</span>
      <span><span class="legend-dot right" /> Right edges</span>
      <span><span class="legend-box left" /> Left tube-end box</span>
      <span><span class="legend-box right" /> Right tube-end box</span>
      <span><span class="legend-dot pair" /> Highlighted measurement</span>
    </div>

    <div v-if="!frameAlignmentData" class="alignment-blocker">
      <p class="alignment-blocker-title">Run alignment analysis to enable anchor-aligned frame overlay.</p>
      <p class="alignment-blocker-copy">{{ overlayAlignmentContext.reason }}</p>
      <Button
        size="sm"
        variant="outline"
        :disabled="isComputingAlignment"
        @click="emit('request-analyze-alignment')"
      >
        {{ isComputingAlignment ? 'Analyzing...' : 'Analyze Alignment' }}
      </Button>
    </div>

    <FrameDiffOverlay
      v-else
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
      :alignment-context="frameAlignmentData"
    />
  </div>
</template>

<style scoped>
.diff-panel {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.alignment-status {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
  font-size: 0.75rem;
  font-weight: 600;
  padding: 0.35rem 0.55rem;
}

.alignment-status.ready {
  color: var(--color-success-700);
  border-color: color-mix(in oklab, var(--color-success-500) 50%, var(--border-light));
}

.alignment-status.blocked {
  color: var(--color-warning-700);
  border-color: color-mix(in oklab, var(--color-warning-500) 50%, var(--border-light));
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

.legend-box {
  display: inline-block;
  width: 10px;
  height: 10px;
  margin-right: 0.28rem;
  border: 2px dashed transparent;
  box-sizing: border-box;
}

.legend-box.left {
  border-color: rgba(34, 211, 238, 0.95);
}

.legend-box.right {
  border-color: rgba(251, 146, 60, 0.95);
}

.alignment-blocker {
  border: 1px dashed var(--border-medium);
  border-radius: 8px;
  background: var(--bg-secondary);
  padding: 0.75rem;
  display: flex;
  flex-direction: column;
  gap: 0.45rem;
}

.alignment-blocker-title {
  margin: 0;
  font-size: 0.82rem;
  font-weight: 600;
}

.alignment-blocker-copy {
  margin: 0;
  font-size: 0.76rem;
  color: var(--text-secondary);
}

@media (max-width: 1024px) {
  .diff-controls {
    grid-template-columns: 1fr;
  }
}
</style>

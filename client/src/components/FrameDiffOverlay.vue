<script setup lang="ts">
import { onMounted, onUnmounted, ref, watch } from 'vue';
import type { FrameData } from '../lib/api';

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
  showDetectedEdges: boolean;
  highlightedPointIndex: number | null;
  overlayAlpha: number;
  aspectRatio: number;
}>();

const wrapperRef = ref<HTMLDivElement | null>(null);
const leftImageRef = ref<HTMLImageElement | null>(null);
const rightImageRef = ref<HTMLImageElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const resizeObserver = ref<ResizeObserver | null>(null);

function normalizePoint(
  x: number,
  y: number,
  videoWidth: number | undefined,
  videoHeight: number | undefined,
  canvasWidth: number,
  canvasHeight: number
): [number, number] | null {
  if (!videoWidth || !videoHeight || videoWidth <= 0 || videoHeight <= 0) {
    return null;
  }
  return [(x / videoWidth) * canvasWidth, (y / videoHeight) * canvasHeight];
}

function drawPath(
  ctx: CanvasRenderingContext2D,
  points: Array<[number, number]>,
  videoWidth: number | undefined,
  videoHeight: number | undefined,
  canvasWidth: number,
  canvasHeight: number
) {
  if (points.length === 0) {
    return;
  }

  let started = false;
  for (const point of points) {
    const normalized = normalizePoint(
      point[0],
      point[1],
      videoWidth,
      videoHeight,
      canvasWidth,
      canvasHeight
    );
    if (!normalized) {
      continue;
    }
    if (!started) {
      ctx.beginPath();
      ctx.moveTo(normalized[0], normalized[1]);
      started = true;
    } else {
      ctx.lineTo(normalized[0], normalized[1]);
    }
  }
  if (started) {
    ctx.stroke();
  }
}

function drawHighlightedPair(
  ctx: CanvasRenderingContext2D,
  pair: [number, number, number, number, number, number, number],
  videoWidth: number | undefined,
  videoHeight: number | undefined,
  canvasWidth: number,
  canvasHeight: number,
  label: string,
  dashed: boolean
) {
  const [, , tx, ty, bx, by] = pair;
  const top = normalizePoint(tx, ty, videoWidth, videoHeight, canvasWidth, canvasHeight);
  const bottom = normalizePoint(bx, by, videoWidth, videoHeight, canvasWidth, canvasHeight);
  if (!top || !bottom) {
    return;
  }

  ctx.save();
  ctx.strokeStyle = '#ffbf00';
  ctx.fillStyle = '#ffbf00';
  ctx.lineWidth = 2.5;
  ctx.setLineDash(dashed ? [6, 4] : []);

  ctx.beginPath();
  ctx.moveTo(top[0], top[1]);
  ctx.lineTo(bottom[0], bottom[1]);
  ctx.stroke();

  ctx.setLineDash([]);
  ctx.beginPath();
  ctx.arc(top[0], top[1], 3.8, 0, Math.PI * 2);
  ctx.fill();

  ctx.beginPath();
  ctx.arc(bottom[0], bottom[1], 3.8, 0, Math.PI * 2);
  ctx.fill();

  const cx = (top[0] + bottom[0]) / 2;
  const cy = (top[1] + bottom[1]) / 2;
  ctx.font = 'bold 12px sans-serif';
  const textWidth = ctx.measureText(label).width;
  const textHeight = 18;
  const textX = cx - textWidth / 2 - 6;
  const textY = cy - textHeight - 8;

  ctx.fillStyle = 'rgba(0, 0, 0, 0.72)';
  ctx.fillRect(textX, textY, textWidth + 12, textHeight);
  ctx.fillStyle = '#fff8cc';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, textX + 6, textY + textHeight / 2);
  ctx.restore();
}

function drawOverlay() {
  const canvas = canvasRef.value;
  const wrapper = wrapperRef.value;
  if (!canvas || !wrapper) {
    return;
  }

  const cssWidth = wrapper.clientWidth;
  const cssHeight = wrapper.clientHeight;
  if (cssWidth <= 0 || cssHeight <= 0) {
    return;
  }

  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${cssHeight}px`;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(cssHeight * dpr);

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return;
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, cssHeight);

  if (props.showDetectedEdges) {
    if (props.leftFrameData) {
      ctx.save();
      ctx.strokeStyle = 'rgba(34, 211, 238, 0.9)';
      ctx.lineWidth = 2.5;
      drawPath(
        ctx,
        props.leftFrameData.pt,
        props.leftVideoWidth,
        props.leftVideoHeight,
        cssWidth,
        cssHeight
      );
      drawPath(
        ctx,
        props.leftFrameData.pb,
        props.leftVideoWidth,
        props.leftVideoHeight,
        cssWidth,
        cssHeight
      );
      ctx.restore();
    }
    if (props.rightFrameData) {
      ctx.save();
      ctx.strokeStyle = 'rgba(251, 146, 60, 0.9)';
      ctx.lineWidth = 2.5;
      drawPath(
        ctx,
        props.rightFrameData.pt,
        props.rightVideoWidth,
        props.rightVideoHeight,
        cssWidth,
        cssHeight
      );
      drawPath(
        ctx,
        props.rightFrameData.pb,
        props.rightVideoWidth,
        props.rightVideoHeight,
        cssWidth,
        cssHeight
      );
      ctx.restore();
    }
  }

  if (props.highlightedPointIndex === null) {
    return;
  }

  if (
    props.leftFrameData?.mpp &&
    props.highlightedPointIndex < props.leftFrameData.mpp.length
  ) {
    const leftPair = props.leftFrameData.mpp[props.highlightedPointIndex];
    if (leftPair && leftPair.length >= 7) {
      const leftDistanceMm = leftPair[6] / Math.max(props.leftPixelToMmFactor, 1e-9);
      drawHighlightedPair(
        ctx,
        leftPair,
        props.leftVideoWidth,
        props.leftVideoHeight,
        cssWidth,
        cssHeight,
        `L ${leftDistanceMm.toFixed(2)} mm`,
        false
      );
    }
  }

  if (
    props.rightFrameData?.mpp &&
    props.highlightedPointIndex < props.rightFrameData.mpp.length
  ) {
    const rightPair = props.rightFrameData.mpp[props.highlightedPointIndex];
    if (rightPair && rightPair.length >= 7) {
      const rightDistanceMm = rightPair[6] / Math.max(props.rightPixelToMmFactor, 1e-9);
      drawHighlightedPair(
        ctx,
        rightPair,
        props.rightVideoWidth,
        props.rightVideoHeight,
        cssWidth,
        cssHeight,
        `R ${rightDistanceMm.toFixed(2)} mm`,
        true
      );
    }
  }
}

function setupResizeObserver() {
  if (!wrapperRef.value) {
    return;
  }

  resizeObserver.value = new ResizeObserver(() => {
    drawOverlay();
  });
  resizeObserver.value.observe(wrapperRef.value);
}

onMounted(() => {
  setupResizeObserver();
  drawOverlay();
});

onUnmounted(() => {
  if (resizeObserver.value) {
    resizeObserver.value.disconnect();
  }
});

watch(
  () => [
    props.leftFrameImageUrl,
    props.rightFrameImageUrl,
    props.leftFrameData,
    props.rightFrameData,
    props.showDetectedEdges,
    props.highlightedPointIndex,
    props.overlayAlpha,
  ],
  () => {
    drawOverlay();
  },
  { deep: true }
);
</script>

<template>
  <div class="frame-diff-overlay">
    <div ref="wrapperRef" class="frame-stack" :style="{ aspectRatio: `${aspectRatio}` }">
      <img
        v-if="leftFrameImageUrl"
        ref="leftImageRef"
        :src="leftFrameImageUrl"
        alt="Left frame"
        class="frame-image base-frame"
        @load="drawOverlay"
      />
      <img
        v-if="rightFrameImageUrl"
        ref="rightImageRef"
        :src="rightFrameImageUrl"
        alt="Right frame"
        class="frame-image overlay-frame"
        :style="{ opacity: overlayAlpha }"
        @load="drawOverlay"
      />
      <canvas ref="canvasRef" class="overlay-canvas" />
      <div v-if="!leftFrameImageUrl || !rightFrameImageUrl" class="missing-frame">
        Frame preview unavailable.
      </div>
    </div>
  </div>
</template>

<style scoped>
.frame-diff-overlay {
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-secondary);
  overflow: hidden;
}

.frame-stack {
  position: relative;
  width: 100%;
  background: #000;
}

.frame-image {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  object-fit: fill;
}

.base-frame {
  opacity: 1;
}

.overlay-frame {
  mix-blend-mode: normal;
}

.overlay-canvas {
  position: absolute;
  inset: 0;
  width: 100%;
  height: 100%;
  pointer-events: none;
}

.missing-frame {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: var(--text-secondary);
  font-size: 0.85rem;
  background: rgba(0, 0, 0, 0.72);
}
</style>

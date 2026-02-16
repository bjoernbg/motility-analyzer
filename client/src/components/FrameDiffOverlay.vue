<script setup lang="ts">
import { computed, onMounted, onUnmounted, ref, watch } from 'vue';
import type { FrameData } from '../lib/api';

interface FrameOverlayAlignmentContext {
  leftAnchorXPx: number;
  rightAnchorXPx: number;
  targetOffsetMm: number;
  targetWindowWidthMm: number;
  leftTubeEndXLeftPx?: number | null;
  leftTubeEndXRightPx?: number | null;
  leftTubeEndYTopPx?: number | null;
  leftTubeEndYBottomPx?: number | null;
  rightTubeEndXLeftPx?: number | null;
  rightTubeEndXRightPx?: number | null;
  rightTubeEndYTopPx?: number | null;
  rightTubeEndYBottomPx?: number | null;
}

interface HorizontalTransform {
  translateX: number;
  scaleX: number;
  translateY: number;
  scaleY: number;
  sourceWidth: number;
  sourceHeight: number;
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
  showDetectedEdges: boolean;
  highlightedPointIndex: number | null;
  overlayAlpha: number;
  aspectRatio: number;
  alignmentContext: FrameOverlayAlignmentContext;
}>();

const wrapperRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const leftImageRef = ref<HTMLImageElement | null>(null);
const rightImageRef = ref<HTMLImageElement | null>(null);
const leftImageLoaded = ref(false);
const rightImageLoaded = ref(false);
const resizeObserver = ref<ResizeObserver | null>(null);
const cssViewportHeightPx = ref(0);
const cssCanvasTopPx = ref(0);
const cssCanvasHeightPx = ref(0);

const canRenderFrames = computed(
  () =>
    Boolean(
      props.leftFrameImageUrl &&
      props.rightFrameImageUrl &&
      leftImageLoaded.value &&
      rightImageLoaded.value
    )
);

const frameStackStyle = computed(() => {
  if (cssViewportHeightPx.value > 0) {
    return {
      height: `${cssViewportHeightPx.value}px`,
    };
  }
  return {
    aspectRatio: `${props.aspectRatio}`,
  };
});

const canvasStyle = computed(() => ({
  top: `${cssCanvasTopPx.value}px`,
  height: `${Math.max(1, cssCanvasHeightPx.value)}px`,
}));

function createTransform(
  sourceWidth: number,
  sourceHeight: number,
  anchorXPx: number,
  pixelsPerMm: number,
  targetOffsetMm: number,
  targetWindowWidthMm: number,
  canvasWidth: number
): HorizontalTransform {
  const safeWidth = Math.max(1, sourceWidth);
  const safeHeight = Math.max(1, sourceHeight);
  const safePixelsPerMm = Math.max(1e-9, pixelsPerMm);
  const safeWindowMm = Math.max(1e-9, targetWindowWidthMm);
  const canonicalLeftMm = -(targetOffsetMm + targetWindowWidthMm);

  const scaleX = canvasWidth / (safePixelsPerMm * safeWindowMm);
  const translateX = (
    ((-anchorXPx / safePixelsPerMm) - canonicalLeftMm) /
    safeWindowMm
  ) * canvasWidth;

  return {
    translateX,
    scaleX,
    translateY: 0,
    scaleY: 1,
    sourceWidth: safeWidth,
    sourceHeight: safeHeight,
  };
}

function fitTransformsToCanvas(
  transforms: HorizontalTransform[],
  canvasWidth: number
): HorizontalTransform[] {
  if (transforms.length === 0 || canvasWidth <= 0) {
    return transforms;
  }

  let minX = Number.POSITIVE_INFINITY;
  let maxX = Number.NEGATIVE_INFINITY;
  for (const transform of transforms) {
    const left = transform.translateX;
    const right = transform.translateX + transform.sourceWidth * transform.scaleX;
    if (!Number.isFinite(left) || !Number.isFinite(right)) {
      return transforms;
    }
    minX = Math.min(minX, left, right);
    maxX = Math.max(maxX, left, right);
  }

  const span = maxX - minX;
  if (!Number.isFinite(span) || span <= 1e-9) {
    return transforms;
  }

  const paddingPx = Math.max(8, canvasWidth * 0.02);
  const availableWidth = Math.max(1, canvasWidth - 2 * paddingPx);
  const fitScale = availableWidth / span;

  return transforms.map((transform) => ({
    ...transform,
    translateX: paddingPx + (transform.translateX - minX) * fitScale,
    scaleX: transform.scaleX * fitScale,
  }));
}

function fitTransformsVertically(
  transforms: HorizontalTransform[],
  canvasHeight: number
): HorizontalTransform[] {
  if (transforms.length === 0 || canvasHeight <= 0) {
    return transforms;
  }

  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const transform of transforms) {
    const top = transform.translateY;
    const bottom = transform.translateY + transform.sourceHeight * transform.scaleY;
    if (!Number.isFinite(top) || !Number.isFinite(bottom)) {
      return transforms;
    }
    minY = Math.min(minY, top, bottom);
    maxY = Math.max(maxY, top, bottom);
  }

  const span = maxY - minY;
  if (!Number.isFinite(span) || span <= 1e-9) {
    return transforms;
  }

  const paddingPx = Math.max(8, canvasHeight * 0.02);
  const availableHeight = Math.max(1, canvasHeight - 2 * paddingPx);
  const fitScale = availableHeight / span;

  return transforms.map((transform) => ({
    ...transform,
    translateY: paddingPx + (transform.translateY - minY) * fitScale,
    scaleY: transform.scaleY * fitScale,
  }));
}

function collectFrameYRange(
  frameData: FrameData | null,
  tubeYTop: number | null | undefined,
  tubeYBottom: number | null | undefined
): [number, number] | null {
  const ys: number[] = [];

  if (frameData) {
    for (const [, y] of frameData.pt ?? []) {
      if (Number.isFinite(y)) ys.push(y);
    }
    for (const [, y] of frameData.pb ?? []) {
      if (Number.isFinite(y)) ys.push(y);
    }
  }

  if (typeof tubeYTop === 'number' && Number.isFinite(tubeYTop)) {
    ys.push(tubeYTop);
  }
  if (typeof tubeYBottom === 'number' && Number.isFinite(tubeYBottom)) {
    ys.push(tubeYBottom);
  }

  if (ys.length === 0) {
    return null;
  }

  let minY = Number.POSITIVE_INFINITY;
  let maxY = Number.NEGATIVE_INFINITY;
  for (const y of ys) {
    minY = Math.min(minY, y);
    maxY = Math.max(maxY, y);
  }
  if (!Number.isFinite(minY) || !Number.isFinite(maxY) || maxY <= minY) {
    return null;
  }
  return [minY, maxY];
}

function getVerticalClipBounds(
  transforms: HorizontalTransform[],
  sourceYRanges: Array<[number, number] | null>,
  paddingPx: number
): [number, number] | null {
  if (transforms.length === 0 || transforms.length !== sourceYRanges.length) {
    return null;
  }

  let cropTop = Number.POSITIVE_INFINITY;
  let cropBottom = Number.NEGATIVE_INFINITY;

  for (let index = 0; index < transforms.length; index += 1) {
    const transform = transforms[index];
    const range = sourceYRanges[index];
    if (!transform || !range) {
      continue;
    }
    const [sourceTop, sourceBottom] = range;
    const top = transform.translateY + sourceTop * transform.scaleY;
    const bottom = transform.translateY + sourceBottom * transform.scaleY;
    cropTop = Math.min(cropTop, top, bottom);
    cropBottom = Math.max(cropBottom, top, bottom);
  }

  if (!Number.isFinite(cropTop) || !Number.isFinite(cropBottom) || cropBottom <= cropTop) {
    return null;
  }

  cropTop -= Math.max(0, paddingPx);
  cropBottom += Math.max(0, paddingPx);

  if (!Number.isFinite(cropTop) || !Number.isFinite(cropBottom) || cropBottom <= cropTop) {
    return null;
  }
  return [cropTop, cropBottom];
}

function samplePathYAtX(
  points: Array<[number, number]>,
  xTarget: number
): number | null {
  if (points.length === 0) {
    return null;
  }
  if (points.length === 1) {
    return points[0]?.[1] ?? null;
  }

  for (let index = 1; index < points.length; index += 1) {
    const prev = points[index - 1];
    const curr = points[index];
    if (!prev || !curr) {
      continue;
    }
    const minX = Math.min(prev[0], curr[0]);
    const maxX = Math.max(prev[0], curr[0]);
    if (xTarget < minX || xTarget > maxX) {
      continue;
    }
    const dx = curr[0] - prev[0];
    if (Math.abs(dx) < 1e-9) {
      return (prev[1] + curr[1]) / 2;
    }
    const t = (xTarget - prev[0]) / dx;
    return prev[1] + t * (curr[1] - prev[1]);
  }

  let nearestY: number | null = null;
  let nearestDistance = Number.POSITIVE_INFINITY;
  for (const [x, y] of points) {
    const distance = Math.abs(x - xTarget);
    if (distance < nearestDistance) {
      nearestDistance = distance;
      nearestY = y;
    }
  }
  return nearestY;
}

function getReferenceCenterY(frameData: FrameData | null, xTarget: number): number | null {
  if (!frameData) {
    return null;
  }

  const center = samplePathYAtX(frameData.pc ?? [], xTarget);
  if (center !== null) {
    return center;
  }

  const top = samplePathYAtX(frameData.pt ?? [], xTarget);
  const bottom = samplePathYAtX(frameData.pb ?? [], xTarget);
  if (top !== null && bottom !== null) {
    return (top + bottom) / 2;
  }
  if (top !== null) {
    return top;
  }
  if (bottom !== null) {
    return bottom;
  }
  return null;
}

function clamp(value: number, low: number, high: number): number {
  return Math.max(low, Math.min(high, value));
}

function hasValidTubeBounds(yTop: number | null | undefined, yBottom: number | null | undefined): boolean {
  return (
    typeof yTop === 'number' &&
    typeof yBottom === 'number' &&
    Number.isFinite(yTop) &&
    Number.isFinite(yBottom) &&
    yBottom > yTop
  );
}

function projectPoint(
  x: number,
  y: number,
  transform: HorizontalTransform
): [number, number] {
  const projectedX = transform.translateX + x * transform.scaleX;
  const projectedY = transform.translateY + y * transform.scaleY;
  return [projectedX, projectedY];
}

function drawPath(
  ctx: CanvasRenderingContext2D,
  points: Array<[number, number]>,
  transform: HorizontalTransform
) {
  if (points.length === 0) {
    return;
  }

  let started = false;
  for (const [x, y] of points) {
    const [px, py] = projectPoint(x, y, transform);
    if (!started) {
      ctx.beginPath();
      ctx.moveTo(px, py);
      started = true;
    } else {
      ctx.lineTo(px, py);
    }
  }
  if (started) {
    ctx.stroke();
  }
}

function drawHighlightedPair(
  ctx: CanvasRenderingContext2D,
  pair: [number, number, number, number, number, number, number],
  transform: HorizontalTransform,
  label: string,
  dashed: boolean
) {
  const [, , tx, ty, bx, by] = pair;
  const top = projectPoint(tx, ty, transform);
  const bottom = projectPoint(bx, by, transform);

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

  const centerX = (top[0] + bottom[0]) / 2;
  const centerY = (top[1] + bottom[1]) / 2;
  ctx.font = 'bold 12px sans-serif';
  const textWidth = ctx.measureText(label).width;
  const textHeight = 18;
  const textX = centerX - textWidth / 2 - 6;
  const textY = centerY - textHeight - 8;

  ctx.fillStyle = 'rgba(0, 0, 0, 0.72)';
  ctx.fillRect(textX, textY, textWidth + 12, textHeight);
  ctx.fillStyle = '#fff8cc';
  ctx.textBaseline = 'middle';
  ctx.fillText(label, textX + 6, textY + textHeight / 2);
  ctx.restore();
}

function drawFrameImage(
  ctx: CanvasRenderingContext2D,
  image: HTMLImageElement,
  transform: HorizontalTransform,
  canvasWidth: number,
  alpha: number
) {
  const srcWidth = Math.max(1, image.naturalWidth || transform.sourceWidth);
  const srcHeight = Math.max(1, image.naturalHeight || transform.sourceHeight);
  const scaleX = transform.scaleX;

  if (!Number.isFinite(scaleX) || scaleX <= 0) {
    return;
  }

  // Draw only the horizontal source slice that maps into the visible canvas.
  // This prevents massive draw widths when canonical windows are narrow.
  const sourceVisibleLeft = (0 - transform.translateX) / scaleX;
  const sourceVisibleRight = (canvasWidth - transform.translateX) / scaleX;
  const sourceStart = Math.max(
    0,
    Math.min(srcWidth, Math.floor(Math.min(sourceVisibleLeft, sourceVisibleRight)))
  );
  const sourceEnd = Math.max(
    0,
    Math.min(srcWidth, Math.ceil(Math.max(sourceVisibleLeft, sourceVisibleRight)))
  );
  const sourceDrawWidth = sourceEnd - sourceStart;
  if (sourceDrawWidth <= 0) {
    return;
  }

  const destX = transform.translateX + sourceStart * scaleX;
  const destWidth = sourceDrawWidth * scaleX;
  const destY = transform.translateY;
  const destHeight = transform.sourceHeight * transform.scaleY;

  ctx.save();
  ctx.globalAlpha = Math.max(0, Math.min(1, alpha));
  ctx.drawImage(
    image,
    sourceStart,
    0,
    sourceDrawWidth,
    srcHeight,
    destX,
    destY,
    destWidth,
    destHeight
  );
  ctx.restore();
}

function drawTubeEndBox(
  ctx: CanvasRenderingContext2D,
  transform: HorizontalTransform,
  anchorXPx: number,
  centerYPx: number | null,
  bounds: {
    xLeft: number | null;
    xRight: number | null;
    yTop: number | null;
    yBottom: number | null;
  },
  color: string,
  label: string
) {
  const hasExactBounds =
    typeof bounds.xLeft === 'number' &&
    typeof bounds.xRight === 'number' &&
    bounds.xRight > bounds.xLeft &&
    typeof bounds.yTop === 'number' &&
    typeof bounds.yBottom === 'number' &&
    bounds.yBottom > bounds.yTop;

  let xLeft: number;
  let xRight: number;
  let yTop: number;
  let yBottom: number;

  if (hasExactBounds) {
    xLeft = clamp(bounds.xLeft!, 0, transform.sourceWidth);
    xRight = clamp(bounds.xRight!, xLeft + 1, transform.sourceWidth);
    yTop = clamp(bounds.yTop!, 0, transform.sourceHeight);
    yBottom = clamp(bounds.yBottom!, yTop + 1, transform.sourceHeight);
  } else {
    const boxWidthPx = clamp(transform.sourceWidth * 0.04, 12, 56);
    const boxHeightPx = clamp(transform.sourceHeight * 0.22, 48, 180);
    const clampedAnchorX = clamp(anchorXPx, 0, transform.sourceWidth);
    const yCenter = centerYPx ?? transform.sourceHeight / 2;
    xLeft = clamp(
      clampedAnchorX - boxWidthPx / 2,
      0,
      Math.max(0, transform.sourceWidth - boxWidthPx)
    );
    yTop = clamp(
      yCenter - boxHeightPx / 2,
      0,
      Math.max(0, transform.sourceHeight - boxHeightPx)
    );
    xRight = xLeft + boxWidthPx;
    yBottom = yTop + boxHeightPx;
  }

  const [topLeftX, topLeftY] = projectPoint(xLeft, yTop, transform);
  const [bottomRightX, bottomRightY] = projectPoint(xRight, yBottom, transform);
  const drawLeft = Math.min(topLeftX, bottomRightX);
  const drawTop = Math.min(topLeftY, bottomRightY);
  const drawWidth = Math.abs(bottomRightX - topLeftX);
  const drawHeight = Math.abs(bottomRightY - topLeftY);

  if (drawWidth <= 0 || drawHeight <= 0) {
    return;
  }

  ctx.save();
  ctx.strokeStyle = color;
  ctx.fillStyle = color;
  ctx.lineWidth = 2;
  ctx.setLineDash([6, 4]);
  ctx.strokeRect(drawLeft, drawTop, drawWidth, drawHeight);
  ctx.setLineDash([]);

  ctx.font = 'bold 11px sans-serif';
  const textWidth = ctx.measureText(label).width;
  const textHeight = 16;
  const textX = drawLeft;
  const textY = Math.max(0, drawTop - textHeight - 4);
  ctx.fillStyle = 'rgba(0, 0, 0, 0.72)';
  ctx.fillRect(textX - 4, textY, textWidth + 8, textHeight);
  ctx.fillStyle = color;
  ctx.textBaseline = 'middle';
  ctx.fillText(label, textX, textY + textHeight / 2);
  ctx.restore();
}

function drawScene() {
  const wrapper = wrapperRef.value;
  const canvas = canvasRef.value;
  const leftImage = leftImageRef.value;
  const rightImage = rightImageRef.value;

  if (!wrapper || !canvas) {
    return;
  }

  const cssWidth = wrapper.clientWidth;
  if (cssWidth <= 0) {
    return;
  }
  const baseAspectRatio = Math.max(0.01, props.aspectRatio);
  const fullHeight = Math.max(1, cssWidth / baseAspectRatio);

  const dpr = window.devicePixelRatio || 1;
  canvas.style.width = `${cssWidth}px`;
  canvas.style.height = `${fullHeight}px`;
  canvas.width = Math.round(cssWidth * dpr);
  canvas.height = Math.round(fullHeight * dpr);

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    return;
  }

  ctx.setTransform(dpr, 0, 0, dpr, 0, 0);
  ctx.clearRect(0, 0, cssWidth, fullHeight);
  ctx.fillStyle = '#000';
  ctx.fillRect(0, 0, cssWidth, fullHeight);

  if (!canRenderFrames.value || !leftImage || !rightImage) {
    return;
  }

  const leftWidth = Math.max(1, props.leftVideoWidth || leftImage.naturalWidth);
  const leftHeight = Math.max(1, props.leftVideoHeight || leftImage.naturalHeight);
  const rightWidth = Math.max(1, props.rightVideoWidth || rightImage.naturalWidth);
  const rightHeight = Math.max(1, props.rightVideoHeight || rightImage.naturalHeight);

  const leftBaseTransform = createTransform(
    leftWidth,
    leftHeight,
    props.alignmentContext.leftAnchorXPx,
    props.leftPixelToMmFactor,
    props.alignmentContext.targetOffsetMm,
    props.alignmentContext.targetWindowWidthMm,
    cssWidth
  );
  const rightBaseTransform = createTransform(
    rightWidth,
    rightHeight,
    props.alignmentContext.rightAnchorXPx,
    props.rightPixelToMmFactor,
    props.alignmentContext.targetOffsetMm,
    props.alignmentContext.targetWindowWidthMm,
    cssWidth
  );
  leftBaseTransform.scaleY = fullHeight / leftBaseTransform.sourceHeight;
  rightBaseTransform.scaleY = fullHeight / rightBaseTransform.sourceHeight;

  const leftTubeYTop = props.alignmentContext.leftTubeEndYTopPx ?? null;
  const leftTubeYBottom = props.alignmentContext.leftTubeEndYBottomPx ?? null;
  const rightTubeYTop = props.alignmentContext.rightTubeEndYTopPx ?? null;
  const rightTubeYBottom = props.alignmentContext.rightTubeEndYBottomPx ?? null;
  const canAlignTubeBoundsY =
    hasValidTubeBounds(leftTubeYTop, leftTubeYBottom) &&
    hasValidTubeBounds(rightTubeYTop, rightTubeYBottom);

  const leftReferenceX =
    props.alignmentContext.leftAnchorXPx -
    props.alignmentContext.targetOffsetMm *
      Math.max(props.leftPixelToMmFactor, 1e-9);
  const rightReferenceX =
    props.alignmentContext.rightAnchorXPx -
    props.alignmentContext.targetOffsetMm *
      Math.max(props.rightPixelToMmFactor, 1e-9);
  const leftReferenceY = getReferenceCenterY(props.leftFrameData, leftReferenceX);
  const rightReferenceY = getReferenceCenterY(props.rightFrameData, rightReferenceX);
  const leftAnchorCenterY = canAlignTubeBoundsY
    ? (leftTubeYTop! + leftTubeYBottom!) / 2
    : getReferenceCenterY(props.leftFrameData, props.alignmentContext.leftAnchorXPx);
  const rightAnchorCenterY = canAlignTubeBoundsY
    ? (rightTubeYTop! + rightTubeYBottom!) / 2
    : getReferenceCenterY(props.rightFrameData, props.alignmentContext.rightAnchorXPx);

  if (canAlignTubeBoundsY) {
    const leftTopCanvas =
      leftBaseTransform.translateY + leftTubeYTop! * leftBaseTransform.scaleY;
    const leftBottomCanvas =
      leftBaseTransform.translateY + leftTubeYBottom! * leftBaseTransform.scaleY;
    const leftTubeSpanCanvas = leftBottomCanvas - leftTopCanvas;
    const rightTubeSpanPx = rightTubeYBottom! - rightTubeYTop!;

    if (leftTubeSpanCanvas > 1e-9 && rightTubeSpanPx > 1e-9) {
      rightBaseTransform.scaleY = leftTubeSpanCanvas / rightTubeSpanPx;
      rightBaseTransform.translateY =
        leftTopCanvas - rightTubeYTop! * rightBaseTransform.scaleY;
    }
  } else if (leftReferenceY !== null && rightReferenceY !== null) {
    const leftCanvasY =
      leftBaseTransform.translateY + leftReferenceY * leftBaseTransform.scaleY;
    const rightCanvasY =
      rightBaseTransform.translateY + rightReferenceY * rightBaseTransform.scaleY;
    rightBaseTransform.translateY += leftCanvasY - rightCanvasY;
  }

  const xFittedTransforms = fitTransformsToCanvas(
    [leftBaseTransform, rightBaseTransform],
    cssWidth
  );
  const leftSourceYRange = collectFrameYRange(
    props.leftFrameData,
    leftTubeYTop,
    leftTubeYBottom
  );
  const rightSourceYRange = collectFrameYRange(
    props.rightFrameData,
    rightTubeYTop,
    rightTubeYBottom
  );
  const fittedTransforms = fitTransformsVertically(xFittedTransforms, fullHeight);
  const leftTransform = fittedTransforms[0] ?? leftBaseTransform;
  const rightTransform = fittedTransforms[1] ?? rightBaseTransform;
  const verticalClipBounds = getVerticalClipBounds(
    fittedTransforms,
    [leftSourceYRange, rightSourceYRange],
    50
  );
  const clipTop = verticalClipBounds
    ? clamp(verticalClipBounds[0], 0, fullHeight)
    : null;
  const clipBottom = verticalClipBounds
    ? clamp(verticalClipBounds[1], 0, fullHeight)
    : null;
  const hasValidClip =
    clipTop !== null &&
    clipBottom !== null &&
    Number.isFinite(clipTop) &&
    Number.isFinite(clipBottom) &&
    clipBottom > clipTop;

  if (hasValidClip) {
    cssCanvasTopPx.value = -clipTop;
    cssCanvasHeightPx.value = fullHeight;
    cssViewportHeightPx.value = Math.max(1, clipBottom - clipTop);
  } else {
    cssCanvasTopPx.value = 0;
    cssCanvasHeightPx.value = fullHeight;
    cssViewportHeightPx.value = fullHeight;
  }

  drawFrameImage(ctx, leftImage, leftTransform, cssWidth, 1);
  drawFrameImage(
    ctx,
    rightImage,
    rightTransform,
    cssWidth,
    props.overlayAlpha
  );

  drawTubeEndBox(
    ctx,
    leftTransform,
    props.alignmentContext.leftAnchorXPx,
    leftAnchorCenterY,
    {
      xLeft: props.alignmentContext.leftTubeEndXLeftPx ?? null,
      xRight: props.alignmentContext.leftTubeEndXRightPx ?? null,
      yTop: props.alignmentContext.leftTubeEndYTopPx ?? null,
      yBottom: props.alignmentContext.leftTubeEndYBottomPx ?? null,
    },
    'rgba(34, 211, 238, 0.95)',
    'L tube end'
  );
  drawTubeEndBox(
    ctx,
    rightTransform,
    props.alignmentContext.rightAnchorXPx,
    rightAnchorCenterY,
    {
      xLeft: props.alignmentContext.rightTubeEndXLeftPx ?? null,
      xRight: props.alignmentContext.rightTubeEndXRightPx ?? null,
      yTop: props.alignmentContext.rightTubeEndYTopPx ?? null,
      yBottom: props.alignmentContext.rightTubeEndYBottomPx ?? null,
    },
    'rgba(251, 146, 60, 0.95)',
    'R tube end'
  );

  if (props.showDetectedEdges) {
    if (props.leftFrameData) {
      ctx.save();
      ctx.strokeStyle = 'rgba(34, 211, 238, 0.9)';
      ctx.lineWidth = 2.5;
      drawPath(ctx, props.leftFrameData.pt, leftTransform);
      drawPath(ctx, props.leftFrameData.pb, leftTransform);
      ctx.restore();
    }

    if (props.rightFrameData) {
      ctx.save();
      ctx.strokeStyle = 'rgba(251, 146, 60, 0.9)';
      ctx.lineWidth = 2.5;
      drawPath(ctx, props.rightFrameData.pt, rightTransform);
      drawPath(ctx, props.rightFrameData.pb, rightTransform);
      ctx.restore();
    }
  }

  if (props.highlightedPointIndex !== null) {
    if (
      props.leftFrameData?.mpp &&
      props.highlightedPointIndex < props.leftFrameData.mpp.length
    ) {
      const leftPair = props.leftFrameData.mpp[props.highlightedPointIndex];
      if (leftPair && leftPair.length >= 7) {
        const distanceMm = leftPair[6] / Math.max(props.leftPixelToMmFactor, 1e-9);
        drawHighlightedPair(
          ctx,
          leftPair,
          leftTransform,
          `L ${distanceMm.toFixed(2)} mm`,
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
        const distanceMm = rightPair[6] / Math.max(props.rightPixelToMmFactor, 1e-9);
        drawHighlightedPair(
          ctx,
          rightPair,
          rightTransform,
          `R ${distanceMm.toFixed(2)} mm`,
          true
        );
      }
    }
  }
}

function handleImageLoad(side: 'left' | 'right') {
  if (side === 'left') {
    leftImageLoaded.value = true;
  } else {
    rightImageLoaded.value = true;
  }
  drawScene();
}

function setupResizeObserver() {
  if (!wrapperRef.value) {
    return;
  }

  resizeObserver.value = new ResizeObserver(() => {
    drawScene();
  });
  resizeObserver.value.observe(wrapperRef.value);
}

onMounted(() => {
  setupResizeObserver();
  drawScene();
});

onUnmounted(() => {
  if (resizeObserver.value) {
    resizeObserver.value.disconnect();
  }
});

watch(
  () => [props.leftFrameImageUrl, props.rightFrameImageUrl],
  () => {
    leftImageLoaded.value = false;
    rightImageLoaded.value = false;
    drawScene();
  }
);

watch(
  () => [
    props.leftFrameData,
    props.rightFrameData,
    props.showDetectedEdges,
    props.highlightedPointIndex,
    props.overlayAlpha,
    props.leftPixelToMmFactor,
    props.rightPixelToMmFactor,
    props.leftVideoWidth,
    props.leftVideoHeight,
    props.rightVideoWidth,
    props.rightVideoHeight,
    props.alignmentContext.leftAnchorXPx,
    props.alignmentContext.rightAnchorXPx,
    props.alignmentContext.targetOffsetMm,
    props.alignmentContext.targetWindowWidthMm,
    props.alignmentContext.leftTubeEndXLeftPx,
    props.alignmentContext.leftTubeEndXRightPx,
    props.alignmentContext.leftTubeEndYTopPx,
    props.alignmentContext.leftTubeEndYBottomPx,
    props.alignmentContext.rightTubeEndXLeftPx,
    props.alignmentContext.rightTubeEndXRightPx,
    props.alignmentContext.rightTubeEndYTopPx,
    props.alignmentContext.rightTubeEndYBottomPx,
  ],
  () => {
    drawScene();
  },
  { deep: true }
);
</script>

<template>
  <div class="frame-diff-overlay">
    <div
      ref="wrapperRef"
      class="frame-stack"
      :style="frameStackStyle"
    >
      <canvas ref="canvasRef" class="frame-canvas" :style="canvasStyle" />

      <img
        v-if="leftFrameImageUrl"
        ref="leftImageRef"
        :src="leftFrameImageUrl"
        alt="Left frame source"
        class="source-image"
        @load="handleImageLoad('left')"
      />
      <img
        v-if="rightFrameImageUrl"
        ref="rightImageRef"
        :src="rightFrameImageUrl"
        alt="Right frame source"
        class="source-image"
        @load="handleImageLoad('right')"
      />

      <div v-if="!canRenderFrames" class="missing-frame">
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
  overflow: hidden;
}

.frame-canvas {
  position: absolute;
  left: 0;
  right: 0;
  width: 100%;
  display: block;
}

.source-image {
  position: absolute;
  width: 1px;
  height: 1px;
  opacity: 0;
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

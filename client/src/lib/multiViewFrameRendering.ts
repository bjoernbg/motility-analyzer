import type { FrameData } from './api';

export interface SidebarFrameViewport {
  sourceX: number;
  sourceY: number;
  sourceWidth: number;
  sourceHeight: number;
  outputWidth: number;
  outputHeight: number;
  drawOffsetX: number;
  drawOffsetY: number;
  drawWidth: number;
  drawHeight: number;
}

export interface SidebarFrameRenderOptions {
  image: CanvasImageSource;
  videoWidth: number;
  videoHeight: number;
  clipWidth: number;
  clipHeight: number;
  frameData: FrameData | null;
  pixelToMmFactor: number;
  showDetectedEdges: boolean;
  showSelectedPointMeasurements: boolean;
  highlightedPointIndex: number | null;
  windowLeft?: number | null;
  windowRight?: number | null;
}

function drawPath(
  ctx: CanvasRenderingContext2D,
  scaleX: number,
  scaleY: number,
  points: Array<[number, number]>,
): void {
  if (points.length === 0) {
    return;
  }

  const firstPoint = points[0];
  if (!firstPoint) {
    return;
  }

  ctx.beginPath();
  ctx.moveTo(firstPoint[0] * scaleX, firstPoint[1] * scaleY);
  for (let index = 1; index < points.length; index += 1) {
    const point = points[index];
    if (!point) {
      continue;
    }
    ctx.lineTo(point[0] * scaleX, point[1] * scaleY);
  }
  ctx.stroke();
}

export function resolveSidebarFrameViewport(
  videoWidth: number,
  videoHeight: number,
  clipWidth: number,
  clipHeight: number,
  windowLeft?: number | null,
  windowRight?: number | null,
): SidebarFrameViewport {
  const safeVideoWidth = Math.max(1, videoWidth);
  const safeVideoHeight = Math.max(1, videoHeight);
  const safeClipWidth = Math.max(1, clipWidth);
  const safeClipHeight = Math.max(1, clipHeight);

  const hasWindow =
    typeof windowLeft === 'number' &&
    typeof windowRight === 'number' &&
    windowRight > windowLeft;

  const baseLeft = hasWindow ? windowLeft : 0;
  const baseRight = hasWindow ? windowRight : safeVideoWidth;
  const windowWidth = Math.max(1, baseRight - baseLeft);
  const padding = hasWindow ? windowWidth * 0.05 : 0;
  const sourceX = Math.max(0, baseLeft - padding);
  const sourceRight = Math.min(safeVideoWidth, baseRight + padding);
  const sourceWidth = Math.max(1, sourceRight - sourceX);
  const scale = safeClipWidth / sourceWidth;
  const scaledImageHeight = safeVideoHeight * scale;

  if (scaledImageHeight >= safeClipHeight) {
    const visibleSourceHeight = safeClipHeight / scale;
    const sourceY = Math.max(0, (safeVideoHeight - visibleSourceHeight) / 2);

    return {
      sourceX,
      sourceY,
      sourceWidth,
      sourceHeight: Math.min(safeVideoHeight, visibleSourceHeight),
      outputWidth: sourceWidth,
      outputHeight: Math.max(1, Math.round(visibleSourceHeight)),
      drawOffsetX: 0,
      drawOffsetY: 0,
      drawWidth: sourceWidth,
      drawHeight: Math.max(1, Math.round(visibleSourceHeight)),
    };
  }

  const outputHeight = Math.max(1, Math.round((sourceWidth * safeClipHeight) / safeClipWidth));
  const drawHeight = Math.max(1, Math.round(scaledImageHeight / scale));
  const drawOffsetY = Math.max(0, Math.round((outputHeight - drawHeight) / 2));

  return {
    sourceX,
    sourceY: 0,
    sourceWidth,
    sourceHeight: safeVideoHeight,
    outputWidth: sourceWidth,
    outputHeight,
    drawOffsetX: 0,
    drawOffsetY,
    drawWidth: sourceWidth,
    drawHeight,
  };
}

export function renderSidebarFrameToCanvas({
  image,
  videoWidth,
  videoHeight,
  clipWidth,
  clipHeight,
  frameData,
  pixelToMmFactor,
  showDetectedEdges,
  showSelectedPointMeasurements,
  highlightedPointIndex,
  windowLeft,
  windowRight,
}: SidebarFrameRenderOptions): HTMLCanvasElement {
  const viewport = resolveSidebarFrameViewport(
    videoWidth,
    videoHeight,
    clipWidth,
    clipHeight,
    windowLeft,
    windowRight,
  );
  const canvas = document.createElement('canvas');
  canvas.width = viewport.outputWidth;
  canvas.height = viewport.outputHeight;

  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('Failed to create sidebar frame export context');
  }

  ctx.fillStyle = '#000000';
  ctx.fillRect(0, 0, canvas.width, canvas.height);
  ctx.drawImage(
    image,
    viewport.sourceX,
    viewport.sourceY,
    viewport.sourceWidth,
    viewport.sourceHeight,
    viewport.drawOffsetX,
    viewport.drawOffsetY,
    viewport.drawWidth,
    viewport.drawHeight,
  );

  const scaleX = viewport.drawWidth / viewport.sourceWidth;
  const scaleY = viewport.drawHeight / viewport.sourceHeight;
  const translateX = viewport.drawOffsetX - viewport.sourceX * scaleX;
  const translateY = viewport.drawOffsetY - viewport.sourceY * scaleY;

  ctx.save();
  ctx.translate(translateX, translateY);

  if (frameData && showDetectedEdges) {
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
    frameData &&
    showSelectedPointMeasurements &&
    highlightedPointIndex !== null &&
    frameData.mpp &&
    frameData.mpp.length > highlightedPointIndex
  ) {
    const pair = frameData.mpp[highlightedPointIndex];
    if (pair && pair.length >= 7) {
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
  }

  ctx.restore();
  return canvas;
}

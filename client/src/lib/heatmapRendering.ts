import type { ContractionEvent, HeatmapMeta } from './api';

export const MIN_HEATMAP_EXPORT_WIDTH = 1920;
export const MIN_HEATMAP_EXPORT_HEIGHT = 1080;

export interface HeatmapRasterOptions {
  width: number;
  height: number;
  values: Float32Array;
  pixelToMmFactor: number;
  heatmapMinMm: number;
  heatmapMaxMm: number;
  colormap: Uint8Array;
}

export interface HeatmapOverlayOptions {
  height: number;
  width: number;
  currentFrame?: number | null;
  showContractionOverlays?: boolean;
  selectedContractionId?: string | null;
  contractionEvents?: readonly ContractionEvent[];
  scaleX: number;
  scaledDataHeight: number;
  offsetX?: number;
  frameMarkerLineWidth?: number;
  arrowLength?: number;
}

export interface HeatmapExportDimensions {
  scaleX: number;
  scaleY: number;
  width: number;
  height: number;
}

function createRenderCanvas(width: number, height: number): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = width;
  canvas.height = height;
  return canvas;
}

export function resolveHeatmapExportDimensions(
  width: number,
  height: number,
  minWidth = MIN_HEATMAP_EXPORT_WIDTH,
  minHeight = MIN_HEATMAP_EXPORT_HEIGHT,
): HeatmapExportDimensions {
  const safeWidth = Math.max(1, width);
  const safeHeight = Math.max(1, height);
  const scaleX = Math.max(1, Math.ceil(minWidth / safeWidth));
  const scaleY = Math.max(1, Math.ceil(minHeight / safeHeight));

  return {
    scaleX,
    scaleY,
    width: safeWidth * scaleX,
    height: safeHeight * scaleY,
  };
}

export function createHeatmapRasterCanvas({
  width,
  height,
  values,
  pixelToMmFactor,
  heatmapMinMm,
  heatmapMaxMm,
  colormap,
}: HeatmapRasterOptions): HTMLCanvasElement {
  const canvas = createRenderCanvas(width, height);
  const ctx = canvas.getContext('2d');
  if (!ctx) {
    throw new Error('Failed to create heatmap canvas context');
  }

  const imageData = ctx.createImageData(width, height);
  const pixels = imageData.data;
  const mmRange = Math.max(1e-9, heatmapMaxMm - heatmapMinMm);

  for (let x = 0; x < width; x += 1) {
    for (let y = 0; y < height; y += 1) {
      const dataIndex = x * height + y;
      const valuePx = values[dataIndex] ?? 0;
      const valueMm = valuePx / pixelToMmFactor;

      let t = (valueMm - heatmapMinMm) / mmRange;
      if (t < 0) {
        t = 0;
      } else if (t > 1) {
        t = 1;
      }

      const colorIndex = Math.floor(t * 255);
      const pixelIndex = (y * width + x) * 4;

      pixels[pixelIndex + 0] = colormap[colorIndex * 3 + 0] ?? 0;
      pixels[pixelIndex + 1] = colormap[colorIndex * 3 + 1] ?? 0;
      pixels[pixelIndex + 2] = colormap[colorIndex * 3 + 2] ?? 0;
      pixels[pixelIndex + 3] = 255;
    }
  }

  ctx.putImageData(imageData, 0, 0);
  return canvas;
}

export function drawHeatmapOverlays(
  ctx: CanvasRenderingContext2D,
  {
    height,
    width,
    currentFrame,
    showContractionOverlays = false,
    selectedContractionId = null,
    contractionEvents = [],
    scaleX,
    scaledDataHeight,
    offsetX = 0,
    frameMarkerLineWidth = 2,
    arrowLength = 20,
  }: HeatmapOverlayOptions,
): void {
  if (showContractionOverlays && contractionEvents.length > 0 && height > 0) {
    const hasSelectedContraction = Boolean(selectedContractionId);

    for (const event of contractionEvents) {
      const [tStart, tEnd] = event.t_range_frames;
      const [yStart, yEnd] = event.y_range_idx;
      const isSelected = selectedContractionId === event.id;

      const xStart = offsetX + tStart * scaleX;
      const xEnd = offsetX + tEnd * scaleX;
      const yStartPx = (yStart / height) * scaledDataHeight;
      const yEndPx = (yEnd / height) * scaledDataHeight;

      ctx.save();
      if (hasSelectedContraction && !isSelected) {
        ctx.globalAlpha = 0.25;
      }

      ctx.strokeStyle = isSelected ? 'rgba(255, 255, 255, 0.95)' : 'rgba(255, 245, 120, 0.85)';
      ctx.lineWidth = isSelected ? 3 : 1.8;
      ctx.setLineDash([]);
      ctx.strokeRect(xStart, yStartPx, xEnd - xStart, yEndPx - yStartPx);

      const { a_idx_per_frame, b } = event.line_fit;
      const yAtStartPx = ((a_idx_per_frame * tStart + b) / height) * scaledDataHeight;
      const yAtEndPx = ((a_idx_per_frame * tEnd + b) / height) * scaledDataHeight;

      ctx.strokeStyle = isSelected ? 'rgba(255, 90, 90, 0.98)' : 'rgba(255, 40, 40, 0.78)';
      ctx.lineWidth = isSelected ? 3 : 2;
      ctx.beginPath();
      ctx.moveTo(xStart, yAtStartPx);
      ctx.lineTo(xEnd, yAtEndPx);
      ctx.stroke();

      const angle = Math.atan2(yAtEndPx - yAtStartPx, xEnd - xStart);
      ctx.beginPath();
      ctx.moveTo(xEnd, yAtEndPx);
      ctx.lineTo(
        xEnd - arrowLength * Math.cos(angle - Math.PI / 6),
        yAtEndPx - arrowLength * Math.sin(angle - Math.PI / 6),
      );
      ctx.moveTo(xEnd, yAtEndPx);
      ctx.lineTo(
        xEnd - arrowLength * Math.cos(angle + Math.PI / 6),
        yAtEndPx - arrowLength * Math.sin(angle + Math.PI / 6),
      );
      ctx.stroke();
      ctx.restore();
    }
  }

  if (
    currentFrame !== null &&
    currentFrame !== undefined &&
    currentFrame >= 0 &&
    currentFrame < width
  ) {
    const frameX = offsetX + currentFrame * scaleX;
    ctx.strokeStyle = '#ffffff';
    ctx.lineWidth = frameMarkerLineWidth;
    ctx.setLineDash([5, 5]);
    ctx.beginPath();
    ctx.moveTo(frameX, 0);
    ctx.lineTo(frameX, scaledDataHeight);
    ctx.stroke();
    ctx.setLineDash([]);
  }
}

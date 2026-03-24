import { describe, expect, it, vi } from 'vitest';

import type { ContractionEvent } from '../api';
import {
  createHeatmapRasterCanvas,
  drawHeatmapOverlays,
  resolveHeatmapExportDimensions,
} from '../heatmapRendering';

function createEvent(): ContractionEvent {
  return {
    id: 'event-1',
    label: 1,
    n_pixels: 10,
    threshold_used: -1,
    t_range_frames: [2, 6],
    y_range_idx: [1, 4],
    duration_s: 0.5,
    height_phys: 5,
    velocity_phys_per_s: 2,
    line_fit: {
      a_idx_per_frame: 0.25,
      b: 1,
    },
    area_exact: 12,
    area_triangle: 12,
    created_at: '2026-03-16T12:00:00',
  };
}

describe('heatmap rendering helpers', () => {
  it('builds a raster canvas at the heatmap data resolution', () => {
    const canvas = createHeatmapRasterCanvas({
      width: 7,
      height: 4,
      values: new Float32Array(28).fill(22),
      pixelToMmFactor: 11,
      heatmapMinMm: 1,
      heatmapMaxMm: 5,
      colormap: new Uint8Array(256 * 3).fill(128),
    });

    expect(canvas.width).toBe(7);
    expect(canvas.height).toBe(4);
  });

  it('upscales export dimensions with integer multipliers until the heatmap reaches at least full hd', () => {
    expect(resolveHeatmapExportDimensions(640, 360)).toEqual({
      scaleX: 3,
      scaleY: 3,
      width: 1920,
      height: 1080,
    });

    expect(resolveHeatmapExportDimensions(2000, 30)).toEqual({
      scaleX: 1,
      scaleY: 36,
      width: 2000,
      height: 1080,
    });

    expect(resolveHeatmapExportDimensions(500, 2000)).toEqual({
      scaleX: 4,
      scaleY: 1,
      width: 2000,
      height: 2000,
    });
  });

  it('draws contraction overlays and the current-frame marker when requested', () => {
    const ctx = {
      save: vi.fn(),
      restore: vi.fn(),
      setLineDash: vi.fn(),
      strokeRect: vi.fn(),
      beginPath: vi.fn(),
      moveTo: vi.fn(),
      lineTo: vi.fn(),
      stroke: vi.fn(),
      globalAlpha: 1,
      strokeStyle: '#000000',
      lineWidth: 1,
    } as unknown as CanvasRenderingContext2D;

    drawHeatmapOverlays(ctx, {
      width: 10,
      height: 5,
      currentFrame: 3,
      showContractionOverlays: true,
      selectedContractionId: 'event-1',
      contractionEvents: [createEvent()],
      scaleX: 2,
      scaledDataHeight: 30,
    });

    expect(ctx.strokeRect).toHaveBeenCalledTimes(1);
    expect(ctx.beginPath).toHaveBeenCalled();
    expect(ctx.moveTo).toHaveBeenCalled();
    expect(ctx.lineTo).toHaveBeenCalled();
    expect(ctx.stroke).toHaveBeenCalled();
    expect(ctx.setLineDash).toHaveBeenCalledWith([5, 5]);
  });
});

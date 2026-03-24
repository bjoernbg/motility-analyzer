import { describe, expect, it } from 'vitest';

import {
  renderSidebarFrameToCanvas,
  resolveSidebarFrameViewport,
} from '../multiViewFrameRendering';

describe('multi-view frame rendering helpers', () => {
  it('applies the current horizontal crop window when resolving the viewport', () => {
    const viewport = resolveSidebarFrameViewport(1920, 1080, 320, 200, 100, 500);

    expect(viewport.sourceX).toBe(80);
    expect(viewport.sourceWidth).toBe(440);
  });

  it('keeps the export free of outer chrome by rendering only the frame viewport', () => {
    const canvas = renderSidebarFrameToCanvas({
      image: document.createElement('canvas'),
      videoWidth: 1920,
      videoHeight: 1080,
      clipWidth: 320,
      clipHeight: 180,
      frameData: null,
      pixelToMmFactor: 11,
      showDetectedEdges: false,
      showSelectedPointMeasurements: false,
      highlightedPointIndex: null,
      windowLeft: 100,
      windowRight: 500,
    });

    expect(canvas.width).toBeGreaterThan(0);
    expect(canvas.height).toBeGreaterThan(0);
  });

  it('renders overlays into the cropped export when enabled', () => {
    const canvas = renderSidebarFrameToCanvas({
      image: document.createElement('canvas'),
      videoWidth: 1920,
      videoHeight: 1080,
      clipWidth: 320,
      clipHeight: 180,
      frameData: {
        f: 0,
        pt: [[110, 100], [120, 110]],
        pb: [[110, 200], [120, 210]],
        pc: [],
        colored_regions: [],
        mpp: [[0, 0, 115, 120, 118, 190, 12]],
      },
      pixelToMmFactor: 11,
      showDetectedEdges: true,
      showSelectedPointMeasurements: true,
      highlightedPointIndex: 0,
      windowLeft: 100,
      windowRight: 500,
    });

    expect(canvas.width).toBeGreaterThan(0);
    expect(canvas.height).toBeGreaterThan(0);
  });
});

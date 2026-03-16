import { describe, expect, it } from 'vitest';
import { analyzeTubeSweep, buildTubeGeometry } from '../tubeGeometry';
import {
  PERSISTED_BOTTOM_FRAME_2450,
  PERSISTED_BOTTOM_PIXEL_TO_MM,
  PERSISTED_FRONT_FRAME_2460,
  PERSISTED_FRONT_PIXEL_TO_MM,
} from './fixtures/persistedDenseTubeFixture';

const COLORMAP = new Uint8Array(256 * 3);
const GRAYSCALE_COLORMAP = createGrayscaleColormap();
const RING_VERTEX_COUNT = 65;

type Mpp = [number, number, number, number, number, number, number];

function toArray(data: Float32Array | Uint32Array): number[] {
  return Array.from(data);
}

function createGrayscaleColormap(): Uint8Array {
  const colormap = new Uint8Array(256 * 3);
  for (let i = 0; i < 256; i += 1) {
    colormap[i * 3] = i;
    colormap[i * 3 + 1] = i;
    colormap[i * 3 + 2] = i;
  }
  return colormap;
}

function createCurvedFrontMpp(count: number): Mpp[] {
  return Array.from({ length: count }, (_, index) => {
    const t = count > 1 ? index / (count - 1) : 0;
    return [
      index * 6,
      220 + Math.sin(t * Math.PI * 1.7) * 45 + Math.sin(t * Math.PI * 5) * 6,
      0,
      0,
      0,
      0,
      30 + Math.cos(t * Math.PI * 2.5) * 6,
    ];
  });
}

function createCurvedBottomMpp(count: number): Mpp[] {
  return Array.from({ length: count }, (_, index) => {
    const t = count > 1 ? index / (count - 1) : 0;
    return [
      index * 6,
      180 + Math.cos(t * Math.PI * 1.4) * 35 + Math.sin(t * Math.PI * 4) * 7,
      0,
      0,
      0,
      0,
      24 + Math.sin(t * Math.PI * 2.8) * 5,
    ];
  });
}

function grayscaleValue(minMm: number, maxMm: number, valueMm: number): number {
  const normalized = maxMm > minMm ? (valueMm - minMm) / (maxMm - minMm) : 0.5;
  const index = Math.max(0, Math.min(255, Math.round(normalized * 255)));
  return index / 255;
}

describe('buildTubeGeometry', () => {
  it('uses declared front and bottom directions even when source slots are reversed', () => {
    const frontMpp: Mpp[] = [
      [10, 20, 0, 0, 0, 0, 8],
      [20, 30, 0, 0, 0, 0, 10],
    ];
    const bottomMpp: Mpp[] = [
      [100, 200, 0, 0, 0, 0, 12],
      [110, 220, 0, 0, 0, 0, 14],
    ];

    const defaultOrder = buildTubeGeometry(
      frontMpp,
      bottomMpp,
      10,
      20,
      COLORMAP,
      0,
      30,
      'front',
      'bottom'
    );
    const swappedOrder = buildTubeGeometry(
      bottomMpp,
      frontMpp,
      20,
      10,
      COLORMAP,
      0,
      30,
      'bottom',
      'front'
    );

    expect(toArray(swappedOrder.positions)).toEqual(toArray(defaultOrder.positions));
    expect(toArray(swappedOrder.normals)).toEqual(toArray(defaultOrder.normals));
    expect(toArray(swappedOrder.colors)).toEqual(toArray(defaultOrder.colors));
    expect(toArray(swappedOrder.indices)).toEqual(toArray(defaultOrder.indices));
  });

  it('returns empty geometry for duplicate direction assignments', () => {
    const mpp: Mpp[] = [
      [10, 20, 0, 0, 0, 0, 8],
      [20, 30, 0, 0, 0, 0, 10],
    ];

    const data = buildTubeGeometry(
      mpp,
      mpp,
      10,
      10,
      COLORMAP,
      0,
      30,
      'front',
      'front'
    );

    expect(data.positions).toHaveLength(0);
    expect(data.normals).toHaveLength(0);
    expect(data.colors).toHaveLength(0);
    expect(data.indices).toHaveLength(0);
  });

  it('keeps the persisted 200-point regression frame non-folding without dropping rings', () => {
    const diagnostics = analyzeTubeSweep(
      PERSISTED_FRONT_FRAME_2460,
      PERSISTED_BOTTOM_FRAME_2450,
      PERSISTED_FRONT_PIXEL_TO_MM,
      PERSISTED_BOTTOM_PIXEL_TO_MM,
      'front',
      'bottom'
    );

    expect(diagnostics).not.toBeNull();
    expect(diagnostics?.minimumForwardAdvance).toBeGreaterThan(1e-3);
    expect(diagnostics?.tangentWindowRadius).toBeGreaterThan(1);
    expect(diagnostics?.usedRadiusClamp).toBe(false);

    const data = buildTubeGeometry(
      PERSISTED_FRONT_FRAME_2460,
      PERSISTED_BOTTOM_FRAME_2450,
      PERSISTED_FRONT_PIXEL_TO_MM,
      PERSISTED_BOTTOM_PIXEL_TO_MM,
      COLORMAP,
      0,
      30,
      'front',
      'bottom'
    );

    expect(data.positions.length / (RING_VERTEX_COUNT * 3)).toBe(
      PERSISTED_FRONT_FRAME_2460.length
    );
  });

  it('chooses a larger tangent window for dense curved inputs than for low-point inputs', () => {
    const denseFront = createCurvedFrontMpp(200);
    const denseBottom = createCurvedBottomMpp(200);
    const lowFront = createCurvedFrontMpp(20);
    const lowBottom = createCurvedBottomMpp(20);

    const denseDiagnostics = analyzeTubeSweep(
      denseFront,
      denseBottom,
      20,
      20,
      'front',
      'bottom'
    );
    const lowDiagnostics = analyzeTubeSweep(
      lowFront,
      lowBottom,
      20,
      20,
      'front',
      'bottom'
    );

    expect(denseDiagnostics).not.toBeNull();
    expect(lowDiagnostics).not.toBeNull();
    expect(denseDiagnostics?.tangentWindowRadius).toBeGreaterThan(
      lowDiagnostics?.tangentWindowRadius ?? 0
    );
    expect(denseDiagnostics?.minimumForwardAdvance).toBeGreaterThan(1e-3);
    expect(lowDiagnostics?.minimumForwardAdvance).toBeGreaterThan(1e-3);
  });

  it('keeps colors tied to raw thickness when the radius clamp fallback is used', () => {
    const frontMpp: Mpp[] = [
      [0, 0, 0, 0, 0, 0, 40],
      [0, 0, 0, 0, 0, 0, 50],
    ];
    const bottomMpp: Mpp[] = [
      [0, 0, 0, 0, 0, 0, 30],
      [0, 0, 0, 0, 0, 0, 35],
    ];
    const minMm = 0;
    const maxMm = 60;

    const diagnostics = analyzeTubeSweep(
      frontMpp,
      bottomMpp,
      1,
      1,
      'front',
      'bottom'
    );
    expect(diagnostics?.usedRadiusClamp).toBe(true);

    const data = buildTubeGeometry(
      frontMpp,
      bottomMpp,
      1,
      1,
      GRAYSCALE_COLORMAP,
      minMm,
      maxMm,
      'front',
      'bottom'
    );

    const expectedFirstColor = grayscaleValue(minMm, maxMm, (40 + 30) / 2);
    expect(data.colors[0]).toBeCloseTo(expectedFirstColor, 5);
    expect(data.colors[1]).toBeCloseTo(expectedFirstColor, 5);
    expect(data.colors[2]).toBeCloseTo(expectedFirstColor, 5);
  });
});

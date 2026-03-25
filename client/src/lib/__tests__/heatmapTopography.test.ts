import { describe, expect, it } from 'vitest'

import { createColormap, colormapValueToRgb } from '../colormap'
import {
  buildHeatmapTopographyFrameLine,
  buildHeatmapTopographySurface,
  convertHeatmapPixelValueToMm,
  mapHeatmapMmValueToTopographyHeight,
  normalizeHeatmapMmValue,
  resolveTopographyColumnCount,
  resolveTopographyFrameFromWorldX,
  resolveTopographyPointIndexFromWorldY,
} from '../heatmapTopography'

describe('heatmap topography utilities', () => {
  it('converts pixel distances to mm and normalizes values against the heatmap range', () => {
    expect(convertHeatmapPixelValueToMm(42, 14)).toBeCloseTo(3)
    expect(normalizeHeatmapMmValue(1, 1, 5)).toBe(0)
    expect(normalizeHeatmapMmValue(3, 1, 5)).toBeCloseTo(0.5)
    expect(normalizeHeatmapMmValue(9, 1, 5)).toBe(1)
  })

  it('reuses the heatmap colormap while building the topography mesh', () => {
    const colormap = createColormap()
    const surface = buildHeatmapTopographySurface({
      colormap,
      frameCount: 2,
      heatmapMaxMm: 5,
      heatmapMinMm: 1,
      maxColumns: 2,
      pixelToMmFactor: 10,
      pointCount: 2,
      values: new Float32Array([10, 20, 30, 50]),
    })

    expect(surface.positions.length).toBe(12)
    expect(surface.indices.length).toBe(6)

    const minColor = colormapValueToRgb(colormap, 0)
    const maxColor = colormapValueToRgb(colormap, 1)

    expect(surface.positions[2]).toBeGreaterThan(surface.positions[5])
    expect(surface.positions[5]).toBeGreaterThan(surface.positions[8])
    expect(surface.positions[8]).toBeGreaterThan(surface.positions[11])
    expect(surface.colors[0]).toBeCloseTo(minColor[0])
    expect(surface.colors[1]).toBeCloseTo(minColor[1])
    expect(surface.colors[2]).toBeCloseTo(minColor[2])
    expect(surface.colors[9]).toBeCloseTo(maxColor[0])
    expect(surface.colors[10]).toBeCloseTo(maxColor[1])
    expect(surface.colors[11]).toBeCloseTo(maxColor[2])
    expect(surface.positions[8]).toBeCloseTo(surface.metrics.heightScale * 0.5)
  })

  it('maps measurement values to descending topography heights across the display range', () => {
    const surface = buildHeatmapTopographySurface({
      colormap: createColormap(),
      frameCount: 6,
      heatmapMaxMm: 5,
      heatmapMinMm: 1,
      pixelToMmFactor: 10,
      pointCount: 5,
      values: new Float32Array(30).fill(20),
    })

    const minHeight = mapHeatmapMmValueToTopographyHeight(1, 1, 5, surface.metrics.heightScale)
    const midHeight = mapHeatmapMmValueToTopographyHeight(3, 1, 5, surface.metrics.heightScale)
    const maxHeight = mapHeatmapMmValueToTopographyHeight(5, 1, 5, surface.metrics.heightScale)

    expect(minHeight).toBeCloseTo(surface.metrics.heightScale)
    expect(midHeight).toBeCloseTo(surface.metrics.heightScale * 0.5)
    expect(maxHeight).toBeCloseTo(0)
    expect(minHeight).toBeGreaterThan(midHeight)
    expect(midHeight).toBeGreaterThan(maxHeight)
  })

  it('downsamples wide analyses to a bounded number of topography columns and clamps the footprint aspect', () => {
    expect(resolveTopographyColumnCount(0, 128)).toBe(0)
    expect(resolveTopographyColumnCount(80, 128)).toBe(80)
    expect(resolveTopographyColumnCount(1000, 128)).toBe(128)

    const surface = buildHeatmapTopographySurface({
      colormap: createColormap(),
      frameCount: 1000,
      heatmapMaxMm: 5,
      heatmapMinMm: 1,
      maxColumns: 128,
      pixelToMmFactor: 10,
      pointCount: 4,
      values: new Float32Array(4000).fill(20),
    })

    expect(surface.metrics.columnCount).toBe(128)
    expect(surface.metrics.footprintAspectRatio).toBe(2)
    expect(surface.metrics.yScale).toBeCloseTo(999 / 6)
    expect(surface.frameWindows).toHaveLength(128)
    expect(surface.frameWindows[0]).toEqual([0, 7])
    expect(surface.frameWindows.at(-1)).toEqual([992, 1000])
  })

  it('maps world coordinates back to the original frame and point indices', () => {
    const surface = buildHeatmapTopographySurface({
      colormap: createColormap(),
      frameCount: 6,
      heatmapMaxMm: 5,
      heatmapMinMm: 1,
      pixelToMmFactor: 10,
      pointCount: 5,
      values: new Float32Array(30).fill(20),
    })

    expect(resolveTopographyFrameFromWorldX(0, surface.metrics)).toBe(3)
    expect(resolveTopographyPointIndexFromWorldY(0, surface.metrics)).toBe(2)

    const line = buildHeatmapTopographyFrameLine({
      frame: 4,
      heatmapMaxMm: 5,
      heatmapMinMm: 1,
      metrics: surface.metrics,
      pixelToMmFactor: 10,
      values: new Float32Array(30).fill(10),
    })

    expect(line).not.toBeNull()
    expect(line?.positions[0]).toBeCloseTo(1.5)
    expect(line?.positions[2]).toBeGreaterThan(surface.metrics.heightScale)
  })
})

import { describe, expect, it } from 'vitest';

import { buildColorScaleLabels, resolveColorScaleColorIndex } from '../colorScale';

describe('color scale helpers', () => {
  it('includes the configured range endpoints and integer ticks between them', () => {
    const labels = buildColorScaleLabels(3.2, 5.7);

    expect(labels).toHaveLength(4);
    expect(labels[0]).toEqual({ value: '3.2', percent: 0 });
    expect(labels[1]?.value).toBe('4');
    expect(labels[1]?.percent).toBeCloseTo(32);
    expect(labels[2]?.value).toBe('5');
    expect(labels[2]?.percent).toBeCloseTo(72);
    expect(labels[3]).toEqual({ value: '5.7', percent: 100 });
  });

  it('maps the top of the scale to the highest color index and the bottom to the lowest', () => {
    expect(resolveColorScaleColorIndex(0, 200)).toBe(255);
    expect(resolveColorScaleColorIndex(199, 200)).toBe(0);
    expect(resolveColorScaleColorIndex(99.5, 200)).toBe(128);
  });
});

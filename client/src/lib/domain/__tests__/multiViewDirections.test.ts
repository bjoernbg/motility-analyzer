import { describe, expect, it } from 'vitest';
import {
  formatMultiViewDirection,
  resolveMultiViewDirectionPair,
  selectMultiViewDirection,
} from '../multiViewDirections';

describe('multi-view direction helpers', () => {
  it('resolves legacy metadata to front and bottom defaults', () => {
    expect(resolveMultiViewDirectionPair(null)).toEqual({
      leftDirection: 'front',
      rightDirection: 'bottom',
      isValid: true,
    });
  });

  it('swaps the opposite slot when a taken direction is selected', () => {
    expect(
      selectMultiViewDirection(
        {
          leftDirection: 'front',
          rightDirection: 'bottom',
        },
        'left',
        'bottom'
      )
    ).toEqual({
      leftDirection: 'bottom',
      rightDirection: 'front',
      isValid: true,
    });
  });

  it('flags duplicate stored directions as invalid', () => {
    expect(
      resolveMultiViewDirectionPair({
        left_direction: 'front',
        right_direction: 'front',
      })
    ).toEqual({
      leftDirection: 'front',
      rightDirection: 'front',
      isValid: false,
    });
  });

  it('formats directions for UI labels', () => {
    expect(formatMultiViewDirection('front')).toBe('Front');
    expect(formatMultiViewDirection('bottom')).toBe('Bottom');
  });
});

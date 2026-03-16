import { describe, expect, it } from 'vitest';
import { buildTubeGeometry } from '../tubeGeometry';

const COLORMAP = new Uint8Array(256 * 3);

type Mpp = [number, number, number, number, number, number, number];

function toArray(data: Float32Array | Uint32Array): number[] {
  return Array.from(data);
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
});

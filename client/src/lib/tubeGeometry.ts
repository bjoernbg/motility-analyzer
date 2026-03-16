/**
 * Pure math module: transforms left/right MPP arrays into Three.js-compatible
 * typed arrays for rendering a 3D tubular model of the intestine.
 *
 * The front analysis defines the axial and vertical dimensions.
 * The bottom analysis defines the depth dimension.
 */

import type { MultiViewAnalysisDirection } from './api';

type Mpp = [number, number, number, number, number, number, number];

export interface TubeGeometryData {
  positions: Float32Array;
  normals: Float32Array;
  colors: Float32Array;
  indices: Uint32Array;
}

const SEGMENTS = 64;

function emptyGeometryData(): TubeGeometryData {
  return {
    positions: new Float32Array(0),
    normals: new Float32Array(0),
    colors: new Float32Array(0),
    indices: new Uint32Array(0),
  };
}

/**
 * Map a [0,1] value to [r, g, b] floats through a 256-entry colormap.
 */
function colormapLookup(
  colormap: Uint8Array,
  normalizedValue: number,
): [number, number, number] {
  const idx = Math.max(0, Math.min(255, Math.round(normalizedValue * 255)));
  return [
    colormap[idx * 3]! / 255,
    colormap[idx * 3 + 1]! / 255,
    colormap[idx * 3 + 2]! / 255,
  ];
}

/**
 * Normalize a 3-vector in place. Returns the original length.
 */
function normalize(v: [number, number, number]): number {
  const len = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  if (len > 1e-10) {
    v[0] /= len;
    v[1] /= len;
    v[2] /= len;
  }
  return len;
}

function cross(
  a: [number, number, number],
  b: [number, number, number],
): [number, number, number] {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

/**
 * Build 3D tube geometry from two views' measurement point pairs.
 *
 * @param leftMpp  Left analysis MPP: [cx, cy, tx, ty, bx, by, distance][]
 * @param rightMpp Right analysis MPP (same format)
 * @param leftPxToMm  Left pixel-to-mm factor
 * @param rightPxToMm Right pixel-to-mm factor
 * @param colormap 256-entry Uint8Array (768 bytes) from createColormap()
 * @param minMm    Heatmap min mm for color mapping
 * @param maxMm    Heatmap max mm for color mapping
 */
export function buildTubeGeometry(
  leftMpp: Mpp[],
  rightMpp: Mpp[],
  leftPxToMm: number,
  rightPxToMm: number,
  colormap: Uint8Array,
  minMm: number,
  maxMm: number,
  leftDirection: MultiViewAnalysisDirection,
  rightDirection: MultiViewAnalysisDirection,
): TubeGeometryData {
  if (leftDirection === rightDirection) {
    return emptyGeometryData();
  }

  const frontMpp = leftDirection === 'front' ? leftMpp : rightMpp;
  const bottomMpp = leftDirection === 'bottom' ? leftMpp : rightMpp;
  const frontPxToMm = leftDirection === 'front' ? leftPxToMm : rightPxToMm;
  const bottomPxToMm = leftDirection === 'bottom' ? leftPxToMm : rightPxToMm;
  const N = Math.min(frontMpp.length, bottomMpp.length);

  if (N < 2) {
    return emptyGeometryData();
  }

  // Step 1: Build 3D center spine + radii
  const spine: [number, number, number][] = [];
  const radiiY: number[] = [];
  const radiiZ: number[] = [];

  let meanY = 0;
  let meanZ = 0;

  for (let i = 0; i < N; i++) {
    const frontMeasurement = frontMpp[i]!;
    const bottomMeasurement = bottomMpp[i]!;
    const x = frontMeasurement[0] / frontPxToMm;
    const y = frontMeasurement[1] / frontPxToMm;
    const z = bottomMeasurement[1] / bottomPxToMm;
    spine.push([x, y, z]);
    meanY += y;
    meanZ += z;
    radiiY.push(frontMeasurement[6] / 2 / frontPxToMm);
    radiiZ.push(bottomMeasurement[6] / 2 / bottomPxToMm);
  }

  meanY /= N;
  meanZ /= N;

  // Center the model at origin (y,z only — keep x as the tube axis)
  for (let i = 0; i < N; i++) {
    spine[i]![1] -= meanY;
    spine[i]![2] -= meanZ;
  }

  // Step 2: Compute Frenet frames via parallel transport
  const tangents: [number, number, number][] = [];
  const normals: [number, number, number][] = [];
  const binormals: [number, number, number][] = [];

  // Tangent via central differences
  for (let i = 0; i < N; i++) {
    let t: [number, number, number];
    if (i === 0) {
      const next = spine[1]!;
      const current = spine[0]!;
      t = [
        next[0] - current[0],
        next[1] - current[1],
        next[2] - current[2],
      ];
    } else if (i === N - 1) {
      const current = spine[N - 1]!;
      const previous = spine[N - 2]!;
      t = [
        current[0] - previous[0],
        current[1] - previous[1],
        current[2] - previous[2],
      ];
    } else {
      const next = spine[i + 1]!;
      const previous = spine[i - 1]!;
      t = [
        next[0] - previous[0],
        next[1] - previous[1],
        next[2] - previous[2],
      ];
    }
    normalize(t);
    tangents.push(t);
  }

  // Initial normal: choose axis most perpendicular to first tangent
  const t0 = tangents[0]!;
  let initialNormal: [number, number, number];
  if (Math.abs(t0[1]) < 0.9) {
    initialNormal = cross(t0, [0, 1, 0]);
  } else {
    initialNormal = cross(t0, [0, 0, 1]);
  }
  normalize(initialNormal);
  normals.push(initialNormal);
  binormals.push(cross(t0, initialNormal));
  normalize(binormals[0]!);

  // Parallel transport
  for (let i = 1; i < N; i++) {
    const tPrev = tangents[i - 1]!;
    const tCurr = tangents[i]!;
    let nPrev = normals[i - 1]!;

    // Rotation axis: cross of consecutive tangents
    const rotAxis = cross(tPrev, tCurr);
    const rotAxisLen = normalize(rotAxis);

    if (rotAxisLen > 1e-10) {
      // Angle between tangents
      const dot =
        tPrev[0] * tCurr[0] + tPrev[1] * tCurr[1] + tPrev[2] * tCurr[2];
      const angle = Math.acos(Math.max(-1, Math.min(1, dot)));

      // Rodrigues rotation of nPrev around rotAxis by angle
      const cosA = Math.cos(angle);
      const sinA = Math.sin(angle);
      const dotNR =
        nPrev[0] * rotAxis[0] +
        nPrev[1] * rotAxis[1] +
        nPrev[2] * rotAxis[2];
      const crossNR = cross(rotAxis, nPrev);

      nPrev = [
        nPrev[0] * cosA + crossNR[0] * sinA + rotAxis[0] * dotNR * (1 - cosA),
        nPrev[1] * cosA + crossNR[1] * sinA + rotAxis[1] * dotNR * (1 - cosA),
        nPrev[2] * cosA + crossNR[2] * sinA + rotAxis[2] * dotNR * (1 - cosA),
      ];
    }

    normalize(nPrev);
    normals.push(nPrev);

    const b = cross(tCurr, nPrev);
    normalize(b);
    binormals.push(b);
  }

  // Step 3: Generate ring vertices
  const S = SEGMENTS;
  const vertexCount = N * (S + 1); // +1 to close the ring with matching UVs
  const positions = new Float32Array(vertexCount * 3);
  const vertexNormals = new Float32Array(vertexCount * 3);
  const colors = new Float32Array(vertexCount * 3);

  const range = maxMm - minMm;

  for (let i = 0; i < N; i++) {
    const center = spine[i]!;
    const n = normals[i]!;
    const b = binormals[i]!;
    const ry = radiiY[i]!;
    const rz = radiiZ[i]!;

    // Average thickness for color
    const avgThicknessMm = (radiiY[i]! * 2 + radiiZ[i]! * 2) / 2;
    let normalizedColor = range > 0 ? (avgThicknessMm - minMm) / range : 0.5;
    normalizedColor = Math.max(0, Math.min(1, normalizedColor));
    const [cr, cg, cb] = colormapLookup(colormap, normalizedColor);

    for (let j = 0; j <= S; j++) {
      const theta = (j / S) * Math.PI * 2;
      const cosTheta = Math.cos(theta);
      const sinTheta = Math.sin(theta);

      // Ellipse point in local frame
      const localY = ry * cosTheta;
      const localZ = rz * sinTheta;

      const vIdx = (i * (S + 1) + j) * 3;

      // Position: center + localY * normal + localZ * binormal
      positions[vIdx] = center[0] + localY * n[0] + localZ * b[0];
      positions[vIdx + 1] = center[1] + localY * n[1] + localZ * b[1];
      positions[vIdx + 2] = center[2] + localY * n[2] + localZ * b[2];

      // Normal: direction from center to vertex (for ellipse, needs adjustment)
      const nx = localY * n[0] + localZ * b[0];
      const ny = localY * n[1] + localZ * b[1];
      const nz = localY * n[2] + localZ * b[2];
      const nLen = Math.sqrt(nx * nx + ny * ny + nz * nz);

      if (nLen > 1e-10) {
        vertexNormals[vIdx] = nx / nLen;
        vertexNormals[vIdx + 1] = ny / nLen;
        vertexNormals[vIdx + 2] = nz / nLen;
      }

      colors[vIdx] = cr;
      colors[vIdx + 1] = cg;
      colors[vIdx + 2] = cb;
    }
  }

  // Step 4: Build triangle index buffer (quad-strip between adjacent rings)
  const faceCount = (N - 1) * S * 2;
  const indices = new Uint32Array(faceCount * 3);
  let idx = 0;

  for (let i = 0; i < N - 1; i++) {
    for (let j = 0; j < S; j++) {
      const a = i * (S + 1) + j;
      const b = a + 1;
      const c = (i + 1) * (S + 1) + j;
      const d = c + 1;

      indices[idx++] = a;
      indices[idx++] = c;
      indices[idx++] = b;

      indices[idx++] = b;
      indices[idx++] = c;
      indices[idx++] = d;
    }
  }

  return {
    positions,
    normals: vertexNormals,
    colors,
    indices,
  };
}

/**
 * Pure math module: transforms left/right MPP arrays into Three.js-compatible
 * typed arrays for rendering a 3D tubular model of the intestine.
 *
 * The front analysis defines the axial and vertical dimensions.
 * The bottom analysis defines the depth dimension.
 */

import type { MultiViewAnalysisDirection } from './api';

type Mpp = [number, number, number, number, number, number, number];
type Vec3 = [number, number, number];

export interface TubeGeometryData {
  positions: Float32Array;
  normals: Float32Array;
  colors: Float32Array;
  indices: Uint32Array;
}

export interface TubeSweepDiagnostics {
  minimumForwardAdvance: number;
  tangentWindowRadius: number;
  usedRadiusClamp: boolean;
}

interface ResolvedSweepInputs {
  frontMpp: Mpp[];
  bottomMpp: Mpp[];
  frontPxToMm: number;
  bottomPxToMm: number;
}

interface TubeSampleBase {
  center: Vec3;
  rawRadiusY: number;
  rawRadiusZ: number;
  rawThicknessMm: number;
}

interface TubeSample extends TubeSampleBase {
  renderScale: number;
  tangent: Vec3;
  normal: Vec3;
  binormal: Vec3;
}

interface TubeSweepLayout {
  samples: TubeSample[];
  minimumForwardAdvance: number;
  tangentWindowRadius: number;
  usedRadiusClamp: boolean;
}

const SEGMENTS = 64;
const FORWARD_ADVANCE_SAMPLES = 32;
const MIN_FORWARD_ADVANCE_MM = 1e-3;
const VECTOR_EPSILON = 1e-10;
const INITIAL_TANGENT_WINDOW_RATIO = 0.04;
const INITIAL_TANGENT_WINDOW_MAX = 8;
const MAX_TANGENT_WINDOW_RADIUS = 10;
const MAX_RADIUS_CLAMP_PASSES = 8;
const BINARY_SEARCH_STEPS = 14;

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

function clampNumber(value: number, min: number, max: number): number {
  return Math.max(min, Math.min(max, value));
}

/**
 * Normalize a 3-vector in place. Returns the original length.
 */
function normalize(v: Vec3): number {
  const len = Math.sqrt(v[0] * v[0] + v[1] * v[1] + v[2] * v[2]);
  if (len > VECTOR_EPSILON) {
    v[0] /= len;
    v[1] /= len;
    v[2] /= len;
  }
  return len;
}

function dot(a: Vec3, b: Vec3): number {
  return a[0] * b[0] + a[1] * b[1] + a[2] * b[2];
}

function cross(a: Vec3, b: Vec3): Vec3 {
  return [
    a[1] * b[2] - a[2] * b[1],
    a[2] * b[0] - a[0] * b[2],
    a[0] * b[1] - a[1] * b[0],
  ];
}

function cloneVec3(v: Vec3): Vec3 {
  return [v[0], v[1], v[2]];
}

function subtractVec3(a: Vec3, b: Vec3): Vec3 {
  return [a[0] - b[0], a[1] - b[1], a[2] - b[2]];
}

function addVec3(a: Vec3, b: Vec3): Vec3 {
  return [a[0] + b[0], a[1] + b[1], a[2] + b[2]];
}

function getInitialTangentWindowRadius(sampleCount: number): number {
  return clampNumber(
    Math.round(sampleCount * INITIAL_TANGENT_WINDOW_RATIO),
    1,
    INITIAL_TANGENT_WINDOW_MAX,
  );
}

function resolveSweepInputs(
  leftMpp: Mpp[],
  rightMpp: Mpp[],
  leftPxToMm: number,
  rightPxToMm: number,
  leftDirection: MultiViewAnalysisDirection,
  rightDirection: MultiViewAnalysisDirection,
): ResolvedSweepInputs | null {
  if (leftDirection === rightDirection) {
    return null;
  }

  return {
    frontMpp: leftDirection === 'front' ? leftMpp : rightMpp,
    bottomMpp: leftDirection === 'bottom' ? leftMpp : rightMpp,
    frontPxToMm: leftDirection === 'front' ? leftPxToMm : rightPxToMm,
    bottomPxToMm: leftDirection === 'bottom' ? leftPxToMm : rightPxToMm,
  };
}

function buildRawSamples(inputs: ResolvedSweepInputs): TubeSampleBase[] {
  const N = Math.min(inputs.frontMpp.length, inputs.bottomMpp.length);
  const samples: TubeSampleBase[] = [];

  let meanY = 0;
  let meanZ = 0;

  for (let i = 0; i < N; i += 1) {
    const frontMeasurement = inputs.frontMpp[i]!;
    const bottomMeasurement = inputs.bottomMpp[i]!;
    const center: Vec3 = [
      frontMeasurement[0] / inputs.frontPxToMm,
      frontMeasurement[1] / inputs.frontPxToMm,
      bottomMeasurement[1] / inputs.bottomPxToMm,
    ];
    const rawRadiusY = frontMeasurement[6] / 2 / inputs.frontPxToMm;
    const rawRadiusZ = bottomMeasurement[6] / 2 / inputs.bottomPxToMm;

    meanY += center[1];
    meanZ += center[2];

    samples.push({
      center,
      rawRadiusY,
      rawRadiusZ,
      rawThicknessMm: (rawRadiusY * 2 + rawRadiusZ * 2) / 2,
    });
  }

  if (samples.length === 0) {
    return samples;
  }

  meanY /= samples.length;
  meanZ /= samples.length;

  for (const sample of samples) {
    sample.center[1] -= meanY;
    sample.center[2] -= meanZ;
  }

  return samples;
}

function computeWindowedTangent(
  samples: TubeSampleBase[],
  index: number,
  tangentWindowRadius: number,
): Vec3 {
  const lastIndex = samples.length - 1;
  const startIndex = Math.max(0, index - tangentWindowRadius);
  const endIndex = Math.min(lastIndex, index + tangentWindowRadius);

  let tangent = subtractVec3(
    samples[endIndex]!.center,
    samples[startIndex]!.center,
  );

  if (normalize(tangent) > VECTOR_EPSILON) {
    return tangent;
  }

  if (index < lastIndex) {
    tangent = subtractVec3(samples[index + 1]!.center, samples[index]!.center);
    if (normalize(tangent) > VECTOR_EPSILON) {
      return tangent;
    }
  }

  if (index > 0) {
    tangent = subtractVec3(samples[index]!.center, samples[index - 1]!.center);
    if (normalize(tangent) > VECTOR_EPSILON) {
      return tangent;
    }
  }

  return [1, 0, 0];
}

function chooseInitialNormal(tangent: Vec3): Vec3 {
  const normal = cross(tangent, Math.abs(tangent[1]) < 0.9 ? [0, 1, 0] : [0, 0, 1]);
  if (normalize(normal) > VECTOR_EPSILON) {
    return normal;
  }

  const fallback = cross(tangent, [1, 0, 0]);
  if (normalize(fallback) > VECTOR_EPSILON) {
    return fallback;
  }

  return [0, 1, 0];
}

function buildFramedSamples(
  samples: TubeSampleBase[],
  tangentWindowRadius: number,
): TubeSample[] {
  const tangents = samples.map((_, index) =>
    computeWindowedTangent(samples, index, tangentWindowRadius),
  );

  const normals: Vec3[] = [];
  const binormals: Vec3[] = [];

  const firstNormal = chooseInitialNormal(tangents[0]!);
  normals.push(firstNormal);
  const firstBinormal = cross(tangents[0]!, firstNormal);
  normalize(firstBinormal);
  binormals.push(firstBinormal);

  for (let i = 1; i < samples.length; i += 1) {
    const tPrev = tangents[i - 1]!;
    const tCurr = tangents[i]!;
    let normal = cloneVec3(normals[i - 1]!);

    const rotationAxis = cross(tPrev, tCurr);
    const rotationAxisLength = normalize(rotationAxis);

    if (rotationAxisLength > VECTOR_EPSILON) {
      const angle = Math.acos(clampNumber(dot(tPrev, tCurr), -1, 1));
      const cosAngle = Math.cos(angle);
      const sinAngle = Math.sin(angle);
      const dotNormalAxis = dot(normal, rotationAxis);
      const axisCrossNormal = cross(rotationAxis, normal);

      normal = [
        normal[0] * cosAngle +
          axisCrossNormal[0] * sinAngle +
          rotationAxis[0] * dotNormalAxis * (1 - cosAngle),
        normal[1] * cosAngle +
          axisCrossNormal[1] * sinAngle +
          rotationAxis[1] * dotNormalAxis * (1 - cosAngle),
        normal[2] * cosAngle +
          axisCrossNormal[2] * sinAngle +
          rotationAxis[2] * dotNormalAxis * (1 - cosAngle),
      ];
    }

    normalize(normal);
    normals.push(normal);

    const binormal = cross(tCurr, normal);
    normalize(binormal);
    binormals.push(binormal);
  }

  return samples.map((sample, index) => ({
    ...sample,
    renderScale: 1,
    tangent: cloneVec3(tangents[index]!),
    normal: cloneVec3(normals[index]!),
    binormal: cloneVec3(binormals[index]!),
  }));
}

function cloneSamples(samples: TubeSample[]): TubeSample[] {
  return samples.map((sample) => ({
    ...sample,
    center: cloneVec3(sample.center),
    tangent: cloneVec3(sample.tangent),
    normal: cloneVec3(sample.normal),
    binormal: cloneVec3(sample.binormal),
  }));
}

function pointOnRing(
  sample: TubeSample,
  cosTheta: number,
  sinTheta: number,
  extraScale = 1,
): Vec3 {
  const scale = sample.renderScale * extraScale;
  const localY = sample.rawRadiusY * scale * cosTheta;
  const localZ = sample.rawRadiusZ * scale * sinTheta;

  return [
    sample.center[0] + localY * sample.normal[0] + localZ * sample.binormal[0],
    sample.center[1] + localY * sample.normal[1] + localZ * sample.binormal[1],
    sample.center[2] + localY * sample.normal[2] + localZ * sample.binormal[2],
  ];
}

function getSweepDirection(first: TubeSample, second: TubeSample): Vec3 {
  const segment = subtractVec3(second.center, first.center);
  if (normalize(segment) > VECTOR_EPSILON) {
    return segment;
  }

  const tangent = addVec3(first.tangent, second.tangent);
  if (normalize(tangent) > VECTOR_EPSILON) {
    return tangent;
  }

  return [1, 0, 0];
}

function computePairMinimumForwardAdvance(
  samples: TubeSample[],
  pairIndex: number,
  angleSamples: number,
  firstScaleMultiplier = 1,
  secondScaleMultiplier = 1,
): number {
  const first = samples[pairIndex]!;
  const second = samples[pairIndex + 1]!;
  const sweepDirection = getSweepDirection(first, second);
  let minimumAdvance = Number.POSITIVE_INFINITY;

  for (let angleIndex = 0; angleIndex < angleSamples; angleIndex += 1) {
    const theta = (angleIndex / angleSamples) * Math.PI * 2;
    const cosTheta = Math.cos(theta);
    const sinTheta = Math.sin(theta);
    const pointA = pointOnRing(first, cosTheta, sinTheta, firstScaleMultiplier);
    const pointB = pointOnRing(second, cosTheta, sinTheta, secondScaleMultiplier);
    const advance = dot(subtractVec3(pointB, pointA), sweepDirection);
    minimumAdvance = Math.min(minimumAdvance, advance);
  }

  return minimumAdvance;
}

function computeMinimumForwardAdvance(
  samples: TubeSample[],
  angleSamples: number,
): number {
  let minimumAdvance = Number.POSITIVE_INFINITY;

  for (let i = 0; i < samples.length - 1; i += 1) {
    minimumAdvance = Math.min(
      minimumAdvance,
      computePairMinimumForwardAdvance(samples, i, angleSamples),
    );
  }

  return minimumAdvance;
}

function solveSharedPairClamp(
  samples: TubeSample[],
  pairIndex: number,
  angleSamples: number,
  minimumAdvance: number,
): number {
  if (
    computePairMinimumForwardAdvance(samples, pairIndex, angleSamples) >
    minimumAdvance
  ) {
    return 1;
  }

  if (
    computePairMinimumForwardAdvance(samples, pairIndex, angleSamples, 0, 0) <=
    minimumAdvance
  ) {
    return 0;
  }

  let low = 0;
  let high = 1;

  for (let step = 0; step < BINARY_SEARCH_STEPS; step += 1) {
    const middle = (low + high) / 2;
    const isValid =
      computePairMinimumForwardAdvance(
        samples,
        pairIndex,
        angleSamples,
        middle,
        middle,
      ) > minimumAdvance;

    if (isValid) {
      low = middle;
    } else {
      high = middle;
    }
  }

  return low;
}

function applyLocalRadiusClamp(
  samples: TubeSample[],
  angleSamples: number,
  minimumAdvance: number,
): boolean {
  let usedRadiusClamp = false;

  for (let pass = 0; pass < MAX_RADIUS_CLAMP_PASSES; pass += 1) {
    let passChanged = false;

    for (let i = 0; i < samples.length - 1; i += 1) {
      const pairAdvance = computePairMinimumForwardAdvance(samples, i, angleSamples);
      if (pairAdvance > minimumAdvance) {
        continue;
      }

      const clampFactor = solveSharedPairClamp(
        samples,
        i,
        angleSamples,
        minimumAdvance,
      );
      if (clampFactor >= 0.999999) {
        continue;
      }

      samples[i]!.renderScale *= clampFactor;
      samples[i + 1]!.renderScale *= clampFactor;
      passChanged = true;
      usedRadiusClamp = true;
    }

    if (!passChanged) {
      break;
    }
  }

  return usedRadiusClamp;
}

function buildSweepLayout(
  inputs: ResolvedSweepInputs,
): TubeSweepLayout | null {
  const baseSamples = buildRawSamples(inputs);
  if (baseSamples.length < 2) {
    return null;
  }

  const initialRadius = getInitialTangentWindowRadius(baseSamples.length);
  let bestLayout: TubeSweepLayout | null = null;

  for (
    let tangentWindowRadius = initialRadius;
    tangentWindowRadius <= MAX_TANGENT_WINDOW_RADIUS;
    tangentWindowRadius += 1
  ) {
    const samples = buildFramedSamples(baseSamples, tangentWindowRadius);
    const minimumForwardAdvance = computeMinimumForwardAdvance(
      samples,
      FORWARD_ADVANCE_SAMPLES,
    );

    if (
      bestLayout === null ||
      minimumForwardAdvance > bestLayout.minimumForwardAdvance
    ) {
      bestLayout = {
        samples,
        minimumForwardAdvance,
        tangentWindowRadius,
        usedRadiusClamp: false,
      };
    }

    if (minimumForwardAdvance > MIN_FORWARD_ADVANCE_MM) {
      return {
        samples,
        minimumForwardAdvance,
        tangentWindowRadius,
        usedRadiusClamp: false,
      };
    }
  }

  if (!bestLayout) {
    return null;
  }

  const clampedSamples = cloneSamples(bestLayout.samples);
  const usedRadiusClamp = applyLocalRadiusClamp(
    clampedSamples,
    FORWARD_ADVANCE_SAMPLES,
    MIN_FORWARD_ADVANCE_MM,
  );

  return {
    samples: clampedSamples,
    minimumForwardAdvance: computeMinimumForwardAdvance(
      clampedSamples,
      FORWARD_ADVANCE_SAMPLES,
    ),
    tangentWindowRadius: bestLayout.tangentWindowRadius,
    usedRadiusClamp,
  };
}

export function analyzeTubeSweep(
  leftMpp: Mpp[],
  rightMpp: Mpp[],
  leftPxToMm: number,
  rightPxToMm: number,
  leftDirection: MultiViewAnalysisDirection,
  rightDirection: MultiViewAnalysisDirection,
): TubeSweepDiagnostics | null {
  const inputs = resolveSweepInputs(
    leftMpp,
    rightMpp,
    leftPxToMm,
    rightPxToMm,
    leftDirection,
    rightDirection,
  );
  if (!inputs) {
    return null;
  }

  const layout = buildSweepLayout(inputs);
  if (!layout) {
    return null;
  }

  return {
    minimumForwardAdvance: layout.minimumForwardAdvance,
    tangentWindowRadius: layout.tangentWindowRadius,
    usedRadiusClamp: layout.usedRadiusClamp,
  };
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
  const inputs = resolveSweepInputs(
    leftMpp,
    rightMpp,
    leftPxToMm,
    rightPxToMm,
    leftDirection,
    rightDirection,
  );

  if (!inputs) {
    return emptyGeometryData();
  }

  const layout = buildSweepLayout(inputs);
  if (!layout) {
    return emptyGeometryData();
  }

  const samples = layout.samples;
  const N = samples.length;

  // Step 3: Generate ring vertices
  const S = SEGMENTS;
  const vertexCount = N * (S + 1); // +1 to close the ring with matching UVs
  const positions = new Float32Array(vertexCount * 3);
  const vertexNormals = new Float32Array(vertexCount * 3);
  const colors = new Float32Array(vertexCount * 3);

  const range = maxMm - minMm;

  for (let i = 0; i < N; i++) {
    const sample = samples[i]!;
    const center = sample.center;
    const n = sample.normal;
    const b = sample.binormal;
    const ry = sample.rawRadiusY * sample.renderScale;
    const rz = sample.rawRadiusZ * sample.renderScale;

    // Colors remain tied to the raw measurement thickness, even if rendering clamps.
    const avgThicknessMm = sample.rawThicknessMm;
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

      if (nLen > VECTOR_EPSILON) {
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

<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, shallowRef } from 'vue';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { FrameData, MultiViewAnalysisDirection } from '../lib/api';
import { formatMultiViewDirection } from '../lib/domain/multiViewDirections';
import { buildTubeGeometry } from '../lib/tubeGeometry';
import { createColormap } from '../lib/colormap';
import { downloadCanvas } from '../lib/download';

const props = defineProps<{
  leftFrameData: FrameData | null;
  rightFrameData: FrameData | null;
  leftPixelToMmFactor: number;
  rightPixelToMmFactor: number;
  heatmapMinMm: number | null;
  heatmapMaxMm: number | null;
  leftDirection: MultiViewAnalysisDirection;
  rightDirection: MultiViewAnalysisDirection;
  highlightedPointIndex?: number | null;
  highlightSelectedPoint?: boolean;
  exportFilename?: string;
}>();

const emit = defineEmits<{
  'export-availability-change': [available: boolean];
}>();

const containerRef = ref<HTMLDivElement | null>(null);
const canvasRef = ref<HTMLCanvasElement | null>(null);
const hasData = ref(false);

const colormap = createColormap();

// Three.js objects held as shallow refs to avoid Vue reactivity overhead
const renderer = shallowRef<THREE.WebGLRenderer | null>(null);
const scene = shallowRef<THREE.Scene | null>(null);
const camera = shallowRef<THREE.PerspectiveCamera | null>(null);
const controls = shallowRef<OrbitControls | null>(null);
const tubeMesh = shallowRef<THREE.Mesh | null>(null);
const geometry = shallowRef<THREE.BufferGeometry | null>(null);
const material = shallowRef<THREE.MeshPhongMaterial | null>(null);
const highlightRing = shallowRef<THREE.LineLoop | null>(null);
const highlightGeometry = shallowRef<THREE.BufferGeometry | null>(null);
const highlightMaterial = shallowRef<THREE.LineBasicMaterial | null>(null);

let dirty = true;
let animFrameId = 0;
let resizeObserver: ResizeObserver | null = null;
let hasFramedCamera = false;

const DEFAULT_TUBE_OPACITY = 1;
const DIMMED_TUBE_OPACITY = 0.18;
const HIGHLIGHT_RING_SCALE = 1.04;

function clearGeometry(): void {
  hasData.value = false;
  if (!geometry.value) {
    updateHighlightState();
    return;
  }

  geometry.value.setIndex(null);
  geometry.value.deleteAttribute('position');
  geometry.value.deleteAttribute('normal');
  geometry.value.deleteAttribute('color');
  updateHighlightState();
  requestRender();
}

function requestRender() {
  dirty = true;
}

async function captureCurrentViewFullHdCanvas(): Promise<HTMLCanvasElement> {
  if (!hasData.value || !scene.value || !camera.value) {
    throw new Error('No 3D geometry available for export');
  }

  controls.value?.update();

  const exportCanvas = document.createElement('canvas');
  const exportRenderer = new THREE.WebGLRenderer({
    canvas: exportCanvas,
    antialias: true,
    alpha: true,
    preserveDrawingBuffer: true,
  });

  try {
    exportRenderer.setPixelRatio(1);
    exportRenderer.setSize(1920, 1080, false);

    const exportCamera = camera.value.clone();
    exportCamera.aspect = 1920 / 1080;
    exportCamera.updateProjectionMatrix();

    exportRenderer.render(scene.value, exportCamera);
    const copyCanvas = document.createElement('canvas');
    copyCanvas.width = exportCanvas.width;
    copyCanvas.height = exportCanvas.height;
    const copyCtx = copyCanvas.getContext('2d');
    if (!copyCtx) {
      throw new Error('Failed to create 3D export copy context');
    }
    copyCtx.drawImage(exportCanvas, 0, 0);
    return copyCanvas;
  } finally {
    exportRenderer.dispose();
    exportRenderer.forceContextLoss();
  }
}

async function downloadCurrentViewFullHd(): Promise<void> {
  const exportCanvas = await captureCurrentViewFullHdCanvas();
  await downloadCanvas(
    exportCanvas,
    props.exportFilename ?? 'multiview_3d.png',
  );
}

function renderLoop() {
  animFrameId = requestAnimationFrame(renderLoop);
  if (!dirty || !renderer.value || !scene.value || !camera.value) return;
  dirty = false;
  renderer.value.render(scene.value, camera.value);
}

function initThree() {
  if (!canvasRef.value || !containerRef.value) return;

  const w = containerRef.value.clientWidth;
  const h = containerRef.value.clientHeight;

  // Renderer
  const r = new THREE.WebGLRenderer({
    canvas: canvasRef.value,
    antialias: true,
    alpha: true,
  });
  r.setPixelRatio(window.devicePixelRatio);
  r.setSize(w, h);
  renderer.value = r;

  // Scene
  const s = new THREE.Scene();
  s.background = new THREE.Color(0x1a1a2e);
  scene.value = s;

  // Camera
  const cam = new THREE.PerspectiveCamera(50, w / h, 0.1, 1000);
  cam.position.set(0, 5, 15);
  camera.value = cam;

  // Controls
  const ctrl = new OrbitControls(cam, r.domElement);
  ctrl.enableDamping = true;
  ctrl.dampingFactor = 0.1;
  ctrl.addEventListener('change', requestRender);
  controls.value = ctrl;

  // Lights
  const ambient = new THREE.AmbientLight(0xffffff, 0.5);
  s.add(ambient);

  const dir = new THREE.DirectionalLight(0xffffff, 0.8);
  dir.position.set(5, 10, 7);
  s.add(dir);

  const dir2 = new THREE.DirectionalLight(0xffffff, 0.3);
  dir2.position.set(-5, -5, -7);
  s.add(dir2);

  // Geometry + Material (reused across updates)
  const geo = new THREE.BufferGeometry();
  geometry.value = geo;

  const mat = new THREE.MeshPhongMaterial({
    vertexColors: true,
    side: THREE.DoubleSide,
    shininess: 40,
  });
  material.value = mat;

  const mesh = new THREE.Mesh(geo, mat);
  s.add(mesh);
  tubeMesh.value = mesh;

  const ringGeo = new THREE.BufferGeometry();
  highlightGeometry.value = ringGeo;

  const ringMat = new THREE.LineBasicMaterial({
    color: 0xffc247,
    transparent: true,
    opacity: 1,
    depthTest: false,
    depthWrite: false,
  });
  highlightMaterial.value = ringMat;

  const ring = new THREE.LineLoop(ringGeo, ringMat);
  ring.visible = false;
  ring.renderOrder = 10;
  s.add(ring);
  highlightRing.value = ring;

  // Resize observer
  resizeObserver = new ResizeObserver(() => {
    if (!containerRef.value || !renderer.value || !camera.value) return;
    const cw = containerRef.value.clientWidth;
    const ch = containerRef.value.clientHeight;
    renderer.value.setSize(cw, ch);
    camera.value.aspect = cw / ch;
    camera.value.updateProjectionMatrix();
    requestRender();
  });
  resizeObserver.observe(containerRef.value);

  renderLoop();
}

function updateTube() {
  const left = props.leftFrameData;
  const right = props.rightFrameData;

  if (
    !left?.mpp ||
    !right?.mpp ||
    left.mpp.length < 2 ||
    right.mpp.length < 2 ||
    !geometry.value
  ) {
    clearGeometry();
    return;
  }

  const minMm = props.heatmapMinMm ?? 0;
  const maxMm = props.heatmapMaxMm ?? 5;

  const data = buildTubeGeometry(
    left.mpp,
    right.mpp,
    props.leftPixelToMmFactor,
    props.rightPixelToMmFactor,
    colormap,
    minMm,
    maxMm,
    props.leftDirection,
    props.rightDirection,
  );

  if (data.positions.length === 0) {
    clearGeometry();
    return;
  }

  const geo = geometry.value;

  // Update or create buffer attributes
  const posAttr = geo.getAttribute('position') as THREE.BufferAttribute | null;
  if (posAttr && posAttr.array.length === data.positions.length) {
    (posAttr.array as Float32Array).set(data.positions);
    posAttr.needsUpdate = true;
  } else {
    geo.setAttribute('position', new THREE.BufferAttribute(data.positions, 3));
  }

  const normAttr = geo.getAttribute('normal') as THREE.BufferAttribute | null;
  if (normAttr && normAttr.array.length === data.normals.length) {
    (normAttr.array as Float32Array).set(data.normals);
    normAttr.needsUpdate = true;
  } else {
    geo.setAttribute('normal', new THREE.BufferAttribute(data.normals, 3));
  }

  const colorAttr = geo.getAttribute('color') as THREE.BufferAttribute | null;
  if (colorAttr && colorAttr.array.length === data.colors.length) {
    (colorAttr.array as Float32Array).set(data.colors);
    colorAttr.needsUpdate = true;
  } else {
    geo.setAttribute('color', new THREE.BufferAttribute(data.colors, 3));
  }

  geo.setIndex(new THREE.BufferAttribute(data.indices, 1));
  geo.computeBoundingSphere();

  hasData.value = true;

  // Auto-frame camera on first valid data
  if (!hasFramedCamera) {
    frameCameraToGeometry();
    hasFramedCamera = true;
  }

  updateHighlightState();
  requestRender();
}

function resetTubeAppearance(): void {
  if (!material.value) {
    return;
  }

  material.value.transparent = false;
  material.value.opacity = DEFAULT_TUBE_OPACITY;
  material.value.depthWrite = true;
  material.value.needsUpdate = true;
}

function hideHighlightRing(): void {
  if (highlightRing.value) {
    highlightRing.value.visible = false;
  }
}

function getSampleCount(): number {
  const leftSampleCount = props.leftFrameData?.mpp?.length ?? 0;
  const rightSampleCount = props.rightFrameData?.mpp?.length ?? 0;
  return Math.min(leftSampleCount, rightSampleCount);
}

function updateHighlightState(): void {
  resetTubeAppearance();

  if (!highlightRing.value || !highlightGeometry.value || !geometry.value) {
    return;
  }

  const highlightIndex = props.highlightSelectedPoint
    ? props.highlightedPointIndex ?? null
    : null;

  if (highlightIndex === null || highlightIndex < 0 || !hasData.value) {
    hideHighlightRing();
    requestRender();
    return;
  }

  const sampleCount = getSampleCount();
  const positionAttr = geometry.value.getAttribute('position') as THREE.BufferAttribute | null;

  if (!positionAttr || sampleCount <= 0 || highlightIndex >= sampleCount) {
    hideHighlightRing();
    requestRender();
    return;
  }

  const verticesPerRing = positionAttr.count / sampleCount;
  if (!Number.isInteger(verticesPerRing) || verticesPerRing < 4) {
    hideHighlightRing();
    requestRender();
    return;
  }

  const ringVertexCount = verticesPerRing - 1;
  const source = positionAttr.array as Float32Array;
  const startOffset = highlightIndex * verticesPerRing * 3;
  const ringPositions = new Float32Array(ringVertexCount * 3);

  let centerX = 0;
  let centerY = 0;
  let centerZ = 0;

  for (let i = 0; i < ringVertexCount; i += 1) {
    const sourceOffset = startOffset + i * 3;
    centerX += source[sourceOffset] ?? 0;
    centerY += source[sourceOffset + 1] ?? 0;
    centerZ += source[sourceOffset + 2] ?? 0;
  }

  centerX /= ringVertexCount;
  centerY /= ringVertexCount;
  centerZ /= ringVertexCount;

  for (let i = 0; i < ringVertexCount; i += 1) {
    const sourceOffset = startOffset + i * 3;
    const targetOffset = i * 3;

    const x = source[sourceOffset] ?? 0;
    const y = source[sourceOffset + 1] ?? 0;
    const z = source[sourceOffset + 2] ?? 0;

    ringPositions[targetOffset] = centerX + (x - centerX) * HIGHLIGHT_RING_SCALE;
    ringPositions[targetOffset + 1] = centerY + (y - centerY) * HIGHLIGHT_RING_SCALE;
    ringPositions[targetOffset + 2] = centerZ + (z - centerZ) * HIGHLIGHT_RING_SCALE;
  }

  const ringPositionAttr = highlightGeometry.value.getAttribute('position') as THREE.BufferAttribute | null;
  if (ringPositionAttr && ringPositionAttr.array.length === ringPositions.length) {
    (ringPositionAttr.array as Float32Array).set(ringPositions);
    ringPositionAttr.needsUpdate = true;
  } else {
    highlightGeometry.value.setAttribute('position', new THREE.BufferAttribute(ringPositions, 3));
  }
  highlightGeometry.value.computeBoundingSphere();

  if (material.value) {
    material.value.transparent = true;
    material.value.opacity = DIMMED_TUBE_OPACITY;
    material.value.depthWrite = false;
    material.value.needsUpdate = true;
  }

  highlightRing.value.visible = true;
  requestRender();
}

function frameCameraToGeometry() {
  if (!geometry.value || !camera.value || !controls.value) return;

  geometry.value.computeBoundingBox();
  const box = geometry.value.boundingBox;
  if (!box) return;

  const center = new THREE.Vector3();
  box.getCenter(center);

  const size = new THREE.Vector3();
  box.getSize(size);
  const maxDim = Math.max(size.x, size.y, size.z);

  const fov = camera.value.fov * (Math.PI / 180);
  const distance = maxDim / (2 * Math.tan(fov / 2)) * .8;

  camera.value.position.set(center.x, center.y + distance * 0.3, center.z + distance);
  controls.value.target.copy(center);
  controls.value.update();
  requestRender();
}

onMounted(() => {
  initThree();
  updateTube();
});

onUnmounted(() => {
  if (animFrameId) cancelAnimationFrame(animFrameId);
  if (resizeObserver) resizeObserver.disconnect();
  if (controls.value) controls.value.dispose();
  if (geometry.value) geometry.value.dispose();
  if (material.value) material.value.dispose();
  if (highlightGeometry.value) highlightGeometry.value.dispose();
  if (highlightMaterial.value) highlightMaterial.value.dispose();
  if (renderer.value) {
    renderer.value.dispose();
    renderer.value.forceContextLoss();
  }
});

watch(
  () => [
    props.leftFrameData,
    props.rightFrameData,
    props.leftPixelToMmFactor,
    props.rightPixelToMmFactor,
    props.heatmapMinMm,
    props.heatmapMaxMm,
    props.leftDirection,
    props.rightDirection,
  ],
  () => {
    updateTube();
  },
  { deep: true },
);

watch(
  () => [props.highlightedPointIndex, props.highlightSelectedPoint],
  () => {
    updateHighlightState();
  },
);

watch(
  hasData,
  (available) => {
    emit('export-availability-change', available);
  },
  { immediate: true },
);

defineExpose({
  captureCurrentViewFullHdCanvas,
  downloadCurrentViewFullHd,
});
</script>

<template>
  <div ref="containerRef" class="viewer-3d-root">
    <canvas ref="canvasRef" class="viewer-3d-canvas" />
    <div v-if="!hasData" class="viewer-3d-empty">
      <p v-if="props.leftDirection === props.rightDirection">
        Assign one {{ formatMultiViewDirection('front').toLowerCase() }} view and one {{ formatMultiViewDirection('bottom').toLowerCase() }} view to render the 3D reconstruction
      </p>
      <p v-else>Scrub to a frame with analysis data to view the 3D reconstruction</p>
    </div>
    <div class="viewer-3d-hint">
      Drag to orbit &middot; Scroll to zoom &middot; Right-drag to pan
    </div>
  </div>
</template>

<style scoped>
.viewer-3d-root {
  position: relative;
  width: 100%;
  min-height: 500px;
  height: 100%;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  overflow: hidden;
  background: #1a1a2e;
}

.viewer-3d-canvas {
  display: block;
  width: 100%;
  height: 100%;
}

.viewer-3d-empty {
  position: absolute;
  inset: 0;
  display: flex;
  align-items: center;
  justify-content: center;
  color: rgba(255, 255, 255, 0.5);
  font-size: 0.9rem;
  pointer-events: none;
}

.viewer-3d-hint {
  position: absolute;
  bottom: 0.5rem;
  right: 0.75rem;
  font-size: 0.7rem;
  color: rgba(255, 255, 255, 0.35);
  pointer-events: none;
}
</style>

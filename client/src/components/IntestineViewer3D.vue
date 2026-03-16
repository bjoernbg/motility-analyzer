<script setup lang="ts">
import { ref, watch, onMounted, onUnmounted, shallowRef } from 'vue';
import * as THREE from 'three';
import { OrbitControls } from 'three/addons/controls/OrbitControls.js';
import type { FrameData } from '../lib/api';
import { buildTubeGeometry } from '../lib/tubeGeometry';
import { createColormap } from '../lib/colormap';

const props = defineProps<{
  leftFrameData: FrameData | null;
  rightFrameData: FrameData | null;
  leftPixelToMmFactor: number;
  rightPixelToMmFactor: number;
  heatmapMinMm: number | null;
  heatmapMaxMm: number | null;
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

let dirty = true;
let animFrameId = 0;
let resizeObserver: ResizeObserver | null = null;
let hasFramedCamera = false;

function requestRender() {
  dirty = true;
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
    hasData.value = false;
    if (geometry.value) {
      geometry.value.setIndex(null);
      geometry.value.deleteAttribute('position');
      geometry.value.deleteAttribute('normal');
      geometry.value.deleteAttribute('color');
      requestRender();
    }
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
  );

  if (data.positions.length === 0) {
    hasData.value = false;
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
  const distance = maxDim / (2 * Math.tan(fov / 2)) * 1.5;

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
  ],
  () => {
    updateTube();
  },
  { deep: true },
);
</script>

<template>
  <div ref="containerRef" class="viewer-3d-root">
    <canvas ref="canvasRef" class="viewer-3d-canvas" />
    <div v-if="!hasData" class="viewer-3d-empty">
      <p>Scrub to a frame with analysis data to view the 3D reconstruction</p>
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

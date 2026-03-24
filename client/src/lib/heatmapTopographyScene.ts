import * as THREE from 'three';

import type {
  HeatmapTopographyFrameLine,
  HeatmapTopographySurface,
} from './heatmapTopography';
import {
  resolveTopographyFrameFromWorldX,
  resolveTopographyPointIndexFromWorldY,
} from './heatmapTopography';

export interface HeatmapTopographyPickResult {
  frame: number;
  pointIndex: number;
}

export interface HeatmapTopographySceneController {
  beginPan: (clientX: number, clientY: number) => void;
  captureCanvas: (width: number, height: number) => HTMLCanvasElement;
  dispose: () => void;
  endPan: () => void;
  pick: (clientX: number, clientY: number) => HeatmapTopographyPickResult | null;
  resize: () => void;
  setFrameLine: (frameLine: HeatmapTopographyFrameLine | null) => void;
  setSurface: (surface: HeatmapTopographySurface | null) => void;
  updatePan: (clientX: number, clientY: number) => void;
  zoom: (deltaY: number) => void;
}

export interface CreateHeatmapTopographySceneOptions {
  canvas: HTMLCanvasElement;
  container: HTMLElement;
}

const CAMERA_DIRECTION = new THREE.Vector3(1.15, -1.2, 0.9).normalize();
const CAMERA_PADDING = 1.25;
const CAMERA_MIN_FRUSTUM_HEIGHT = 12;
const CAMERA_NEAR = 0.1;
const MIN_ZOOM = 0.6;
const MAX_ZOOM = 12;
const BACKGROUND_COLOR = 0x09131f;

export function createHeatmapTopographyScene(
  options: CreateHeatmapTopographySceneOptions,
): HeatmapTopographySceneController {
  const { canvas, container } = options;
  const renderer = new THREE.WebGLRenderer({
    alpha: true,
    antialias: true,
    canvas,
  });
  const scene = new THREE.Scene();
  const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, CAMERA_NEAR, 5000);
  const surfaceGeometry = new THREE.BufferGeometry();
  const surfaceMaterial = new THREE.MeshPhongMaterial({
    flatShading: true,
    shininess: 28,
    side: THREE.DoubleSide,
    vertexColors: true,
  });
  const surfaceMesh = new THREE.Mesh(surfaceGeometry, surfaceMaterial);
  const frameLineGeometry = new THREE.BufferGeometry();
  const frameLineMaterial = new THREE.LineBasicMaterial({
    color: 0xffffff,
    depthTest: false,
    depthWrite: false,
    opacity: 0.95,
    transparent: true,
  });
  const frameLine = new THREE.Line(frameLineGeometry, frameLineMaterial);
  const raycaster = new THREE.Raycaster();
  const pointer = new THREE.Vector2();
  const cameraTarget = new THREE.Vector3(0, 0, 0);
  const box = new THREE.Box3();
  const corner = new THREE.Vector3();
  let wireframe: THREE.LineSegments | null = null;
  let surface: HeatmapTopographySurface | null = null;
  let baseFrustumHeight = CAMERA_MIN_FRUSTUM_HEIGHT;
  let lastPanX = 0;
  let lastPanY = 0;

  renderer.setPixelRatio(window.devicePixelRatio || 1);
  scene.background = new THREE.Color(BACKGROUND_COLOR);

  camera.up.set(0, 0, 1);

  surfaceMesh.castShadow = false;
  surfaceMesh.receiveShadow = false;
  scene.add(surfaceMesh);

  frameLine.renderOrder = 10;
  frameLine.visible = false;
  scene.add(frameLine);

  scene.add(new THREE.AmbientLight(0xffffff, 0.78));

  const keyLight = new THREE.DirectionalLight(0xffffff, 0.92);
  keyLight.position.set(18, -14, 26);
  scene.add(keyLight);

  const fillLight = new THREE.DirectionalLight(0x8fc6ff, 0.38);
  fillLight.position.set(-18, 16, 12);
  scene.add(fillLight);

  resize();

  function applyFrustum(nextAspect: number): void {
    const halfHeight = baseFrustumHeight / 2;
    const halfWidth = halfHeight * Math.max(nextAspect, 0.01);
    camera.left = -halfWidth;
    camera.right = halfWidth;
    camera.top = halfHeight;
    camera.bottom = -halfHeight;
    camera.updateProjectionMatrix();
  }

  function render(): void {
    renderer.render(scene, camera);
  }

  function updateCamera(distance: number): void {
    camera.position.copy(cameraTarget).addScaledVector(CAMERA_DIRECTION, distance);
    camera.near = CAMERA_NEAR;
    camera.far = Math.max(distance * 4, 1000);
    camera.lookAt(cameraTarget);
    camera.updateProjectionMatrix();
    camera.updateMatrixWorld();
  }

  function fitCameraToSurface(nextSurface: HeatmapTopographySurface): void {
    if (nextSurface.positions.length === 0) {
      baseFrustumHeight = CAMERA_MIN_FRUSTUM_HEIGHT;
      camera.zoom = 1;
      updateCamera(40);
      applyFrustum(getAspect());
      render();
      return;
    }

    box.makeEmpty();
    for (let offset = 0; offset < nextSurface.positions.length; offset += 3) {
      corner.set(
        nextSurface.positions[offset] ?? 0,
        nextSurface.positions[offset + 1] ?? 0,
        nextSurface.positions[offset + 2] ?? 0,
      );
      box.expandByPoint(corner);
    }

    const center = box.getCenter(new THREE.Vector3());
    const size = box.getSize(new THREE.Vector3());
    const distance = Math.max(size.length() * 1.2, 40);

    cameraTarget.copy(center);
    updateCamera(distance);

    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
    let minX = Infinity;
    let maxX = -Infinity;
    let minY = Infinity;
    let maxY = -Infinity;

    for (const x of [box.min.x, box.max.x]) {
      for (const y of [box.min.y, box.max.y]) {
        for (const z of [box.min.z, box.max.z]) {
          corner.set(x, y, z).sub(center);
          const projectedX = corner.dot(right);
          const projectedY = corner.dot(up);
          minX = Math.min(minX, projectedX);
          maxX = Math.max(maxX, projectedX);
          minY = Math.min(minY, projectedY);
          maxY = Math.max(maxY, projectedY);
        }
      }
    }

    const projectedWidth = Math.max(maxX - minX, 1);
    const projectedHeight = Math.max(maxY - minY, 1);
    const aspect = getAspect();
    baseFrustumHeight = Math.max(
      CAMERA_MIN_FRUSTUM_HEIGHT,
      projectedHeight * CAMERA_PADDING,
      (projectedWidth / Math.max(aspect, 0.01)) * CAMERA_PADDING,
    );
    camera.zoom = 1;
    applyFrustum(aspect);
    render();
  }

  function disposeWireframe(): void {
    if (!wireframe) {
      return;
    }

    scene.remove(wireframe);
    wireframe.geometry.dispose();
    (wireframe.material as THREE.Material).dispose();
    wireframe = null;
  }

  function rebuildWireframe(): void {
    disposeWireframe();

    if (!surface || surface.positions.length === 0 || surface.indices.length === 0) {
      return;
    }

    const geometry = new THREE.WireframeGeometry(surfaceGeometry);
    const material = new THREE.LineBasicMaterial({
      color: 0x10243a,
      opacity: 0.22,
      transparent: true,
    });
    wireframe = new THREE.LineSegments(geometry, material);
    scene.add(wireframe);
  }

  function getAspect(): number {
    const width = Math.max(container.clientWidth, 1);
    const height = Math.max(container.clientHeight, 1);
    return width / height;
  }

  function resize(): void {
    const width = Math.max(container.clientWidth, 1);
    const height = Math.max(container.clientHeight, 1);
    renderer.setSize(width, height, false);
    applyFrustum(width / height);
    render();
  }

  function setSurface(nextSurface: HeatmapTopographySurface | null): void {
    surface = nextSurface;

    if (!nextSurface || nextSurface.positions.length === 0 || nextSurface.indices.length === 0) {
      surfaceGeometry.setIndex(null);
      surfaceGeometry.deleteAttribute('position');
      surfaceGeometry.deleteAttribute('color');
      surfaceGeometry.deleteAttribute('normal');
      surfaceMesh.visible = false;
      disposeWireframe();
      render();
      return;
    }

    surfaceGeometry.setAttribute('position', new THREE.BufferAttribute(nextSurface.positions, 3));
    surfaceGeometry.setAttribute('color', new THREE.BufferAttribute(nextSurface.colors, 3));
    surfaceGeometry.setIndex(new THREE.BufferAttribute(nextSurface.indices, 1));
    surfaceGeometry.computeVertexNormals();
    surfaceGeometry.computeBoundingSphere();
    surfaceMesh.visible = true;
    rebuildWireframe();
    fitCameraToSurface(nextSurface);
  }

  function setFrameLine(nextFrameLine: HeatmapTopographyFrameLine | null): void {
    if (!nextFrameLine || nextFrameLine.positions.length === 0) {
      frameLine.visible = false;
      frameLineGeometry.deleteAttribute('position');
      render();
      return;
    }

    frameLineGeometry.setAttribute('position', new THREE.BufferAttribute(nextFrameLine.positions, 3));
    frameLineGeometry.computeBoundingSphere();
    frameLine.visible = true;
    render();
  }

  function pick(clientX: number, clientY: number): HeatmapTopographyPickResult | null {
    if (!surface || !surfaceMesh.visible) {
      return null;
    }

    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return null;
    }

    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1;
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1;
    raycaster.setFromCamera(pointer, camera);

    const hit = raycaster.intersectObject(surfaceMesh, false)[0];
    if (!hit) {
      return null;
    }

    return {
      frame: resolveTopographyFrameFromWorldX(hit.point.x, surface.metrics),
      pointIndex: resolveTopographyPointIndexFromWorldY(hit.point.y, surface.metrics),
    };
  }

  function zoom(deltaY: number): void {
    camera.zoom = THREE.MathUtils.clamp(
      camera.zoom * (deltaY < 0 ? 1.12 : 0.9),
      MIN_ZOOM,
      MAX_ZOOM,
    );
    camera.updateProjectionMatrix();
    render();
  }

  function beginPan(clientX: number, clientY: number): void {
    lastPanX = clientX;
    lastPanY = clientY;
  }

  function updatePan(clientX: number, clientY: number): void {
    const dx = clientX - lastPanX;
    const dy = clientY - lastPanY;
    lastPanX = clientX;
    lastPanY = clientY;

    const rect = canvas.getBoundingClientRect();
    if (rect.width <= 0 || rect.height <= 0) {
      return;
    }

    const frustumWidth = (camera.right - camera.left) / camera.zoom;
    const frustumHeight = (camera.top - camera.bottom) / camera.zoom;
    const worldDeltaX = (-dx / rect.width) * frustumWidth;
    const worldDeltaY = (dy / rect.height) * frustumHeight;
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize();
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize();
    const translation = right.multiplyScalar(worldDeltaX).add(up.multiplyScalar(worldDeltaY));

    camera.position.add(translation);
    cameraTarget.add(translation);
    camera.lookAt(cameraTarget);
    camera.updateMatrixWorld();
    render();
  }

  function endPan(): void {
    // Intentionally empty. Pointer state is handled by the component.
  }

  function captureCanvas(width: number, height: number): HTMLCanvasElement {
    if (!surface || !surfaceMesh.visible) {
      throw new Error('No topography surface available for export');
    }

    const exportCanvas = document.createElement('canvas');
    const exportRenderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      canvas: exportCanvas,
      preserveDrawingBuffer: true,
    });

    try {
      exportRenderer.setPixelRatio(1);
      exportRenderer.setSize(width, height, false);

      const exportCamera = camera.clone() as THREE.OrthographicCamera;
      exportCamera.up.copy(camera.up);
      exportCamera.position.copy(camera.position);
      exportCamera.zoom = camera.zoom;

      const halfHeight = baseFrustumHeight / 2;
      const halfWidth = halfHeight * (width / Math.max(height, 1));
      exportCamera.left = -halfWidth;
      exportCamera.right = halfWidth;
      exportCamera.top = halfHeight;
      exportCamera.bottom = -halfHeight;
      exportCamera.near = camera.near;
      exportCamera.far = camera.far;
      exportCamera.lookAt(cameraTarget);
      exportCamera.updateProjectionMatrix();
      exportCamera.updateMatrixWorld();

      exportRenderer.render(scene, exportCamera);

      const copyCanvas = document.createElement('canvas');
      copyCanvas.width = exportCanvas.width;
      copyCanvas.height = exportCanvas.height;
      const copyContext = copyCanvas.getContext('2d');
      if (!copyContext) {
        throw new Error('Failed to create topography export context');
      }

      copyContext.drawImage(exportCanvas, 0, 0);
      return copyCanvas;
    } finally {
      exportRenderer.dispose();
      exportRenderer.forceContextLoss();
    }
  }

  function dispose(): void {
    disposeWireframe();
    surfaceGeometry.dispose();
    surfaceMaterial.dispose();
    frameLineGeometry.dispose();
    frameLineMaterial.dispose();
    renderer.dispose();
    renderer.forceContextLoss();
  }

  return {
    beginPan,
    captureCanvas,
    dispose,
    endPan,
    pick,
    resize,
    setFrameLine,
    setSurface,
    updatePan,
    zoom,
  };
}

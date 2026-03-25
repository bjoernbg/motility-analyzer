import * as THREE from 'three'

import type {
  HeatmapTopographyAxes,
  HeatmapTopographyFrameLine,
  HeatmapTopographySurface,
} from './heatmapTopography'
import {
  resolveTopographyFrameFromWorldX,
  resolveTopographyPointIndexFromWorldY,
} from './heatmapTopography'

export interface HeatmapTopographyPickResult {
  frame: number
  pointIndex: number
}

export interface HeatmapTopographySceneController {
  beginPan: (clientX: number, clientY: number) => void
  captureCanvas: (width: number, height: number) => HTMLCanvasElement
  dispose: () => void
  endPan: () => void
  pick: (clientX: number, clientY: number) => HeatmapTopographyPickResult | null
  resize: () => void
  setAxes: (axes: HeatmapTopographyAxes | null) => void
  setClippingHeight: (height: number | null) => void
  setFrameLine: (frameLine: HeatmapTopographyFrameLine | null) => void
  setSurface: (surface: HeatmapTopographySurface | null) => void
  updatePan: (clientX: number, clientY: number) => void
  zoom: (deltaY: number) => void
}

export interface CreateHeatmapTopographySceneOptions {
  canvas: HTMLCanvasElement
  container: HTMLElement
}

const CAMERA_DIRECTION = new THREE.Vector3(1.15, -1.2, 0.9).normalize()
const CAMERA_PADDING = 1.25
const CAMERA_MIN_FRUSTUM_HEIGHT = 12
const CAMERA_NEAR = 0.1
const MIN_ZOOM = 0.6
const MAX_ZOOM = 12
const BACKGROUND_COLOR = 0x09131f
const AXIS_PLANE_COLOR = 0xd7e1ea
const AXIS_LINE_COLOR = 0xc6d4e2
const AXIS_LABEL_COLOR = '#edf4fb'
const AXIS_LABEL_BACKGROUND = 'rgba(9, 19, 31, 0.82)'
const CLIPPING_GUIDE_COLOR = 0x9fd4ff
const CLIPPING_GUIDE_OPACITY = 0.2
const CLIPPING_PICK_EPSILON = 1e-6

function disposeMaterial(material: THREE.Material): void {
  const materialWithMap = material as THREE.Material & { map?: THREE.Texture | null }
  materialWithMap.map?.dispose()
  material.dispose()
}

function disposeObjectResources(root: THREE.Object3D): void {
  root.traverse((child) => {
    const geometry = (child as THREE.Mesh).geometry
    if (geometry instanceof THREE.BufferGeometry) {
      geometry.dispose()
    }

    const material = (child as THREE.Mesh).material
    if (Array.isArray(material)) {
      material.forEach(disposeMaterial)
      return
    }

    if (material instanceof THREE.Material) {
      disposeMaterial(material)
    }
  })
}

function createLabelSprite(text: string, worldHeight: number): THREE.Sprite {
  const fontSize = 56
  const paddingX = 26
  const paddingY = 18
  const canvas = document.createElement('canvas')
  const context = canvas.getContext('2d')
  if (!context) {
    throw new Error('Failed to create topography axis label')
  }

  context.font = `600 ${fontSize}px "Helvetica Neue", Arial, sans-serif`
  const textMetrics = context.measureText(text)
  canvas.width = Math.ceil(textMetrics.width + paddingX * 2)
  canvas.height = Math.ceil(fontSize + paddingY * 2)

  const resizedContext = canvas.getContext('2d')
  if (!resizedContext) {
    throw new Error('Failed to create topography axis label context')
  }

  resizedContext.font = `600 ${fontSize}px "Helvetica Neue", Arial, sans-serif`
  resizedContext.fillStyle = AXIS_LABEL_BACKGROUND
  resizedContext.fillRect(0, 0, canvas.width, canvas.height)
  resizedContext.fillStyle = AXIS_LABEL_COLOR
  resizedContext.textAlign = 'center'
  resizedContext.textBaseline = 'middle'
  resizedContext.fillText(text, canvas.width / 2, canvas.height / 2)

  const texture = new THREE.CanvasTexture(canvas)
  texture.colorSpace = THREE.SRGBColorSpace
  texture.generateMipmaps = false
  texture.needsUpdate = true

  const sprite = new THREE.Sprite(
    new THREE.SpriteMaterial({
      depthTest: false,
      depthWrite: false,
      map: texture,
      transparent: true,
    }),
  )
  const aspect = canvas.width / Math.max(canvas.height, 1)
  sprite.renderOrder = 20
  sprite.scale.set(worldHeight * aspect, worldHeight, 1)
  return sprite
}

function createLineSegments(points: number[], opacity = 0.38): THREE.LineSegments {
  const geometry = new THREE.BufferGeometry()
  geometry.setAttribute('position', new THREE.Float32BufferAttribute(points, 3))
  const material = new THREE.LineBasicMaterial({
    color: AXIS_LINE_COLOR,
    depthTest: false,
    depthWrite: false,
    opacity,
    transparent: true,
  })
  const line = new THREE.LineSegments(geometry, material)
  line.renderOrder = 12
  return line
}

function createAxisPlane(width: number, height: number): THREE.Mesh {
  const material = new THREE.MeshBasicMaterial({
    color: AXIS_PLANE_COLOR,
    depthWrite: false,
    opacity: 0.08,
    side: THREE.DoubleSide,
    transparent: true,
  })
  const mesh = new THREE.Mesh(new THREE.PlaneGeometry(width, height), material)
  mesh.renderOrder = 2
  return mesh
}

export function createHeatmapTopographyScene(
  options: CreateHeatmapTopographySceneOptions,
): HeatmapTopographySceneController {
  const { canvas, container } = options
  const renderer = new THREE.WebGLRenderer({
    alpha: true,
    antialias: true,
    canvas,
  })
  const scene = new THREE.Scene()
  const camera = new THREE.OrthographicCamera(-10, 10, 10, -10, CAMERA_NEAR, 5000)
  const surfaceGeometry = new THREE.BufferGeometry()
  const surfaceMaterial = new THREE.MeshPhongMaterial({
    flatShading: true,
    shininess: 28,
    side: THREE.DoubleSide,
    vertexColors: true,
  })
  const surfaceMesh = new THREE.Mesh(surfaceGeometry, surfaceMaterial)
  const frameLineGeometry = new THREE.BufferGeometry()
  const frameLineMaterial = new THREE.LineBasicMaterial({
    color: 0xffffff,
    depthTest: false,
    depthWrite: false,
    opacity: 0.95,
    transparent: true,
  })
  const frameLine = new THREE.Line(frameLineGeometry, frameLineMaterial)
  const axisGroup = new THREE.Group()
  const raycaster = new THREE.Raycaster()
  const pointer = new THREE.Vector2()
  const cameraTarget = new THREE.Vector3(0, 0, 0)
  const box = new THREE.Box3()
  const corner = new THREE.Vector3()
  const clippingPlane = new THREE.Plane(new THREE.Vector3(0, 0, 1), 0)
  let wireframe: THREE.LineSegments | null = null
  let clippingGuide: THREE.Mesh | null = null
  let surface: HeatmapTopographySurface | null = null
  let axes: HeatmapTopographyAxes | null = null
  let clippingHeight: number | null = null
  let baseFrustumHeight = CAMERA_MIN_FRUSTUM_HEIGHT
  let lastPanX = 0
  let lastPanY = 0

  renderer.setPixelRatio(window.devicePixelRatio || 1)
  renderer.localClippingEnabled = true
  scene.background = new THREE.Color(BACKGROUND_COLOR)

  camera.up.set(0, 0, 1)

  surfaceMesh.castShadow = false
  surfaceMesh.receiveShadow = false
  scene.add(surfaceMesh)

  frameLine.renderOrder = 15
  frameLine.visible = false
  scene.add(frameLine)

  axisGroup.visible = false
  scene.add(axisGroup)

  scene.add(new THREE.AmbientLight(0xffffff, 0.78))

  const keyLight = new THREE.DirectionalLight(0xffffff, 0.92)
  keyLight.position.set(18, -14, 26)
  scene.add(keyLight)

  const fillLight = new THREE.DirectionalLight(0x8fc6ff, 0.38)
  fillLight.position.set(-18, 16, 12)
  scene.add(fillLight)

  resize()

  function applyFrustum(nextAspect: number): void {
    const halfHeight = baseFrustumHeight / 2
    const halfWidth = halfHeight * Math.max(nextAspect, 0.01)
    camera.left = -halfWidth
    camera.right = halfWidth
    camera.top = halfHeight
    camera.bottom = -halfHeight
    camera.updateProjectionMatrix()
  }

  function render(): void {
    renderer.render(scene, camera)
  }

  function updateCamera(distance: number): void {
    camera.position.copy(cameraTarget).addScaledVector(CAMERA_DIRECTION, distance)
    camera.near = CAMERA_NEAR
    camera.far = Math.max(distance * 4, 1000)
    camera.lookAt(cameraTarget)
    camera.updateProjectionMatrix()
    camera.updateMatrixWorld()
  }

  function fitCameraToContent(): void {
    const hasSurface = Boolean(surface && surface.positions.length > 0)
    const hasAxes = axisGroup.visible && axisGroup.children.length > 0
    if (!hasSurface && !hasAxes) {
      baseFrustumHeight = CAMERA_MIN_FRUSTUM_HEIGHT
      camera.zoom = 1
      updateCamera(40)
      applyFrustum(getAspect())
      render()
      return
    }

    box.makeEmpty()
    if (surface) {
      for (let offset = 0; offset < surface.positions.length; offset += 3) {
        corner.set(
          surface.positions[offset] ?? 0,
          surface.positions[offset + 1] ?? 0,
          surface.positions[offset + 2] ?? 0,
        )
        box.expandByPoint(corner)
      }
    }

    if (hasAxes) {
      axisGroup.updateWorldMatrix(true, true)
      box.expandByObject(axisGroup, true)
    }

    const center = box.getCenter(new THREE.Vector3())
    const size = box.getSize(new THREE.Vector3())
    const distance = Math.max(size.length() * 1.2, 40)

    cameraTarget.copy(center)
    updateCamera(distance)

    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize()
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize()
    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity

    for (const x of [box.min.x, box.max.x]) {
      for (const y of [box.min.y, box.max.y]) {
        for (const z of [box.min.z, box.max.z]) {
          corner.set(x, y, z).sub(center)
          const projectedX = corner.dot(right)
          const projectedY = corner.dot(up)
          minX = Math.min(minX, projectedX)
          maxX = Math.max(maxX, projectedX)
          minY = Math.min(minY, projectedY)
          maxY = Math.max(maxY, projectedY)
        }
      }
    }

    const projectedWidth = Math.max(maxX - minX, 1)
    const projectedHeight = Math.max(maxY - minY, 1)
    const aspect = getAspect()
    baseFrustumHeight = Math.max(
      CAMERA_MIN_FRUSTUM_HEIGHT,
      projectedHeight * CAMERA_PADDING,
      (projectedWidth / Math.max(aspect, 0.01)) * CAMERA_PADDING,
    )
    camera.zoom = 1
    applyFrustum(aspect)
    render()
  }

  function disposeWireframe(): void {
    if (!wireframe) {
      return
    }

    scene.remove(wireframe)
    wireframe.geometry.dispose()
    ;(wireframe.material as THREE.Material).dispose()
    wireframe = null
  }

  function disposeClippingGuide(): void {
    if (!clippingGuide) {
      return
    }

    scene.remove(clippingGuide)
    clippingGuide.geometry.dispose()
    ;(clippingGuide.material as THREE.Material).dispose()
    clippingGuide = null
  }

  function applyMaterialClipping(material: THREE.Material): void {
    material.clippingPlanes = clippingHeight === null ? [] : [clippingPlane]
    material.needsUpdate = true
  }

  function resolveClippingGuideBounds(): {
    centerX: number
    centerY: number
    spanX: number
    spanY: number
  } | null {
    if (axes) {
      const spanX = Math.max(axes.bounds.maxX - axes.bounds.minX, 1)
      const spanY = Math.max(axes.bounds.maxY - axes.bounds.minY, 1)

      return {
        centerX: (axes.bounds.minX + axes.bounds.maxX) / 2,
        centerY: (axes.bounds.minY + axes.bounds.maxY) / 2,
        spanX,
        spanY,
      }
    }

    if (!surface || surface.positions.length === 0) {
      return null
    }

    let minX = Infinity
    let maxX = -Infinity
    let minY = Infinity
    let maxY = -Infinity

    for (let offset = 0; offset < surface.positions.length; offset += 3) {
      const x = surface.positions[offset] ?? 0
      const y = surface.positions[offset + 1] ?? 0
      minX = Math.min(minX, x)
      maxX = Math.max(maxX, x)
      minY = Math.min(minY, y)
      maxY = Math.max(maxY, y)
    }

    return {
      centerX: (minX + maxX) / 2,
      centerY: (minY + maxY) / 2,
      spanX: Math.max(maxX - minX, 1),
      spanY: Math.max(maxY - minY, 1),
    }
  }

  function rebuildClippingGuide(): void {
    disposeClippingGuide()

    if (clippingHeight === null) {
      return
    }

    const bounds = resolveClippingGuideBounds()
    if (!bounds) {
      return
    }

    const material = new THREE.MeshBasicMaterial({
      color: CLIPPING_GUIDE_COLOR,
      depthTest: false,
      depthWrite: false,
      opacity: CLIPPING_GUIDE_OPACITY,
      side: THREE.DoubleSide,
      transparent: true,
    })
    const mesh = new THREE.Mesh(new THREE.PlaneGeometry(bounds.spanX, bounds.spanY), material)
    mesh.position.set(bounds.centerX, bounds.centerY, clippingHeight)
    mesh.renderOrder = 14
    clippingGuide = mesh
    scene.add(clippingGuide)
  }

  function rebuildWireframe(): void {
    disposeWireframe()

    if (!surface || surface.positions.length === 0 || surface.indices.length === 0) {
      return
    }

    const geometry = new THREE.WireframeGeometry(surfaceGeometry)
    const material = new THREE.LineBasicMaterial({
      color: 0x10243a,
      opacity: 0.22,
      transparent: true,
    })
    applyMaterialClipping(material)
    wireframe = new THREE.LineSegments(geometry, material)
    scene.add(wireframe)
  }

  function clearAxisGroup(): void {
    while (axisGroup.children.length > 0) {
      const child = axisGroup.children[0]
      if (!child) {
        break
      }
      axisGroup.remove(child)
      disposeObjectResources(child)
    }
  }

  function rebuildAxes(): void {
    clearAxisGroup()
    axisGroup.visible = false

    if (!axes) {
      return
    }

    const { bounds, xLabel, xTicks, yLabel, yTicks, zLabel, zTicks } = axes
    const spanX = Math.max(bounds.maxX - bounds.minX, 1)
    const spanY = Math.max(bounds.maxY - bounds.minY, 1)
    const spanZ = Math.max(bounds.maxZ - bounds.minZ, 1)
    const axisUnit = Math.max(Math.max(spanZ, Math.min(spanX, spanY) * 0.1) * 0.08, 0.6)
    const planeInset = axisUnit * 0.28
    const floorZ = bounds.minZ - planeInset
    const frontWallY = bounds.minY - axisUnit * 0.75
    const backWallY = bounds.maxY + axisUnit * 0.75
    const wallX = bounds.minX - axisUnit * 0.75
    const tickLength = axisUnit * 0.6
    const labelHeight = axisUnit * 0.8
    const axisLabelHeight = axisUnit
    const centerX = (bounds.minX + bounds.maxX) / 2
    const centerY = (bounds.minY + bounds.maxY) / 2
    const centerZ = (floorZ + bounds.maxZ) / 2

    const floorPlane = createAxisPlane(spanX, spanY)
    floorPlane.position.set(centerX, centerY, floorZ)
    axisGroup.add(floorPlane)

    const xzWall = createAxisPlane(spanX, bounds.maxZ - floorZ)
    xzWall.rotation.x = Math.PI / 2
    xzWall.position.set(centerX, backWallY, centerZ)
    axisGroup.add(xzWall)

    const yzWall = createAxisPlane(bounds.maxZ - floorZ, spanY)
    yzWall.rotation.y = Math.PI / 2
    yzWall.position.set(wallX, centerY, centerZ)
    axisGroup.add(yzWall)

    axisGroup.add(
      createLineSegments(
        [
          bounds.minX,
          bounds.minY,
          floorZ,
          bounds.maxX,
          bounds.minY,
          floorZ,
          bounds.maxX,
          bounds.minY,
          floorZ,
          bounds.maxX,
          bounds.maxY,
          floorZ,
          bounds.maxX,
          bounds.maxY,
          floorZ,
          bounds.minX,
          bounds.maxY,
          floorZ,
          bounds.minX,
          bounds.maxY,
          floorZ,
          bounds.minX,
          bounds.minY,
          floorZ,
          bounds.minX,
          backWallY,
          floorZ,
          bounds.maxX,
          backWallY,
          floorZ,
          bounds.maxX,
          backWallY,
          floorZ,
          bounds.maxX,
          backWallY,
          bounds.maxZ,
          bounds.maxX,
          backWallY,
          bounds.maxZ,
          bounds.minX,
          backWallY,
          bounds.maxZ,
          bounds.minX,
          backWallY,
          bounds.maxZ,
          bounds.minX,
          backWallY,
          floorZ,
          wallX,
          bounds.minY,
          floorZ,
          wallX,
          bounds.maxY,
          floorZ,
          wallX,
          bounds.maxY,
          floorZ,
          wallX,
          bounds.maxY,
          bounds.maxZ,
          wallX,
          bounds.maxY,
          bounds.maxZ,
          wallX,
          bounds.minY,
          bounds.maxZ,
          wallX,
          bounds.minY,
          bounds.maxZ,
          wallX,
          bounds.minY,
          floorZ,
        ],
        0.44,
      ),
    )

    const tickSegments: number[] = []
    for (const tick of xTicks) {
      tickSegments.push(
        tick.position,
        bounds.minY,
        floorZ,
        tick.position,
        bounds.minY - tickLength,
        floorZ,
      )
      const label = createLabelSprite(tick.label, labelHeight)
      label.position.set(tick.position, bounds.minY - tickLength - labelHeight * 0.45, floorZ)
      axisGroup.add(label)
    }

    for (const tick of yTicks) {
      tickSegments.push(
        bounds.maxX,
        tick.position,
        floorZ,
        bounds.maxX + tickLength,
        tick.position,
        floorZ,
      )
      const label = createLabelSprite(tick.label, labelHeight)
      label.position.set(bounds.maxX + tickLength + labelHeight * 0.45, tick.position, floorZ)
      axisGroup.add(label)
    }

    for (const tick of zTicks) {
      tickSegments.push(
        wallX,
        bounds.minY,
        tick.position,
        wallX,
        bounds.minY - tickLength,
        tick.position,
      )
      const label = createLabelSprite(tick.label, labelHeight)
      label.position.set(
        wallX - labelHeight * 0.55,
        bounds.minY - tickLength - labelHeight * 0.2,
        tick.position,
      )
      axisGroup.add(label)
    }

    axisGroup.add(createLineSegments(tickSegments, 0.55))

    const xAxisLabel = createLabelSprite(xLabel, axisLabelHeight)
    xAxisLabel.position.set(centerX, bounds.minY - tickLength - axisLabelHeight * 1.15, floorZ)
    axisGroup.add(xAxisLabel)

    const yAxisLabel = createLabelSprite(yLabel, axisLabelHeight)
    yAxisLabel.position.set(bounds.maxX + tickLength + axisLabelHeight * 1.25, centerY, floorZ)
    axisGroup.add(yAxisLabel)

    const zAxisLabel = createLabelSprite(zLabel, axisLabelHeight)
    zAxisLabel.position.set(
      wallX - axisLabelHeight * 0.8,
      frontWallY - axisLabelHeight * 0.7,
      centerZ,
    )
    axisGroup.add(zAxisLabel)

    axisGroup.visible = true
  }

  function getAspect(): number {
    const width = Math.max(container.clientWidth, 1)
    const height = Math.max(container.clientHeight, 1)
    return width / height
  }

  function resize(): void {
    const width = Math.max(container.clientWidth, 1)
    const height = Math.max(container.clientHeight, 1)
    renderer.setSize(width, height, false)
    applyFrustum(width / height)
    render()
  }

  function setSurface(nextSurface: HeatmapTopographySurface | null): void {
    surface = nextSurface

    if (!nextSurface || nextSurface.positions.length === 0 || nextSurface.indices.length === 0) {
      surfaceGeometry.setIndex(null)
      surfaceGeometry.deleteAttribute('position')
      surfaceGeometry.deleteAttribute('color')
      surfaceGeometry.deleteAttribute('normal')
      surfaceMesh.visible = false
      disposeWireframe()
      disposeClippingGuide()
      fitCameraToContent()
      return
    }

    surfaceGeometry.setAttribute('position', new THREE.BufferAttribute(nextSurface.positions, 3))
    surfaceGeometry.setAttribute('color', new THREE.BufferAttribute(nextSurface.colors, 3))
    surfaceGeometry.setIndex(new THREE.BufferAttribute(nextSurface.indices, 1))
    surfaceGeometry.computeVertexNormals()
    surfaceGeometry.computeBoundingSphere()
    surfaceMesh.visible = true
    rebuildWireframe()
    rebuildClippingGuide()
    fitCameraToContent()
  }

  function setAxes(nextAxes: HeatmapTopographyAxes | null): void {
    axes = nextAxes
    rebuildAxes()
    rebuildClippingGuide()
    fitCameraToContent()
  }

  function setClippingHeight(height: number | null): void {
    clippingHeight = typeof height === 'number' && Number.isFinite(height) ? height : null
    clippingPlane.constant = clippingHeight === null ? 0 : -clippingHeight

    applyMaterialClipping(surfaceMaterial)
    applyMaterialClipping(frameLineMaterial)

    if (wireframe) {
      applyMaterialClipping(wireframe.material as THREE.Material)
    }

    rebuildClippingGuide()
    render()
  }

  function setFrameLine(nextFrameLine: HeatmapTopographyFrameLine | null): void {
    if (!nextFrameLine || nextFrameLine.positions.length === 0) {
      frameLine.visible = false
      frameLineGeometry.deleteAttribute('position')
      render()
      return
    }

    frameLineGeometry.setAttribute(
      'position',
      new THREE.BufferAttribute(nextFrameLine.positions, 3),
    )
    frameLineGeometry.computeBoundingSphere()
    frameLine.visible = true
    render()
  }

  function pick(clientX: number, clientY: number): HeatmapTopographyPickResult | null {
    if (!surface || !surfaceMesh.visible) {
      return null
    }

    const rect = canvas.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) {
      return null
    }

    pointer.x = ((clientX - rect.left) / rect.width) * 2 - 1
    pointer.y = -((clientY - rect.top) / rect.height) * 2 + 1
    raycaster.setFromCamera(pointer, camera)

    const hit = raycaster.intersectObject(surfaceMesh, false).find((intersection) => {
      if (clippingHeight === null) {
        return true
      }

      return intersection.point.z >= clippingHeight - CLIPPING_PICK_EPSILON
    })
    if (!hit) {
      return null
    }

    return {
      frame: resolveTopographyFrameFromWorldX(hit.point.x, surface.metrics),
      pointIndex: resolveTopographyPointIndexFromWorldY(hit.point.y, surface.metrics),
    }
  }

  function zoom(deltaY: number): void {
    camera.zoom = THREE.MathUtils.clamp(camera.zoom * (deltaY < 0 ? 1.12 : 0.9), MIN_ZOOM, MAX_ZOOM)
    camera.updateProjectionMatrix()
    render()
  }

  function beginPan(clientX: number, clientY: number): void {
    lastPanX = clientX
    lastPanY = clientY
  }

  function updatePan(clientX: number, clientY: number): void {
    const dx = clientX - lastPanX
    const dy = clientY - lastPanY
    lastPanX = clientX
    lastPanY = clientY

    const rect = canvas.getBoundingClientRect()
    if (rect.width <= 0 || rect.height <= 0) {
      return
    }

    const frustumWidth = (camera.right - camera.left) / camera.zoom
    const frustumHeight = (camera.top - camera.bottom) / camera.zoom
    const worldDeltaX = (-dx / rect.width) * frustumWidth
    const worldDeltaY = (dy / rect.height) * frustumHeight
    const right = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 0).normalize()
    const up = new THREE.Vector3().setFromMatrixColumn(camera.matrixWorld, 1).normalize()
    const translation = right.multiplyScalar(worldDeltaX).add(up.multiplyScalar(worldDeltaY))

    camera.position.add(translation)
    cameraTarget.add(translation)
    camera.lookAt(cameraTarget)
    camera.updateMatrixWorld()
    render()
  }

  function endPan(): void {
    // Intentionally empty. Pointer state is handled by the component.
  }

  function captureCanvas(width: number, height: number): HTMLCanvasElement {
    if (!surface || !surfaceMesh.visible) {
      throw new Error('No topography surface available for export')
    }

    const exportCanvas = document.createElement('canvas')
    const exportRenderer = new THREE.WebGLRenderer({
      alpha: true,
      antialias: true,
      canvas: exportCanvas,
      preserveDrawingBuffer: true,
    })

    try {
      exportRenderer.setPixelRatio(1)
      exportRenderer.setSize(width, height, false)
      exportRenderer.localClippingEnabled = true

      const exportCamera = camera.clone() as THREE.OrthographicCamera
      exportCamera.up.copy(camera.up)
      exportCamera.position.copy(camera.position)
      exportCamera.zoom = camera.zoom

      const halfHeight = baseFrustumHeight / 2
      const halfWidth = halfHeight * (width / Math.max(height, 1))
      exportCamera.left = -halfWidth
      exportCamera.right = halfWidth
      exportCamera.top = halfHeight
      exportCamera.bottom = -halfHeight
      exportCamera.near = camera.near
      exportCamera.far = camera.far
      exportCamera.lookAt(cameraTarget)
      exportCamera.updateProjectionMatrix()
      exportCamera.updateMatrixWorld()

      exportRenderer.render(scene, exportCamera)

      const copyCanvas = document.createElement('canvas')
      copyCanvas.width = exportCanvas.width
      copyCanvas.height = exportCanvas.height
      const copyContext = copyCanvas.getContext('2d')
      if (!copyContext) {
        throw new Error('Failed to create topography export context')
      }

      copyContext.drawImage(exportCanvas, 0, 0)
      return copyCanvas
    } finally {
      exportRenderer.dispose()
      exportRenderer.forceContextLoss()
    }
  }

  function dispose(): void {
    clearAxisGroup()
    disposeWireframe()
    disposeClippingGuide()
    surfaceGeometry.dispose()
    surfaceMaterial.dispose()
    frameLineGeometry.dispose()
    frameLineMaterial.dispose()
    renderer.dispose()
    renderer.forceContextLoss()
  }

  return {
    beginPan,
    captureCanvas,
    dispose,
    endPan,
    pick,
    resize,
    setAxes,
    setClippingHeight,
    setFrameLine,
    setSurface,
    updatePan,
    zoom,
  }
}

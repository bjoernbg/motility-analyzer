import { beforeEach, describe, expect, it, vi } from 'vitest'
import { nextTick } from 'vue'
import { mount } from '@vue/test-utils'

import type { HeatmapMeta } from '../../lib/api'
import { mapHeatmapMmValueToTopographyHeight } from '../../lib/heatmapTopography'

const testState = vi.hoisted(() => ({
  createSceneMock: vi.fn(),
  data: null as any,
  error: null as any,
  heatmapMaxMm: null as any,
  heatmapMinMm: null as any,
  isLoading: null as any,
  meta: null as any,
  pixelToMmFactor: null as any,
  sceneController: null as any,
}))

vi.mock('../../composables/useAnalysisHeatmap', async () => {
  const { ref } = await import('vue')

  testState.data ??= ref<Float32Array | null>(null)
  testState.error ??= ref<string | null>(null)
  testState.heatmapMaxMm ??= ref(5)
  testState.heatmapMinMm ??= ref(1)
  testState.isLoading ??= ref(false)
  testState.meta ??= ref<HeatmapMeta | null>(null)
  testState.pixelToMmFactor ??= ref(10)

  return {
    useAnalysisHeatmap: () => ({
      data: testState.data,
      error: testState.error,
      heatmapMaxMm: testState.heatmapMaxMm,
      heatmapMinMm: testState.heatmapMinMm,
      isLoading: testState.isLoading,
      meta: testState.meta,
      pixelToMmFactor: testState.pixelToMmFactor,
    }),
  }
})

vi.mock('../../lib/heatmapTopographyScene', () => ({
  createHeatmapTopographyScene: testState.createSceneMock,
}))

import HeatmapTopographyViewer from '../HeatmapTopographyViewer.vue'

async function flush(): Promise<void> {
  await nextTick()
  await Promise.resolve()
}

function createMeta(): HeatmapMeta {
  return {
    dtype: 'float32',
    fps: 10,
    height: 2,
    max: 50,
    min: 10,
    width: 2,
  }
}

function createSurfaceData(): Float32Array {
  return new Float32Array([10, 20, 30, 50])
}

function mountSubject(props: Record<string, unknown> = {}) {
  return mount(HeatmapTopographyViewer, {
    props: {
      analysisId: 'analysis-1',
      currentFrame: 1,
      ...props,
    },
  })
}

describe('HeatmapTopographyViewer', () => {
  beforeEach(() => {
    testState.createSceneMock.mockReset()
    testState.sceneController = {
      beginPan: vi.fn(),
      captureCanvas: vi.fn(() => document.createElement('canvas')),
      dispose: vi.fn(),
      endPan: vi.fn(),
      pick: vi.fn(() => null),
      resize: vi.fn(),
      setAxes: vi.fn(),
      setClippingHeight: vi.fn(),
      setFrameLine: vi.fn(),
      setSurface: vi.fn(),
      updatePan: vi.fn(),
      zoom: vi.fn(),
    }
    testState.createSceneMock.mockImplementation(() => testState.sceneController)

    testState.data.value = createSurfaceData()
    testState.error.value = null
    testState.heatmapMaxMm.value = 5
    testState.heatmapMinMm.value = 1
    testState.isLoading.value = false
    testState.meta.value = createMeta()
    testState.pixelToMmFactor.value = 10
  })

  it('shows the loading state before data is ready', async () => {
    testState.isLoading.value = true
    const wrapper = mountSubject()
    await flush()

    expect(wrapper.text()).toContain('Loading heatmap data...')
  })

  it('shows the error state when heatmap loading fails', async () => {
    testState.error.value = 'Could not load topography'
    const wrapper = mountSubject()
    await flush()

    expect(wrapper.text()).toContain('Could not load topography')
  })

  it('shows the empty state when no heatmap surface can be built', async () => {
    testState.meta.value = {
      ...createMeta(),
      width: 0,
    }

    const wrapper = mountSubject()
    await flush()

    expect(wrapper.text()).toContain('No heatmap data available.')
    expect(testState.sceneController.setSurface).toHaveBeenCalledWith(null)
    expect(testState.sceneController.setAxes).toHaveBeenCalledWith(null)
  })

  it('emits export availability when a topography surface is ready', async () => {
    const wrapper = mountSubject()
    await flush()

    expect(wrapper.emitted('export-availability-change')).toEqual([[true]])
    expect(testState.sceneController.setAxes).toHaveBeenCalledWith(
      expect.objectContaining({
        xLabel: 'Time (s)',
        yLabel: 'Point',
        zLabel: 'Distance (mm)',
      }),
    )
  })

  it('clears the clipping plane when clipping is disabled', async () => {
    mountSubject({
      clippingEnabled: false,
      clipPlaneMm: 3,
    })
    await flush()

    expect(testState.sceneController.setClippingHeight).toHaveBeenLastCalledWith(null)
  })

  it('maps the clipping plane measurement to world-space height when clipping is enabled', async () => {
    mountSubject({
      clippingEnabled: true,
      clipPlaneMm: 3,
    })
    await flush()

    const appliedSurface = testState.sceneController.setSurface.mock.calls.at(-1)?.[0]
    const expectedHeight = mapHeatmapMmValueToTopographyHeight(
      3,
      testState.heatmapMinMm.value,
      testState.heatmapMaxMm.value,
      appliedSurface.metrics.heightScale,
    )

    expect(testState.sceneController.setClippingHeight).toHaveBeenLastCalledWith(expectedHeight)
  })

  it('updates the clipping plane height when the requested measurement changes', async () => {
    const wrapper = mountSubject({
      clippingEnabled: true,
      clipPlaneMm: 2,
    })
    await flush()

    const appliedSurface = testState.sceneController.setSurface.mock.calls.at(-1)?.[0]

    await wrapper.setProps({ clipPlaneMm: 4 })
    await flush()

    const expectedHeight = mapHeatmapMmValueToTopographyHeight(
      4,
      testState.heatmapMinMm.value,
      testState.heatmapMaxMm.value,
      appliedSurface.metrics.heightScale,
    )

    expect(testState.sceneController.setClippingHeight).toHaveBeenLastCalledWith(expectedHeight)
    expect(wrapper.emitted('export-availability-change')).toEqual([[true]])
  })

  it('emits the picked frame and point index when the surface is clicked', async () => {
    testState.sceneController.pick.mockReturnValue({ frame: 7, pointIndex: 1 })

    const wrapper = mountSubject()
    await flush()

    await wrapper.get('canvas').trigger('click', {
      clientX: 24,
      clientY: 36,
    })

    expect(wrapper.emitted('frame-click')).toEqual([[7, 1]])
  })
})

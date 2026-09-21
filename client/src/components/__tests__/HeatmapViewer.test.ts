import { beforeEach, describe, expect, it, vi } from 'vitest'
import { mount } from '@vue/test-utils'

import type { HeatmapMeta } from '../../lib/api'

const testState = vi.hoisted(() => ({
  storeMock: null as any,
  data: null as any,
  error: null as any,
  heatmapMaxMm: null as any,
  heatmapMinMm: null as any,
  isLoading: null as any,
  loadDataMock: vi.fn(),
  meta: null as any,
  pixelToMmFactor: null as any,
}))

vi.mock('../../stores/analysis', async () => {
  const { reactive } = await import('vue')

  testState.storeMock = reactive({
    contractionEvents: [] as Array<unknown>,
    currentVideo: null as { metadata?: { total_frames: number; frame_multiplier: number } } | null,
  })

  return {
    useAnalysisStore: () => testState.storeMock,
  }
})

vi.mock('../../composables/useAnalysisHeatmap', async () => {
  const { computed, ref } = await import('vue')

  testState.data ??= ref<Float32Array | null>(null)
  testState.error ??= ref<string | null>(null)
  testState.heatmapMaxMm ??= ref(5)
  testState.heatmapMinMm ??= ref(1)
  testState.isLoading ??= ref(true)
  testState.meta ??= ref<HeatmapMeta | null>(null)
  testState.pixelToMmFactor ??= ref(10)

  return {
    useAnalysisHeatmap: () => ({
      data: testState.data,
      error: testState.error,
      hasExportableData: computed(
        () =>
          Boolean(
            testState.meta.value &&
              testState.data.value &&
              testState.meta.value.width > 0 &&
              testState.meta.value.height > 0 &&
              !testState.error.value,
          ),
      ),
      hasRenderableData: computed(
        () =>
          Boolean(
            testState.meta.value &&
              testState.data.value &&
              testState.meta.value.width > 0 &&
              testState.meta.value.height > 0,
          ),
      ),
      heatmapMaxMm: testState.heatmapMaxMm,
      heatmapMinMm: testState.heatmapMinMm,
      isLoading: testState.isLoading,
      loadData: testState.loadDataMock,
      meta: testState.meta,
      pixelToMmFactor: testState.pixelToMmFactor,
    }),
  }
})

import HeatmapViewer from '../HeatmapViewer.vue'

async function flush(): Promise<void> {
  await Promise.resolve()
  await Promise.resolve()
}

function createMeta(): HeatmapMeta {
  return {
    dtype: 'float32',
    fps: 10,
    height: 4,
    max: 40,
    min: 10,
    width: 10,
  }
}

function mountSubject() {
  return mount(HeatmapViewer, {
    props: {
      analysisId: 'analysis-1',
    },
  })
}

describe('HeatmapViewer', () => {
  beforeEach(() => {
    testState.storeMock.contractionEvents = []
    testState.storeMock.currentVideo = null
    testState.data.value = null
    testState.error.value = null
    testState.heatmapMaxMm.value = 5
    testState.heatmapMinMm.value = 1
    testState.isLoading.value = true
    testState.loadDataMock.mockReset()
    testState.meta.value = null
    testState.pixelToMmFactor.value = 10
  })

  it('emits frame-click after the heatmap canvas appears from an async load', async () => {
    const wrapper = mountSubject()
    const container = wrapper.get('.heatmap-container').element as HTMLDivElement

    Object.defineProperty(container, 'clientWidth', {
      configurable: true,
      value: 160,
    })
    Object.defineProperty(container, 'clientHeight', {
      configurable: true,
      value: 130,
    })

    expect(wrapper.find('.heatmap-canvas').exists()).toBe(false)

    testState.isLoading.value = false
    testState.meta.value = createMeta()
    testState.data.value = new Float32Array(createMeta().width * createMeta().height).fill(10)
    await flush()

    const canvas = wrapper.get('.heatmap-canvas')
    vi.spyOn(canvas.element, 'getBoundingClientRect').mockReturnValue({
      bottom: 100,
      height: 100,
      left: 0,
      right: 100,
      toJSON: () => ({}),
      top: 0,
      width: 100,
      x: 0,
      y: 0,
    })

    await canvas.trigger('click', {
      clientX: 52,
      clientY: 55,
    })

    expect(wrapper.emitted('frame-click')).toEqual([[5, 2]])
  })
})

import { beforeEach, describe, expect, it, vi } from 'vitest'
import { defineComponent, h, nextTick, onMounted } from 'vue'
import { mount } from '@vue/test-utils'

const testState = vi.hoisted(() => ({
  storeMock: null as any,
  getVideoDisplaySettingsMock: vi.fn(async () => ({
    pixel_to_mm_factor: 11,
    heatmap_min_mm: 3,
    heatmap_max_mm: 30,
  })),
  videoDownloadMock: vi.fn(async () => {}),
  heatmapDownloadMock: vi.fn(async () => {}),
  topographyDownloadMock: vi.fn(async () => {}),
  heatmapExportAvailable: true,
  topographyExportAvailable: true,
}))

vi.mock('../../stores/analysis', async () => {
  const { reactive } = await import('vue')

  testState.storeMock = reactive({
    activeAnalysis: {
      id: 'analysis-1',
    } as { id: string } | null,
    activeVideo: {
      id: 'video-1',
    } as { id: string } | null,
    currentFrame: 12 as number | null,
    liveFrameData: new Map([[12, {}]]),
    contractionEvents: [] as Array<unknown>,
    seekToFrame: vi.fn(),
  })

  return {
    useAnalysisStore: () => testState.storeMock,
  }
})

vi.mock('../../lib/api', () => ({
  getVideoDisplaySettings: testState.getVideoDisplaySettingsMock,
}))

const ButtonStub = defineComponent({
  name: 'Button',
  props: {
    disabled: Boolean,
    title: {
      type: String,
      default: '',
    },
  },
  emits: ['click'],
  setup(props, { emit, slots }) {
    return () =>
      h(
        'button',
        {
          disabled: props.disabled,
          title: props.title,
          onClick: (event: MouseEvent) => emit('click', event),
        },
        slots.default?.(),
      )
  },
})

const ButtonGroupStub = defineComponent({
  name: 'ButtonGroup',
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

const SliderStub = defineComponent({
  name: 'Slider',
  props: {
    disabled: Boolean,
    max: {
      type: Number,
      default: 0,
    },
    min: {
      type: Number,
      default: 0,
    },
    modelValue: {
      type: Array,
      default: () => [],
    },
    orientation: {
      type: String,
      default: 'horizontal',
    },
    step: {
      type: Number,
      default: 1,
    },
  },
  emits: ['update:modelValue'],
  setup(props) {
    return () =>
      h('div', {
        class: 'slider-stub',
        'data-disabled': props.disabled ? 'true' : 'false',
        'data-orientation': props.orientation,
      })
  },
})

const IconStub = defineComponent({
  name: 'Icon',
  setup() {
    return () => h('span')
  },
})

const PopoverStub = defineComponent({
  name: 'Popover',
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

const PopoverTriggerStub = defineComponent({
  name: 'PopoverTrigger',
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

const PopoverContentStub = defineComponent({
  name: 'PopoverContent',
  setup(_, { slots }) {
    return () => h('div', slots.default?.())
  },
})

const DisplaySettingsControlsStub = defineComponent({
  name: 'DisplaySettingsControls',
  setup() {
    return () => h('div')
  },
})

const VideoPlayerStub = defineComponent({
  name: 'VideoPlayer',
  emits: ['update:showCanvasOverlay'],
  setup(_, { expose }) {
    expose({
      downloadCurrentFrame: testState.videoDownloadMock,
    })

    return () => h('div', { class: 'video-player-stub' })
  },
})

const HeatmapViewerStub = defineComponent({
  name: 'HeatmapViewer',
  emits: ['frame-click', 'export-availability-change'],
  setup(_, { emit, expose }) {
    onMounted(() => {
      emit('export-availability-change', testState.heatmapExportAvailable)
    })

    expose({
      downloadCurrentView: testState.heatmapDownloadMock,
    })

    return () => h('div', { class: 'heatmap-viewer-stub' })
  },
})

const HeatmapTopographyViewerStub = defineComponent({
  name: 'HeatmapTopographyViewer',
  props: {
    clipPlaneMm: {
      type: Number,
      default: null,
    },
    clippingEnabled: Boolean,
  },
  emits: ['frame-click', 'export-availability-change'],
  setup(props, { emit, expose }) {
    onMounted(() => {
      emit('export-availability-change', testState.topographyExportAvailable)
    })

    expose({
      downloadCurrentView: testState.topographyDownloadMock,
    })

    return () =>
      h('div', {
        class: 'topography-viewer-stub',
        'data-clip-plane-mm': props.clipPlaneMm ?? '',
        'data-clipping-enabled': props.clippingEnabled ? 'true' : 'false',
      })
  },
})

import MediaViewer from '../MediaViewer.vue'

async function flush(): Promise<void> {
  await nextTick()
  await Promise.resolve()
}

function mountSubject() {
  return mount(MediaViewer, {
    global: {
      stubs: {
        Button: ButtonStub,
        ButtonGroup: ButtonGroupStub,
        Icon: IconStub,
        Popover: PopoverStub,
        PopoverTrigger: PopoverTriggerStub,
        PopoverContent: PopoverContentStub,
        DisplaySettingsControls: DisplaySettingsControlsStub,
        Slider: SliderStub,
        VideoPlayer: VideoPlayerStub,
        HeatmapViewer: HeatmapViewerStub,
        HeatmapTopographyViewer: HeatmapTopographyViewerStub,
      },
    },
  })
}

async function switchToHeatmap(wrapper: ReturnType<typeof mountSubject>): Promise<void> {
  const modeButtons = wrapper.findAll('.view-toggle button')
  await modeButtons[1]?.trigger('click')
  await flush()
}

async function switchToTopography(wrapper: ReturnType<typeof mountSubject>): Promise<void> {
  const modeButtons = wrapper.findAll('.view-toggle button')
  await modeButtons[2]?.trigger('click')
  await flush()
}

describe('MediaViewer toolbar exports', () => {
  beforeEach(() => {
    testState.storeMock.activeAnalysis = { id: 'analysis-1' }
    testState.storeMock.activeVideo = { id: 'video-1' }
    testState.storeMock.currentFrame = 12
    testState.storeMock.liveFrameData = new Map([[12, {}]])
    testState.storeMock.contractionEvents = []
    testState.storeMock.seekToFrame = vi.fn()
    testState.heatmapExportAvailable = true
    testState.topographyExportAvailable = true
    testState.videoDownloadMock.mockClear()
    testState.heatmapDownloadMock.mockClear()
    testState.topographyDownloadMock.mockClear()
    testState.getVideoDisplaySettingsMock.mockClear()
    testState.getVideoDisplaySettingsMock.mockImplementation(async (videoId: string) => ({
      pixel_to_mm_factor: 11,
      heatmap_min_mm: videoId === 'video-2' ? 4 : 3,
      heatmap_max_mm: videoId === 'video-2' ? 10 : 30,
    }))
  })

  it('dispatches the download action to the video player in video mode', async () => {
    const wrapper = mountSubject()
    await flush()

    await wrapper.get('button[title="Download current video frame"]').trigger('click')

    expect(testState.videoDownloadMock).toHaveBeenCalledTimes(1)
    expect(testState.heatmapDownloadMock).not.toHaveBeenCalled()
  })

  it('dispatches the download action to the heatmap viewer in heatmap mode', async () => {
    const wrapper = mountSubject()
    await flush()

    await switchToHeatmap(wrapper)

    await wrapper.get('button[title="Download current heatmap view"]').trigger('click')

    expect(testState.heatmapDownloadMock).toHaveBeenCalledTimes(1)
    expect(testState.videoDownloadMock).not.toHaveBeenCalled()
  })

  it('disables the download button when the active heatmap view is not exportable', async () => {
    testState.heatmapExportAvailable = false

    const wrapper = mountSubject()
    await flush()

    await switchToHeatmap(wrapper)

    expect(
      wrapper.get('button[title="Download current heatmap view"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('dispatches the download action to the topography viewer in topography mode', async () => {
    const wrapper = mountSubject()
    await flush()

    await switchToTopography(wrapper)

    await wrapper.get('button[title="Download current topography view"]').trigger('click')

    expect(testState.topographyDownloadMock).toHaveBeenCalledTimes(1)
    expect(testState.videoDownloadMock).not.toHaveBeenCalled()
    expect(testState.heatmapDownloadMock).not.toHaveBeenCalled()
  })

  it('disables the download button when the active topography view is not exportable', async () => {
    testState.topographyExportAvailable = false

    const wrapper = mountSubject()
    await flush()

    await switchToTopography(wrapper)

    expect(
      wrapper.get('button[title="Download current topography view"]').attributes('disabled'),
    ).toBeDefined()
  })

  it('keeps the mini video preview visible in topography mode', async () => {
    const wrapper = mountSubject()
    await flush()

    await switchToTopography(wrapper)

    expect(wrapper.find('.mini-video-wrapper').exists()).toBe(true)
    expect(wrapper.find('.topography-viewer-stub').exists()).toBe(true)
  })

  it('only shows the clipping toggle in topography mode and hides the slider until clipping is active', async () => {
    const wrapper = mountSubject()
    await flush()

    expect(wrapper.find('button[title="Toggle horizontal clipping plane"]').exists()).toBe(false)
    expect(wrapper.findComponent(SliderStub).exists()).toBe(false)

    await switchToHeatmap(wrapper)

    expect(wrapper.find('button[title="Toggle horizontal clipping plane"]').exists()).toBe(false)
    expect(wrapper.findComponent(SliderStub).exists()).toBe(false)

    await switchToTopography(wrapper)

    expect(wrapper.find('button[title="Toggle horizontal clipping plane"]').exists()).toBe(true)
    expect(wrapper.findComponent(SliderStub).exists()).toBe(false)

    await wrapper.get('button[title="Toggle horizontal clipping plane"]').trigger('click')
    await flush()

    expect(wrapper.findComponent(SliderStub).exists()).toBe(true)
  })

  it('keeps clipping off by default and initializes the first enabled value to the midpoint', async () => {
    const wrapper = mountSubject()
    await flush()
    await switchToTopography(wrapper)

    const topographyViewer = wrapper.findComponent(HeatmapTopographyViewerStub)

    expect(topographyViewer.props('clippingEnabled')).toBe(false)
    expect(topographyViewer.props('clipPlaneMm')).toBe(null)
    expect(wrapper.findComponent(SliderStub).exists()).toBe(false)

    await wrapper.get('button[title="Toggle horizontal clipping plane"]').trigger('click')
    await flush()

    const slider = wrapper.findComponent(SliderStub)

    expect(topographyViewer.props('clippingEnabled')).toBe(true)
    expect(Number(topographyViewer.props('clipPlaneMm'))).toBeCloseTo(16.5)
    expect(slider.exists()).toBe(true)
  })

  it('propagates slider changes to the topography clipping plane', async () => {
    const wrapper = mountSubject()
    await flush()
    await switchToTopography(wrapper)

    await wrapper.get('button[title="Toggle horizontal clipping plane"]').trigger('click')
    await flush()

    const slider = wrapper.findComponent(SliderStub)
    await slider.vm.$emit('update:modelValue', [9.4])
    await flush()

    expect(
      Number(wrapper.findComponent(HeatmapTopographyViewerStub).props('clipPlaneMm')),
    ).toBeCloseTo(9.4)
  })

  it('clamps the stored clipping plane value when the display range changes', async () => {
    const wrapper = mountSubject()
    await flush()
    await switchToTopography(wrapper)

    await wrapper.get('button[title="Toggle horizontal clipping plane"]').trigger('click')
    await flush()

    const slider = wrapper.findComponent(SliderStub)
    await slider.vm.$emit('update:modelValue', [28])
    await flush()

    testState.storeMock.activeVideo = { id: 'video-2' }
    await flush()
    await flush()

    expect(
      Number(wrapper.findComponent(HeatmapTopographyViewerStub).props('clipPlaneMm')),
    ).toBeCloseTo(10)
    expect(wrapper.findComponent(SliderStub).props('min')).toBe(4)
    expect(wrapper.findComponent(SliderStub).props('max')).toBe(10)
  })
})

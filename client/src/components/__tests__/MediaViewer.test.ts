import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, onMounted } from 'vue';
import { mount } from '@vue/test-utils';

const testState = vi.hoisted(() => ({
  storeMock: null as any,
  getVideoDisplaySettingsMock: vi.fn(async () => ({
    pixel_to_mm_factor: 11,
    heatmap_min_mm: 3,
    heatmap_max_mm: 30,
  })),
  videoDownloadMock: vi.fn(async () => {}),
  heatmapDownloadMock: vi.fn(async () => {}),
  heatmapExportAvailable: true,
}));

vi.mock('../../stores/analysis', async () => {
  const { reactive } = await import('vue');

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
  });

  return {
    useAnalysisStore: () => testState.storeMock,
  };
});

vi.mock('../../lib/api', () => ({
  getVideoDisplaySettings: testState.getVideoDisplaySettingsMock,
}));

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
      );
  },
});

const ButtonGroupStub = defineComponent({
  name: 'ButtonGroup',
  setup(_, { slots }) {
    return () => h('div', slots.default?.());
  },
});

const IconStub = defineComponent({
  name: 'Icon',
  setup() {
    return () => h('span');
  },
});

const PopoverStub = defineComponent({
  name: 'Popover',
  setup(_, { slots }) {
    return () => h('div', slots.default?.());
  },
});

const PopoverTriggerStub = defineComponent({
  name: 'PopoverTrigger',
  setup(_, { slots }) {
    return () => h('div', slots.default?.());
  },
});

const PopoverContentStub = defineComponent({
  name: 'PopoverContent',
  setup(_, { slots }) {
    return () => h('div', slots.default?.());
  },
});

const DisplaySettingsControlsStub = defineComponent({
  name: 'DisplaySettingsControls',
  setup() {
    return () => h('div');
  },
});

const VideoPlayerStub = defineComponent({
  name: 'VideoPlayer',
  emits: ['update:showCanvasOverlay'],
  setup(_, { expose }) {
    expose({
      downloadCurrentFrame: testState.videoDownloadMock,
    });

    return () => h('div', { class: 'video-player-stub' });
  },
});

const HeatmapViewerStub = defineComponent({
  name: 'HeatmapViewer',
  emits: ['frame-click', 'export-availability-change'],
  setup(_, { emit, expose }) {
    onMounted(() => {
      emit('export-availability-change', testState.heatmapExportAvailable);
    });

    expose({
      downloadCurrentView: testState.heatmapDownloadMock,
    });

    return () => h('div', { class: 'heatmap-viewer-stub' });
  },
});

import MediaViewer from '../MediaViewer.vue';

async function flush(): Promise<void> {
  await nextTick();
  await Promise.resolve();
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
        VideoPlayer: VideoPlayerStub,
        HeatmapViewer: HeatmapViewerStub,
      },
    },
  });
}

describe('MediaViewer toolbar exports', () => {
  beforeEach(() => {
    testState.storeMock.activeAnalysis = { id: 'analysis-1' };
    testState.storeMock.activeVideo = { id: 'video-1' };
    testState.storeMock.currentFrame = 12;
    testState.storeMock.liveFrameData = new Map([[12, {}]]);
    testState.storeMock.contractionEvents = [];
    testState.storeMock.seekToFrame = vi.fn();
    testState.heatmapExportAvailable = true;
    testState.videoDownloadMock.mockClear();
    testState.heatmapDownloadMock.mockClear();
    testState.getVideoDisplaySettingsMock.mockClear();
  });

  it('dispatches the download action to the video player in video mode', async () => {
    const wrapper = mountSubject();
    await flush();

    await wrapper.get('button[title="Download current video frame"]').trigger('click');

    expect(testState.videoDownloadMock).toHaveBeenCalledTimes(1);
    expect(testState.heatmapDownloadMock).not.toHaveBeenCalled();
  });

  it('dispatches the download action to the heatmap viewer in heatmap mode', async () => {
    const wrapper = mountSubject();
    await flush();

    const modeButtons = wrapper.findAll('.view-toggle button');
    await modeButtons[1]?.trigger('click');
    await flush();

    await wrapper.get('button[title="Download current heatmap view"]').trigger('click');

    expect(testState.heatmapDownloadMock).toHaveBeenCalledTimes(1);
    expect(testState.videoDownloadMock).not.toHaveBeenCalled();
  });

  it('disables the download button when the active heatmap view is not exportable', async () => {
    testState.heatmapExportAvailable = false;

    const wrapper = mountSubject();
    await flush();

    const modeButtons = wrapper.findAll('.view-toggle button');
    await modeButtons[1]?.trigger('click');
    await flush();

    expect(wrapper.get('button[title="Download current heatmap view"]').attributes('disabled')).toBeDefined();
  });
});

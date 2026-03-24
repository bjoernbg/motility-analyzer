import { beforeEach, describe, expect, it, vi } from 'vitest';
import { defineComponent, h, nextTick, onMounted } from 'vue';
import { mount } from '@vue/test-utils';

function createExportCanvas(): HTMLCanvasElement {
  const canvas = document.createElement('canvas');
  canvas.width = 16;
  canvas.height = 9;
  return canvas;
}

const testState = vi.hoisted(() => ({
  storeMock: null as any,
  getHeatmapMetaMock: vi.fn(async () => ({
    width: 10,
    height: 5,
    dtype: 'float32',
    min: 10,
    max: 50,
    fps: 30,
    display_settings: {
      pixel_to_mm_factor: 11,
      heatmap_min_mm: 1,
      heatmap_max_mm: 5,
    },
  })),
  getAnalysisFrameMock: vi.fn(async () => ({
    f: 0,
    pt: [],
    pb: [],
    pc: [],
    colored_regions: [],
    mpp: [
      [0, 0, 1, 1, 2, 2, 10],
      [0, 0, 2, 2, 3, 3, 12],
    ],
  })),
  getVideoDisplaySettingsMock: vi.fn(async () => ({
    pixel_to_mm_factor: 11,
    heatmap_min_mm: 1,
    heatmap_max_mm: 5,
  })),
  threeDCaptureMock: vi.fn(async () => createExportCanvas()),
  leftHeatmapCaptureMock: vi.fn(async () => createExportCanvas()),
  rightHeatmapCaptureMock: vi.fn(async () => createExportCanvas()),
  downloadZipMock: vi.fn(async () => {}),
  renderSidebarFrameToCanvasMock: vi.fn(() => createExportCanvas()),
  threeDExportAvailable: true,
}));

vi.mock('../../stores/analysis', async () => {
  const { reactive } = await import('vue');

  testState.storeMock = reactive({
    leftVideo: {
      id: 'left-video',
      display_name: 'Left video',
      filename: 'left.mp4',
      metadata: {
        fps: 30,
        total_frames: 200,
        width: 1920,
        height: 1080,
        display_aspect_ratio: 16 / 9,
        duration: 10,
        frame_multiplier: 1,
      },
    },
    rightVideo: {
      id: 'right-video',
      display_name: 'Right video',
      filename: 'right.mp4',
      metadata: {
        fps: 30,
        total_frames: 200,
        width: 1920,
        height: 1080,
        display_aspect_ratio: 16 / 9,
        duration: 10,
        frame_multiplier: 1,
      },
    },
    leftAnalysis: {
      id: 'left-analysis',
      display_name: null,
      created_at: '2026-03-16T12:00:00',
      parameters: {
        distribution_method: 'center_line_projection',
        num_tracking_points: 30,
        horizontal_window_x_left: 10,
        horizontal_window_x_right: 100,
      },
    },
    rightAnalysis: {
      id: 'right-analysis',
      display_name: null,
      created_at: '2026-03-16T12:00:00',
      parameters: {
        distribution_method: 'center_line_projection',
        num_tracking_points: 30,
        horizontal_window_x_left: 20,
        horizontal_window_x_right: 120,
      },
    },
    currentMultiViewSession: {
      id: 'session-1',
      name: 'Combined Analysis',
    },
    currentMultiViewDirections: {
      leftDirection: 'front',
      rightDirection: 'bottom',
    },
    latestAlignmentSuggestion: null,
    syncedTimeSec: 0,
    rightTimeShiftSec: 0,
    minSyncedTimeSec: 0,
    maxSyncedTimeSec: 5,
    isComputingAlignment: false,
    computeMultiViewAlignment: vi.fn(async () => {}),
    setSyncedTime: vi.fn(),
  });

  return {
    useAnalysisStore: () => testState.storeMock,
  };
});

vi.mock('../../lib/api', () => ({
  getHeatmapMeta: testState.getHeatmapMetaMock,
  getAnalysisFrame: testState.getAnalysisFrameMock,
  getFrameImageUrl: vi.fn((videoId: string, frame: number) => `/frames/${videoId}/${frame}.jpg`),
  getVideoDisplaySettings: testState.getVideoDisplaySettingsMock,
}));

vi.mock('../../lib/zip', () => ({
  downloadZip: testState.downloadZipMock,
}));

vi.mock('../../lib/multiViewFrameRendering', () => ({
  renderSidebarFrameToCanvas: testState.renderSidebarFrameToCanvasMock,
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

const SliderStub = defineComponent({
  name: 'Slider',
  setup() {
    return () => h('div');
  },
});

const HeatmapViewerStub = defineComponent({
  name: 'HeatmapViewer',
  props: {
    analysisId: {
      type: String,
      default: '',
    },
  },
  setup(props, { expose }) {
    expose({
      captureExportCanvas: () => {
        if (props.analysisId === 'left-analysis') {
          return testState.leftHeatmapCaptureMock();
        }
        return testState.rightHeatmapCaptureMock();
      },
    });

    return () => h('div', { class: 'heatmap-viewer-stub' });
  },
});

const MultiViewDiffPanelStub = defineComponent({
  name: 'MultiViewDiffPanel',
  setup() {
    return () => h('div');
  },
});

const IntestineViewer3DStub = defineComponent({
  name: 'IntestineViewer3D',
  emits: ['export-availability-change'],
  setup(_, { emit, expose }) {
    onMounted(() => {
      emit('export-availability-change', testState.threeDExportAvailable);
    });

    expose({
      captureCurrentViewFullHdCanvas: testState.threeDCaptureMock,
    });

    return () => h('div', { class: 'viewer-3d-stub' });
  },
});

import MultiViewWorkspace from '../MultiViewWorkspace.vue';

async function flush(): Promise<void> {
  await nextTick();
  await Promise.resolve();
}

function mountSubject() {
  return mount(MultiViewWorkspace, {
    global: {
      stubs: {
        HeatmapViewer: HeatmapViewerStub,
        MultiViewDiffPanel: MultiViewDiffPanelStub,
        IntestineViewer3D: IntestineViewer3DStub,
        Slider: SliderStub,
        Button: ButtonStub,
        ButtonGroup: ButtonGroupStub,
        Icon: IconStub,
      },
    },
  });
}

describe('MultiViewWorkspace toolbar exports', () => {
  beforeEach(() => {
    testState.storeMock.leftVideo = {
      ...testState.storeMock.leftVideo,
      id: 'left-video',
    };
    testState.storeMock.rightVideo = {
      ...testState.storeMock.rightVideo,
      id: 'right-video',
    };
    testState.storeMock.leftAnalysis = {
      ...testState.storeMock.leftAnalysis,
      id: 'left-analysis',
    };
    testState.storeMock.rightAnalysis = {
      ...testState.storeMock.rightAnalysis,
      id: 'right-analysis',
    };
    testState.storeMock.currentMultiViewSession = {
      id: 'session-1',
      name: 'Combined Analysis',
    };
    testState.storeMock.currentMultiViewDirections = {
      leftDirection: 'front',
      rightDirection: 'bottom',
    };
    testState.storeMock.syncedTimeSec = 0;
    testState.storeMock.rightTimeShiftSec = 0;
    testState.storeMock.minSyncedTimeSec = 0;
    testState.storeMock.maxSyncedTimeSec = 5;
    testState.storeMock.isComputingAlignment = false;
    testState.storeMock.computeMultiViewAlignment = vi.fn(async () => {});
    testState.storeMock.setSyncedTime = vi.fn();
    testState.threeDCaptureMock.mockClear();
    testState.leftHeatmapCaptureMock.mockClear();
    testState.rightHeatmapCaptureMock.mockClear();
    testState.downloadZipMock.mockClear();
    testState.renderSidebarFrameToCanvasMock.mockClear();
    testState.getHeatmapMetaMock.mockClear();
    testState.getAnalysisFrameMock.mockClear();
    testState.getVideoDisplaySettingsMock.mockClear();
    testState.threeDExportAvailable = true;
  });

  it('shows the bundle button only in 3D mode and downloads one zip containing all captures', async () => {
    const wrapper = mountSubject();
    await flush();

    expect(wrapper.find('button[title="Download current 3D workspace bundle"]').exists()).toBe(false);

    const modeButtons = wrapper.findAll('.view-mode-tabs button');
    await modeButtons[2]?.trigger('click');
    await flush();

    const images = wrapper.findAll('img');
    for (const image of images) {
      Object.defineProperty(image.element, 'complete', { value: true, configurable: true });
      Object.defineProperty(image.element, 'naturalWidth', { value: 1920, configurable: true });
    }

    const downloadButton = wrapper.get('button[title="Download current 3D workspace bundle"]');
    expect(downloadButton.exists()).toBe(true);

    await downloadButton.trigger('click');
    await flush();

    expect(testState.threeDCaptureMock).toHaveBeenCalledTimes(1);
    expect(testState.leftHeatmapCaptureMock).toHaveBeenCalledTimes(1);
    expect(testState.rightHeatmapCaptureMock).toHaveBeenCalledTimes(1);
    expect(testState.renderSidebarFrameToCanvasMock).toHaveBeenCalledTimes(2);
    expect(testState.downloadZipMock).toHaveBeenCalledTimes(1);

    const leftFrameRenderArgs = testState.renderSidebarFrameToCanvasMock.mock.calls[0]?.[0];
    const rightFrameRenderArgs = testState.renderSidebarFrameToCanvasMock.mock.calls[1]?.[0];
    expect(leftFrameRenderArgs?.clipWidth).toBe(1920);
    expect(leftFrameRenderArgs?.clipHeight).toBe(1080);
    expect(leftFrameRenderArgs?.windowLeft).toBeUndefined();
    expect(leftFrameRenderArgs?.windowRight).toBeUndefined();
    expect(rightFrameRenderArgs?.clipWidth).toBe(1920);
    expect(rightFrameRenderArgs?.clipHeight).toBe(1080);
    expect(rightFrameRenderArgs?.windowLeft).toBeUndefined();
    expect(rightFrameRenderArgs?.windowRight).toBeUndefined();

    const [entries, filename] = testState.downloadZipMock.mock.calls[0] ?? [];
    expect(filename).toBe('multiview_views_session-1_0_0.zip');
    expect(entries).toEqual([
      expect.objectContaining({ filename: 'left_heatmap.png' }),
      expect.objectContaining({ filename: 'right_heatmap.png' }),
      expect.objectContaining({ filename: 'left_frame.png' }),
      expect.objectContaining({ filename: 'right_frame.png' }),
      expect.objectContaining({ filename: '3d_view.png' }),
    ]);
  });

  it('disables the bundle button when the 3D export is unavailable', async () => {
    testState.threeDExportAvailable = false;

    const wrapper = mountSubject();
    await flush();

    const modeButtons = wrapper.findAll('.view-mode-tabs button');
    await modeButtons[2]?.trigger('click');
    await flush();

    expect(wrapper.get('button[title="Download current 3D workspace bundle"]').attributes('disabled')).toBeDefined();
  });
});

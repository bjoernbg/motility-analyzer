import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { nextTick } from 'vue';
import { shallowMount } from '@vue/test-utils';

type VideoMetadata = {
  fps: number;
  width: number;
  height: number;
  display_aspect_ratio: number;
};

type VideoEntity = {
  id: string;
  metadata: VideoMetadata;
};

const testState = vi.hoisted(() => ({
  storeMock: null as any,
  downloadUrlMock: vi.fn(),
  getFrameImageUrlMock: vi.fn(() => '/frame.jpg'),
}));

vi.mock('../../stores/analysis', async () => {
  const { reactive } = await import('vue');

  testState.storeMock = reactive({
    currentVideo: {
      id: 'video-a',
      metadata: {
        fps: 30,
        width: 1920,
        height: 1080,
        display_aspect_ratio: 16 / 9,
      },
    } as VideoEntity | null,
    currentFrame: null as number | null,
    currentParameters: null,
    isProcessing: true,
    isAnalysisSwitching: false,
    liveFrameData: new Map<number, unknown>(),
    analyzeCurrentFrame: vi.fn(async () => {}),
    saveCurrentSettings: vi.fn(async () => {}),
  });

  return {
    useAnalysisStore: () => testState.storeMock,
  };
});

vi.mock('../../lib/api', () => ({
  detectHorizontalWindow: vi.fn(async () => ({ x_left: -1, x_right: -1 })),
  getFrameImageUrl: testState.getFrameImageUrlMock,
}));

vi.mock('../../lib/download', () => ({
  downloadUrl: testState.downloadUrlMock,
}));

import VideoPlayer from '../VideoPlayer.vue';

const storeMock = testState.storeMock as {
  currentVideo: VideoEntity | null;
  currentFrame: number | null;
  currentParameters: null;
  isProcessing: boolean;
  isAnalysisSwitching: boolean;
  liveFrameData: Map<number, unknown>;
  analyzeCurrentFrame: ReturnType<typeof vi.fn>;
  saveCurrentSettings: ReturnType<typeof vi.fn>;
};

async function flush(): Promise<void> {
  await nextTick();
  await Promise.resolve();
}

describe('VideoPlayer RAF scheduling', () => {
  let rafIdSeed = 0;
  const rafCallbacks: Array<FrameRequestCallback> = [];
  const requestAnimationFrameMock = vi.fn((cb: FrameRequestCallback): number => {
    rafCallbacks.push(cb);
    rafIdSeed += 1;
    return rafIdSeed;
  });
  const cancelAnimationFrameMock = vi.fn();

  beforeEach(() => {
    rafIdSeed = 0;
    rafCallbacks.length = 0;

    storeMock.currentVideo = {
      id: 'video-a',
      metadata: {
        fps: 30,
        width: 1920,
        height: 1080,
        display_aspect_ratio: 16 / 9,
      },
    };
    storeMock.currentFrame = null;
    storeMock.currentParameters = null;
    storeMock.isProcessing = true;
    storeMock.isAnalysisSwitching = false;
    storeMock.liveFrameData = new Map();

    storeMock.analyzeCurrentFrame = vi.fn(async () => {});
    storeMock.saveCurrentSettings = vi.fn(async () => {});

    requestAnimationFrameMock.mockClear();
    cancelAnimationFrameMock.mockClear();
    testState.downloadUrlMock.mockClear();

    vi.stubGlobal('requestAnimationFrame', requestAnimationFrameMock);
    vi.stubGlobal('cancelAnimationFrame', cancelAnimationFrameMock);
  });

  afterEach(() => {
    vi.unstubAllGlobals();
  });

  function mountSubject() {
    return shallowMount(VideoPlayer, {
      props: {
        showCanvasOverlay: true,
      },
      global: {
        stubs: {
          Slider: true,
          Button: true,
          ButtonGroup: true,
          Icon: true,
        },
      },
    });
  }

  it('does not recursively schedule RAF draws when inputs are static', async () => {
    const wrapper = mountSubject();
    await flush();

    const initialCallCount = requestAnimationFrameMock.mock.calls.length;
    expect(initialCallCount).toBeGreaterThan(0);

    const pendingCallbacks = [...rafCallbacks];
    for (const callback of pendingCallbacks) {
      callback(16);
    }
    await flush();

    expect(requestAnimationFrameMock).toHaveBeenCalledTimes(initialCallCount);

    wrapper.unmount();
  });

  it('cancels any pending RAF request on unmount', async () => {
    const wrapper = mountSubject();
    await flush();

    const initialCallCount = requestAnimationFrameMock.mock.calls.length;
    expect(initialCallCount).toBeGreaterThan(0);
    wrapper.unmount();

    expect(cancelAnimationFrameMock).toHaveBeenCalled();
    expect(cancelAnimationFrameMock).toHaveBeenCalledWith(initialCallCount);
  });

  it('cancels pending RAF and reschedules when the selected video changes', async () => {
    const wrapper = mountSubject();
    await flush();

    const initialCallCount = requestAnimationFrameMock.mock.calls.length;
    expect(initialCallCount).toBeGreaterThan(0);

    storeMock.currentVideo = {
      id: 'video-b',
      metadata: {
        fps: 24,
        width: 1280,
        height: 720,
        display_aspect_ratio: 16 / 9,
      },
    };

    await flush();

    expect(cancelAnimationFrameMock).toHaveBeenCalledWith(initialCallCount);
    expect(requestAnimationFrameMock.mock.calls.length).toBeGreaterThan(initialCallCount);

    wrapper.unmount();
  });

  it('downloads the current frame using the source image URL', async () => {
    storeMock.currentFrame = 7;

    const wrapper = mountSubject();
    await flush();

    await (wrapper.vm as unknown as { downloadCurrentFrame: () => Promise<void> }).downloadCurrentFrame();

    expect(testState.downloadUrlMock).toHaveBeenCalledWith('/frame.jpg', 'video_video-a_frame_7.jpg');

    wrapper.unmount();
  });
});

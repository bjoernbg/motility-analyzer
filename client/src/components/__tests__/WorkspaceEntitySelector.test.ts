import { mount } from '@vue/test-utils';
import { beforeEach, describe, expect, it, vi } from 'vitest';
import { reactive } from 'vue';

type WorkspaceEntityType = 'video' | 'combined' | null;

const storeMock = reactive<{
  videos: Array<{
    id: string;
    filename: string;
    display_name?: string | null;
    upload_date: string;
  }>;
  multiViewSessions: Array<{
    id: string;
    name: string;
    created_at: string;
    metadata?: Record<string, unknown>;
  }>;
  activeEntityType: WorkspaceEntityType;
  activeEntityId: string | null;
  currentVideo: {
    id: string;
    filename: string;
    display_name?: string | null;
    metadata?: Record<string, unknown>;
  } | null;
  isLoadingMetadata: boolean;
  error: string | null;
  handleVideoUpload: ReturnType<typeof vi.fn>;
  selectVideoEntity: ReturnType<typeof vi.fn>;
  selectCombinedEntity: ReturnType<typeof vi.fn>;
  renameVideo: ReturnType<typeof vi.fn>;
  renameMultiViewSession: ReturnType<typeof vi.fn>;
  reencodeCurrentVideo: ReturnType<typeof vi.fn>;
  deleteVideoById: ReturnType<typeof vi.fn>;
  clearAllData: ReturnType<typeof vi.fn>;
  deleteMultiViewSessionById: ReturnType<typeof vi.fn>;
}>({
  videos: [],
  multiViewSessions: [],
  activeEntityType: null,
  activeEntityId: null,
  currentVideo: null,
  isLoadingMetadata: false,
  error: null,
  handleVideoUpload: vi.fn(async () => {}),
  selectVideoEntity: vi.fn(async () => {}),
  selectCombinedEntity: vi.fn(async () => {}),
  renameVideo: vi.fn(async () => {}),
  renameMultiViewSession: vi.fn(async () => {}),
  reencodeCurrentVideo: vi.fn(async () => ({ statistics: {} })),
  deleteVideoById: vi.fn(async () => {}),
  clearAllData: vi.fn(async () => {}),
  deleteMultiViewSessionById: vi.fn(async () => {}),
});

vi.mock('../../stores/analysis', () => ({
  useAnalysisStore: () => storeMock,
}));

import WorkspaceEntitySelector from '../WorkspaceEntitySelector.vue';

function createVideo(id: string, name: string) {
  return {
    id,
    filename: `${name}.mp4`,
    display_name: name,
    upload_date: '2026-03-20T10:00:00',
  };
}

function createSession(id: string, name: string) {
  return {
    id,
    name,
    created_at: '2026-03-20T11:00:00',
    metadata: {},
  };
}

async function flushPromises() {
  await Promise.resolve();
}

function mountSelector() {
  return mount(WorkspaceEntitySelector, {
    global: {
      stubs: {
        Popover: {
          template: '<div><slot /></div>',
        },
        PopoverTrigger: {
          template: '<div><slot /></div>',
        },
        PopoverContent: {
          template: '<div><slot /></div>',
        },
        Icon: {
          template: '<span class="icon-stub" />',
        },
      },
    },
  });
}

describe('WorkspaceEntitySelector', () => {
  beforeEach(() => {
    storeMock.videos = [createVideo('video-1', 'Project A')];
    storeMock.multiViewSessions = [createSession('session-1', 'Combined A')];
    storeMock.activeEntityType = null;
    storeMock.activeEntityId = null;
    storeMock.currentVideo = null;
    storeMock.isLoadingMetadata = false;
    storeMock.error = null;
    storeMock.handleVideoUpload = vi.fn(async () => {
      storeMock.activeEntityType = 'video';
      storeMock.activeEntityId = 'uploaded-video';
      storeMock.currentVideo = {
        id: 'uploaded-video',
        filename: 'uploaded-video.mp4',
        display_name: 'Uploaded Video',
        metadata: {},
      };
    });
    storeMock.selectVideoEntity = vi.fn(async (videoId: string) => {
      storeMock.activeEntityType = 'video';
      storeMock.activeEntityId = videoId;
      storeMock.currentVideo = {
        id: videoId,
        filename: `${videoId}.mp4`,
        display_name: `Selected ${videoId}`,
        metadata: {},
      };
    });
    storeMock.selectCombinedEntity = vi.fn(async (sessionId: string) => {
      storeMock.activeEntityType = 'combined';
      storeMock.activeEntityId = sessionId;
    });
    storeMock.renameVideo = vi.fn(async () => {});
    storeMock.renameMultiViewSession = vi.fn(async () => {});
    storeMock.reencodeCurrentVideo = vi.fn(async () => ({ statistics: {} }));
    storeMock.deleteVideoById = vi.fn(async () => {});
    storeMock.clearAllData = vi.fn(async () => {});
    storeMock.deleteMultiViewSessionById = vi.fn(async () => {});
    vi.stubGlobal('confirm', vi.fn(() => true));
    vi.stubGlobal('alert', vi.fn(() => {}));
  });

  it('emits entity-selected after successful video selection', async () => {
    const wrapper = mountSelector();

    await wrapper.get('.entity-main').trigger('click');
    await flushPromises();

    expect(storeMock.selectVideoEntity).toHaveBeenCalledWith('video-1');
    expect(wrapper.emitted('entity-selected')).toEqual([
      [{ type: 'video', id: 'video-1' }],
    ]);
  });

  it('emits entity-selected immediately when the clicked video is already active', async () => {
    storeMock.activeEntityType = 'video';
    storeMock.activeEntityId = 'video-1';

    const wrapper = mountSelector();

    await wrapper.get('.entity-main').trigger('click');

    expect(storeMock.selectVideoEntity).not.toHaveBeenCalled();
    expect(wrapper.emitted('entity-selected')).toEqual([
      [{ type: 'video', id: 'video-1' }],
    ]);
  });

  it('emits entity-selected after successful combined session selection', async () => {
    const wrapper = mountSelector();
    const entityButtons = wrapper.findAll('.entity-main');

    expect(entityButtons).toHaveLength(2);
    await entityButtons[1]!.trigger('click');
    await flushPromises();

    expect(storeMock.selectCombinedEntity).toHaveBeenCalledWith('session-1');
    expect(wrapper.emitted('entity-selected')).toContainEqual([
      { type: 'combined', id: 'session-1' },
    ]);
  });

  it('emits entity-selected after upload selects the new video', async () => {
    const wrapper = mountSelector();
    const input = wrapper.get('input[type="file"]').element as HTMLInputElement;
    const file = new File(['video'], 'new-video.mp4', { type: 'video/mp4' });

    Object.defineProperty(input, 'files', {
      configurable: true,
      value: [file],
    });

    await wrapper.get('input[type="file"]').trigger('change');
    await flushPromises();

    expect(storeMock.handleVideoUpload).toHaveBeenCalled();
    expect(wrapper.emitted('entity-selected')).toContainEqual([
      { type: 'video', id: 'uploaded-video' },
    ]);
  });

  it('does not emit entity-selected for rename-only actions', async () => {
    const wrapper = mountSelector();
    const renameButton = wrapper.findAll('button').find((candidate) => candidate.text() === 'Rename');
    if (!renameButton) {
      throw new Error('Rename button not found');
    }

    await renameButton.trigger('click');
    await flushPromises();

    expect(wrapper.emitted('entity-selected')).toBeUndefined();
  });

  it('does not emit entity-selected for delete-only actions', async () => {
    const wrapper = mountSelector();
    const deleteButton = wrapper.findAll('button').find((candidate) => candidate.text() === 'Delete Video');
    if (!deleteButton) {
      throw new Error('Delete Video button not found');
    }

    await deleteButton.trigger('click');
    await flushPromises();

    expect(storeMock.deleteVideoById).toHaveBeenCalledWith('video-1');
    expect(wrapper.emitted('entity-selected')).toBeUndefined();
  });
});

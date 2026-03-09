import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest';
import { effectScope, nextTick, reactive } from 'vue';

type WorkspaceEntityType = 'video' | 'combined' | null;

const routeState = reactive<{
  name: string;
  params: Record<string, unknown>;
}>({
  name: 'home',
  params: {},
});

const replaceMock = vi.fn(async () => {});

const storeMock = reactive<{
  activeEntityType: WorkspaceEntityType;
  activeEntityId: string | null;
  selectVideoEntity: (videoId: string) => Promise<void>;
  selectCombinedEntity: (sessionId: string) => Promise<void>;
  clearActiveEntity: () => void;
}>({
  activeEntityType: null,
  activeEntityId: null,
  selectVideoEntity: vi.fn(async () => {}),
  selectCombinedEntity: vi.fn(async () => {}),
  clearActiveEntity: vi.fn(() => {}),
});

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
  useRouter: () => ({ replace: replaceMock }),
}));

vi.mock('../../stores/analysis', () => ({
  useAnalysisStore: () => storeMock,
}));

import { useWorkspaceEntityRouting } from '../useWorkspaceEntityRouting';

async function flushWatchers(): Promise<void> {
  await nextTick();
  await Promise.resolve();
}

describe('useWorkspaceEntityRouting', () => {
  let scope: ReturnType<typeof effectScope> | null = null;

  beforeEach(() => {
    routeState.name = 'home';
    routeState.params = {};

    storeMock.activeEntityType = null;
    storeMock.activeEntityId = null;
    storeMock.selectVideoEntity = vi.fn(async () => {});
    storeMock.selectCombinedEntity = vi.fn(async () => {});
    storeMock.clearActiveEntity = vi.fn(() => {});
    replaceMock.mockClear();

    scope = effectScope();
    scope.run(() => {
      useWorkspaceEntityRouting();
    });
  });

  afterEach(() => {
    scope?.stop();
    scope = null;
  });

  it('selects the video entity when route is /video/:videoId', async () => {
    routeState.name = 'video';
    routeState.params = { videoId: 'video-123' };

    await flushWatchers();

    expect(storeMock.selectVideoEntity).toHaveBeenCalledWith('video-123');
  });

  it('pushes video route updates when active store entity changes', async () => {
    storeMock.activeEntityType = 'video';
    storeMock.activeEntityId = 'video-999';

    await flushWatchers();

    expect(replaceMock).toHaveBeenCalledWith({
      name: 'video',
      params: { videoId: 'video-999' },
    });
  });

  it('navigates back to home when no entity is active', async () => {
    storeMock.activeEntityType = 'video';
    storeMock.activeEntityId = 'video-123';
    await flushWatchers();

    routeState.name = 'video';
    routeState.params = { videoId: 'video-123' };
    await flushWatchers();

    replaceMock.mockClear();
    storeMock.activeEntityType = null;
    storeMock.activeEntityId = null;

    await flushWatchers();

    expect(replaceMock).toHaveBeenCalledWith({ name: 'home' });
  });
});

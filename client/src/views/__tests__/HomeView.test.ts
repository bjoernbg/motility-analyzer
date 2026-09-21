import { beforeEach, describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick, reactive } from 'vue';

type WorkspaceEntityType = 'video' | 'combined' | null;

const routeState = reactive<{
  name: string;
  params: Record<string, unknown>;
}>({
  name: 'home',
  params: {},
});

const storeMock = reactive<{
  activeEntityType: WorkspaceEntityType;
  activeEntityId: string | null;
  currentVideo: { id: string; filename: string; display_name?: string | null } | null;
  currentMultiViewSession: { id: string; name: string } | null;
  isInVideoMode: boolean;
  isInCombinedMode: boolean;
  loadVideos: ReturnType<typeof vi.fn>;
  loadMultiViewSessions: ReturnType<typeof vi.fn>;
  stopPolling: ReturnType<typeof vi.fn>;
}>({
  activeEntityType: null,
  activeEntityId: null,
  currentVideo: null,
  currentMultiViewSession: null,
  get isInVideoMode() {
    return this.activeEntityType === 'video' && this.activeEntityId !== null;
  },
  get isInCombinedMode() {
    return this.activeEntityType === 'combined' && this.activeEntityId !== null;
  },
  loadVideos: vi.fn(async () => {}),
  loadMultiViewSessions: vi.fn(async () => {}),
  stopPolling: vi.fn(() => {}),
});

vi.mock('vue-router', () => ({
  useRoute: () => routeState,
}));

vi.mock('../../stores/analysis', () => ({
  useAnalysisStore: () => storeMock,
}));

vi.mock('../../composables/useWorkspaceEntityRouting', () => ({
  useWorkspaceEntityRouting: () => {},
}));

import HomeView from '../HomeView.vue';

async function flushWatchers(): Promise<void> {
  await nextTick();
  await Promise.resolve();
}

function mountHomeView() {
  return mount(HomeView, {
    global: {
      stubs: {
        AnalysisParams: {
          template: '<div class="analysis-params-stub">Analysis Params</div>',
        },
        CombinedAnalysisSidebar: {
          template: '<div class="combined-sidebar-stub">Combined Sidebar</div>',
        },
        MediaViewer: {
          template: '<div class="media-viewer-stub" />',
        },
        MediaController: {
          template: '<div class="media-controller-stub" />',
        },
        AnalysisResults: {
          template: '<div class="analysis-results-stub" />',
        },
        MultiViewWorkspace: {
          template: '<div class="multi-view-workspace-stub" />',
        },
        MultiViewStartModal: {
          props: ['modelValue'],
          template: '<div class="multi-view-modal-stub" :data-open="String(modelValue)" />',
        },
        ProjectSelectorDrawer: {
          props: ['open'],
          emits: ['update:open', 'entity-selected', 'create-combined'],
          template: `
            <div class="project-drawer-stub" :data-open="String(open)">
              <button class="drawer-close" @click="$emit('update:open', false)">Close</button>
              <button class="drawer-select" @click="$emit('entity-selected', { type: 'video', id: 'video-1' })">
                Select
              </button>
              <button class="drawer-create" @click="$emit('create-combined')">Create</button>
            </div>
          `,
        },
      },
    },
  });
}

describe('HomeView', () => {
  beforeEach(() => {
    routeState.name = 'home';
    routeState.params = {};

    storeMock.activeEntityType = null;
    storeMock.activeEntityId = null;
    storeMock.currentVideo = null;
    storeMock.currentMultiViewSession = null;
    storeMock.loadVideos = vi.fn(async () => {});
    storeMock.loadMultiViewSessions = vi.fn(async () => {});
    storeMock.stopPolling = vi.fn(() => {});
  });

  it('auto-opens the drawer on the home route with no active entity and preloads catalogs', async () => {
    const wrapper = mountHomeView();

    await flushWatchers();

    expect(storeMock.loadVideos).toHaveBeenCalledTimes(1);
    expect(storeMock.loadMultiViewSessions).toHaveBeenCalledTimes(1);
    expect(wrapper.get('.project-drawer-stub').attributes('data-open')).toBe('true');
    expect(wrapper.text()).toContain('No project selected');
  });

  it('keeps the drawer closed for a route-driven active video selection', async () => {
    routeState.name = 'video';
    routeState.params = { videoId: 'video-1' };
    storeMock.activeEntityType = 'video';
    storeMock.activeEntityId = 'video-1';
    storeMock.currentVideo = {
      id: 'video-1',
      filename: 'project-a.mp4',
      display_name: 'Project A',
    };

    const wrapper = mountHomeView();

    await flushWatchers();

    expect(wrapper.get('.project-drawer-stub').attributes('data-open')).toBe('false');
    expect(wrapper.text()).toContain('Project A');
    expect(wrapper.text()).toContain('Change project');
  });

  it('opens from the sidebar trigger and closes when the drawer reports a selection', async () => {
    routeState.name = 'video';
    routeState.params = { videoId: 'video-1' };
    storeMock.activeEntityType = 'video';
    storeMock.activeEntityId = 'video-1';
    storeMock.currentVideo = {
      id: 'video-1',
      filename: 'project-a.mp4',
      display_name: 'Project A',
    };

    const wrapper = mountHomeView();
    await flushWatchers();

    await wrapper.get('.project-switcher-action').trigger('click');
    expect(wrapper.get('.project-drawer-stub').attributes('data-open')).toBe('true');

    await wrapper.get('.drawer-select').trigger('click');
    await flushWatchers();

    expect(wrapper.get('.project-drawer-stub').attributes('data-open')).toBe('false');
  });

  it('reopens the drawer when the active entity clears and routing returns to home', async () => {
    routeState.name = 'video';
    routeState.params = { videoId: 'video-1' };
    storeMock.activeEntityType = 'video';
    storeMock.activeEntityId = 'video-1';
    storeMock.currentVideo = {
      id: 'video-1',
      filename: 'project-a.mp4',
      display_name: 'Project A',
    };

    const wrapper = mountHomeView();
    await flushWatchers();

    storeMock.activeEntityType = null;
    storeMock.activeEntityId = null;
    storeMock.currentVideo = null;
    routeState.name = 'home';
    routeState.params = {};

    await flushWatchers();

    expect(wrapper.get('.project-drawer-stub').attributes('data-open')).toBe('true');
  });

  it('closes the drawer before opening the combined-analysis modal', async () => {
    const wrapper = mountHomeView();
    await flushWatchers();

    await wrapper.get('.drawer-create').trigger('click');
    await flushWatchers();

    expect(wrapper.get('.project-drawer-stub').attributes('data-open')).toBe('false');
    expect(wrapper.get('.multi-view-modal-stub').attributes('data-open')).toBe('true');
  });
});

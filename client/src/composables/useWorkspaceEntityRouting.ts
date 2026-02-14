import { ref, watch } from 'vue';
import { useRoute, useRouter } from 'vue-router';
import { useAnalysisStore } from '../stores/analysis';

export function useWorkspaceEntityRouting() {
  const store = useAnalysisStore();
  const route = useRoute();
  const router = useRouter();

  const syncingFromRoute = ref(false);
  const syncingToRoute = ref(false);

  async function applyRouteSelection() {
    if (syncingToRoute.value) {
      return;
    }

    syncingFromRoute.value = true;

    try {
      if (route.name === 'video') {
        const videoId = route.params.videoId;
        if (typeof videoId === 'string' && videoId.length > 0) {
          await store.selectVideoEntity(videoId);
          return;
        }
      }

      if (route.name === 'combined') {
        const sessionId = route.params.sessionId;
        if (typeof sessionId === 'string' && sessionId.length > 0) {
          await store.selectCombinedEntity(sessionId);
          return;
        }
      }

      store.clearActiveEntity();
    } catch {
      await router.replace({ name: 'home' });
    } finally {
      syncingFromRoute.value = false;
    }
  }

  watch(
    () => [route.name, route.params.videoId, route.params.sessionId],
    () => {
      void applyRouteSelection();
    },
    { immediate: true }
  );

  watch(
    () => [store.activeEntityType, store.activeEntityId] as const,
    async ([type, id]) => {
      if (syncingFromRoute.value) {
        return;
      }

      if (type === 'video' && id) {
        if (route.name === 'video' && route.params.videoId === id) {
          return;
        }

        syncingToRoute.value = true;
        try {
          await router.replace({ name: 'video', params: { videoId: id } });
        } finally {
          syncingToRoute.value = false;
        }
        return;
      }

      if (type === 'combined' && id) {
        if (route.name === 'combined' && route.params.sessionId === id) {
          return;
        }

        syncingToRoute.value = true;
        try {
          await router.replace({ name: 'combined', params: { sessionId: id } });
        } finally {
          syncingToRoute.value = false;
        }
        return;
      }

      if (route.name !== 'home') {
        syncingToRoute.value = true;
        try {
          await router.replace({ name: 'home' });
        } finally {
          syncingToRoute.value = false;
        }
      }
    }
  );
}

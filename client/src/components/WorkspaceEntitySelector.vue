<script setup lang="ts">
import { computed, onMounted, ref } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import type { Video } from '../lib/api';
import { videoNeedsReencoding } from '../lib/api';

const emit = defineEmits<{
  'create-combined': [];
}>();

const store = useAnalysisStore();

const fileInput = ref<HTMLInputElement | null>(null);
const isUploading = ref(false);
const selectingVideoId = ref<string | null>(null);
const editingVideoId = ref<string | null>(null);
const videoNameDraft = ref('');
const isSavingVideoName = ref(false);
const isReencoding = ref(false);
const isClearingAll = ref(false);
const deletingSessionId = ref<string | null>(null);
const editingSessionId = ref<string | null>(null);
const sessionNameDraft = ref('');
const isSavingSessionName = ref(false);

const VIDEO_UPLOAD_ACCEPT = '.mp4,.avi,.mov,.mkv,.webm,.mts,video/*';

const canReencodeCurrentVideo = computed(() => {
  if (!store.currentVideo?.metadata) {
    return false;
  }
  return videoNeedsReencoding(store.currentVideo.metadata);
});

onMounted(async () => {
  await Promise.all([store.loadVideos(), store.loadMultiViewSessions()]);
});

function getVideoPrimaryName(video: Video): string {
  const customName = video.display_name?.trim();
  return customName && customName.length > 0 ? customName : video.filename;
}

function hasCustomVideoName(video: Video): boolean {
  const customName = video.display_name?.trim();
  return Boolean(customName && customName.length > 0);
}

function startRenameVideo(video: Video) {
  editingVideoId.value = video.id;
  videoNameDraft.value = video.display_name?.trim() || video.filename;
}

function cancelRenameVideo() {
  editingVideoId.value = null;
  videoNameDraft.value = '';
}

async function saveRenameVideo(videoId: string) {
  if (isSavingVideoName.value) {
    return;
  }

  try {
    isSavingVideoName.value = true;
    const trimmed = videoNameDraft.value.trim();
    await store.renameVideo(videoId, trimmed.length > 0 ? trimmed : null);
    cancelRenameVideo();
  } catch (error) {
    console.error('Failed to rename video:', error);
  } finally {
    isSavingVideoName.value = false;
  }
}

async function selectVideo(videoId: string) {
  if (selectingVideoId.value === videoId || store.isLoadingMetadata) {
    return;
  }

  try {
    selectingVideoId.value = videoId;
    await store.selectVideoEntity(videoId);
  } catch (error) {
    console.error('Failed to select video:', error);
  } finally {
    selectingVideoId.value = null;
  }
}

async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) {
    return;
  }

  isUploading.value = true;

  try {
    await store.handleVideoUpload(file);
  } catch (error) {
    console.error('Upload failed:', error);
  } finally {
    isUploading.value = false;
    if (fileInput.value) {
      fileInput.value.value = '';
    }
  }
}

async function handleReencodeCurrentVideo() {
  if (!store.currentVideo || isReencoding.value) {
    return;
  }

  const filename = store.currentVideo.filename;

  const confirmed = confirm(
    `Re-encode "${filename}"?\n\n` +
      'This will:\n' +
      '• Replace the original video file\n' +
      '• Delete all analyses for this video\n' +
      '• Clear all cached data\n\n' +
      'This operation cannot be undone and may take several minutes.'
  );

  if (!confirmed) {
    return;
  }

  isReencoding.value = true;
  try {
    await store.reencodeCurrentVideo();
  } catch (error) {
    console.error('Re-encode failed:', error);
    alert(`Failed to re-encode "${filename}": ${error instanceof Error ? error.message : 'Unknown error'}`);
  } finally {
    isReencoding.value = false;
  }
}

async function handleClearAllData() {
  const confirmed = confirm(
    'Clear ALL data?\n\n' +
      'This will permanently delete:\n' +
      '  - All uploaded videos\n' +
      '  - All analyses and results\n' +
      '  - All cached heatmaps and metadata\n\n' +
      'This action cannot be undone.'
  );

  if (!confirmed) {
    return;
  }

  try {
    isClearingAll.value = true;
    await store.clearAllData();
  } catch (error) {
    console.error('Failed to clear all data:', error);
  } finally {
    isClearingAll.value = false;
  }
}

function startRenameSession(sessionId: string, currentName: string) {
  editingSessionId.value = sessionId;
  sessionNameDraft.value = currentName;
}

function cancelRenameSession() {
  editingSessionId.value = null;
  sessionNameDraft.value = '';
}

async function saveRenameSession(sessionId: string) {
  if (isSavingSessionName.value) {
    return;
  }

  try {
    isSavingSessionName.value = true;
    await store.renameMultiViewSession(sessionId, sessionNameDraft.value.trim());
    cancelRenameSession();
  } catch (error) {
    console.error('Failed to rename combined analysis:', error);
  } finally {
    isSavingSessionName.value = false;
  }
}

async function selectSession(sessionId: string) {
  try {
    await store.selectCombinedEntity(sessionId);
  } catch (error) {
    console.error('Failed to select combined analysis:', error);
  }
}

async function deleteSession(sessionId: string) {
  try {
    deletingSessionId.value = sessionId;
    await store.deleteMultiViewSessionById(sessionId);
  } catch (error) {
    console.error('Failed to delete combined analysis:', error);
  } finally {
    deletingSessionId.value = null;
  }
}
</script>

<template>
  <div class="workspace-entity-selector">
    <section class="entity-section">
      <div class="section-header">
        <h3>Videos</h3>
      </div>

      <div class="video-actions">
        <label class="upload-button">
          <span>{{ isUploading ? 'Uploading...' : 'Upload Video' }}</span>
          <input
            ref="fileInput"
            type="file"
            :accept="VIDEO_UPLOAD_ACCEPT"
            class="hidden-input"
            @change="handleFileSelect"
          />
        </label>

        <button
          class="action-button"
          :disabled="!store.currentVideo || !canReencodeCurrentVideo || isReencoding || store.isLoadingMetadata"
          @click="handleReencodeCurrentVideo"
        >
          {{ isReencoding ? 'Re-encoding...' : 'Re-encode Selected' }}
        </button>
      </div>

      <div v-if="store.videos.length === 0" class="empty-state">No videos yet.</div>
      <div v-else class="entity-list">
        <div
          v-for="video in store.videos"
          :key="video.id"
          class="entity-item"
          :class="{ active: store.activeEntityType === 'video' && store.activeEntityId === video.id }"
        >
          <button
            class="entity-main"
            :disabled="editingVideoId === video.id || selectingVideoId === video.id"
            @click="selectVideo(video.id)"
          >
            <p class="entity-title">{{ getVideoPrimaryName(video) }}</p>
            <p v-if="hasCustomVideoName(video)" class="entity-subtitle">File: {{ video.filename }}</p>
            <p class="entity-meta">{{ new Date(video.upload_date).toLocaleDateString() }}</p>
          </button>

          <div class="entity-actions-row">
            <template v-if="editingVideoId === video.id">
              <input
                v-model="videoNameDraft"
                class="rename-input"
                type="text"
                maxlength="200"
                placeholder="Display name (empty to reset)"
                @keyup.enter="saveRenameVideo(video.id)"
                @keyup.escape="cancelRenameVideo"
              />
              <button class="small-button" :disabled="isSavingVideoName" @click="saveRenameVideo(video.id)">Save</button>
              <button class="small-button" :disabled="isSavingVideoName" @click="cancelRenameVideo">Cancel</button>
            </template>
            <button v-else class="small-button" @click="startRenameVideo(video)">Rename</button>
          </div>
        </div>
      </div>

      <button class="clear-all-button" :disabled="isClearingAll" @click="handleClearAllData">
        {{ isClearingAll ? 'Clearing...' : 'Clear All Data' }}
      </button>
    </section>

    <section class="entity-section">
      <div class="section-header">
        <h3>Combined Analyses</h3>
        <button class="small-button" @click="emit('create-combined')">New Combined Analysis</button>
      </div>

      <div v-if="store.multiViewSessions.length === 0" class="empty-state">No combined analyses yet.</div>
      <div v-else class="entity-list">
        <div
          v-for="session in store.multiViewSessions"
          :key="session.id"
          class="entity-item"
          :class="{ active: store.activeEntityType === 'combined' && store.activeEntityId === session.id }"
        >
          <button class="entity-main" :disabled="editingSessionId === session.id" @click="selectSession(session.id)">
            <p class="entity-title">{{ session.name }}</p>
            <p class="entity-meta">{{ new Date(session.created_at).toLocaleString() }}</p>
          </button>

          <div class="entity-actions-row">
            <template v-if="editingSessionId === session.id">
              <input
                v-model="sessionNameDraft"
                class="rename-input"
                type="text"
                maxlength="200"
                placeholder="Combined analysis name"
                @keyup.enter="saveRenameSession(session.id)"
                @keyup.escape="cancelRenameSession"
              />
              <button class="small-button" :disabled="isSavingSessionName" @click="saveRenameSession(session.id)">Save</button>
              <button class="small-button" :disabled="isSavingSessionName" @click="cancelRenameSession">Cancel</button>
            </template>
            <template v-else>
              <button class="small-button" @click="startRenameSession(session.id, session.name)">Rename</button>
              <button
                class="small-button danger"
                :disabled="deletingSessionId === session.id"
                @click="deleteSession(session.id)"
              >
                {{ deletingSessionId === session.id ? 'Deleting...' : 'Delete' }}
              </button>
            </template>
          </div>
        </div>
      </div>
    </section>

    <p v-if="store.error" class="error-text">{{ store.error }}</p>
  </div>
</template>

<style scoped>
.workspace-entity-selector {
  padding: 0.85rem;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.entity-section {
  display: flex;
  flex-direction: column;
  gap: 0.6rem;
}

.entity-section + .entity-section {
  border-top: 1px solid var(--border-light);
  padding-top: 1rem;
}

.section-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.5rem;
}

h3 {
  margin: 0;
  font-size: 0.95rem;
}

.video-actions {
  display: flex;
  gap: 0.5rem;
}

.upload-button,
.action-button,
.small-button,
.clear-all-button {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.35rem 0.55rem;
}

.upload-button {
  display: inline-flex;
  align-items: center;
}

.action-button,
.clear-all-button {
  flex: 1;
}

.clear-all-button {
  color: var(--color-error-600);
  border-color: var(--color-error-300);
}

.hidden-input {
  display: none;
}

.entity-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.entity-item {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  overflow: hidden;
}

.entity-item.active {
  border-color: var(--color-primary-500);
  background: var(--color-primary-50);
}

.entity-main {
  width: 100%;
  border: none;
  background: transparent;
  text-align: left;
  padding: 0.6rem;
  cursor: pointer;
}

.entity-title {
  margin: 0;
  font-size: 0.86rem;
  font-weight: 600;
}

.entity-subtitle,
.entity-meta {
  margin: 0.2rem 0 0;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.entity-actions-row {
  border-top: 1px solid var(--border-light);
  padding: 0.45rem 0.55rem;
  display: flex;
  gap: 0.4rem;
  flex-wrap: wrap;
}

.rename-input {
  min-width: 140px;
  flex: 1;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 0.3rem 0.4rem;
  font-size: 0.78rem;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.small-button.danger {
  color: var(--color-error-600);
  border-color: var(--color-error-300);
}

.empty-state {
  font-size: 0.82rem;
  color: var(--text-secondary);
}

.error-text {
  margin: 0;
  padding: 0.5rem;
  border-radius: 6px;
  background: var(--color-error-100);
  border: 1px solid var(--color-error-200);
  color: var(--color-error-700);
  font-size: 0.8rem;
}

button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

@media (max-width: 1200px) {
  .video-actions {
    flex-direction: column;
  }
}
</style>

<script setup lang="ts">
import { reactive, ref } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import type { Video, MultiViewSession } from '../lib/api';
import { videoNeedsReencoding } from '../lib/api';
import { getVideoDisplayName, hasCustomDisplayName } from '../lib/domain/displayNames';
import { Popover, PopoverContent, PopoverTrigger } from './ui/popover';
import { Icon } from './ui/icon';

const emit = defineEmits<{
  'create-combined': [];
  'entity-selected': [{ type: 'video' | 'combined'; id: string }];
}>();

const store = useAnalysisStore();

const fileInput = ref<HTMLInputElement | null>(null);
const isUploading = ref(false);
const selectingVideoId = ref<string | null>(null);
const editingVideoId = ref<string | null>(null);
const videoNameDraft = ref('');
const isSavingVideoName = ref(false);
const isReencoding = ref(false);
const reencodingVideoId = ref<string | null>(null);
const isClearingAll = ref(false);
const isDeletingVideoId = ref<string | null>(null);
const deletingSessionId = ref<string | null>(null);
const editingSessionId = ref<string | null>(null);
const sessionNameDraft = ref('');
const isSavingSessionName = ref(false);
const videosHeaderMenuOpen = ref(false);
const videoMenuOpen = reactive<Record<string, boolean>>({});
const sessionMenuOpen = reactive<Record<string, boolean>>({});

const VIDEO_UPLOAD_ACCEPT = '.mp4,.avi,.mov,.mkv,.webm,.mts,video/*';

function isSessionAutoAligned(session: MultiViewSession): boolean {
  const alignmentSource = session.metadata?.alignment?.source;
  const realignStatus = session.metadata?.realign_job?.status;
  return alignmentSource === 'auto' || realignStatus === 'committed';
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

function startRenameVideoFromMenu(video: Video) {
  videoMenuOpen[video.id] = false;
  startRenameVideo(video);
}

async function selectVideo(videoId: string) {
  if (selectingVideoId.value === videoId || store.isLoadingMetadata) {
    return;
  }

  if (store.activeEntityType === 'video' && store.activeEntityId === videoId) {
    emit('entity-selected', { type: 'video', id: videoId });
    return;
  }

  try {
    selectingVideoId.value = videoId;
    await store.selectVideoEntity(videoId);
    emit('entity-selected', { type: 'video', id: videoId });
  } catch (error) {
    console.error('Failed to select video:', error);
  } finally {
    selectingVideoId.value = null;
  }
}

function openUploadPicker() {
  fileInput.value?.click();
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
    if (store.activeEntityType === 'video' && store.activeEntityId) {
      emit('entity-selected', { type: 'video', id: store.activeEntityId });
    }
  } catch (error) {
    console.error('Upload failed:', error);
  } finally {
    isUploading.value = false;
    if (fileInput.value) {
      fileInput.value.value = '';
    }
  }
}

function canReencodeVideo(video: Video): boolean {
  if (isReencoding.value || store.isLoadingMetadata) {
    return false;
  }

  if (store.currentVideo?.id === video.id && store.currentVideo.metadata) {
    return videoNeedsReencoding(store.currentVideo.metadata);
  }

  return true;
}

function isReencodingVideo(videoId: string): boolean {
  return isReencoding.value && reencodingVideoId.value === videoId;
}

async function handleReencodeVideo(video: Video) {
  videoMenuOpen[video.id] = false;

  if (!canReencodeVideo(video)) {
    return;
  }

  if (
    store.currentVideo?.id !== video.id ||
    store.activeEntityType !== 'video' ||
    store.activeEntityId !== video.id
  ) {
    await selectVideo(video.id);
  }

  const currentVideo = store.currentVideo;
  if (!currentVideo || currentVideo.id !== video.id) {
    return;
  }

  if (!videoNeedsReencoding(currentVideo.metadata)) {
    return;
  }

  const filename = currentVideo.filename;
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
  reencodingVideoId.value = currentVideo.id;
  try {
    await store.reencodeCurrentVideo();
  } catch (error) {
    console.error('Re-encode failed:', error);
    alert(
      `Failed to re-encode "${filename}": ${error instanceof Error ? error.message : 'Unknown error'}`
    );
  } finally {
    isReencoding.value = false;
    reencodingVideoId.value = null;
  }
}

async function handleDeleteVideo(video: Video) {
  videoMenuOpen[video.id] = false;

  if (isDeletingVideoId.value) {
    return;
  }

  const confirmed = confirm(
    `Delete "${getVideoDisplayName(video)}"?\n\n` +
      'This will permanently delete:\n' +
      '• The video file\n' +
      '• All analyses for this video\n' +
      '• Combined analyses that reference those analyses\n' +
      '• Cached metadata and heatmaps\n\n' +
      'This action cannot be undone.'
  );

  if (!confirmed) {
    return;
  }

  try {
    isDeletingVideoId.value = video.id;
    await store.deleteVideoById(video.id);
    if (editingVideoId.value === video.id) {
      cancelRenameVideo();
    }
  } catch (error) {
    console.error('Failed to delete video:', error);
  } finally {
    isDeletingVideoId.value = null;
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

  videosHeaderMenuOpen.value = false;

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

function startRenameSessionFromMenu(sessionId: string, currentName: string) {
  sessionMenuOpen[sessionId] = false;
  startRenameSession(sessionId, currentName);
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
  if (store.activeEntityType === 'combined' && store.activeEntityId === sessionId) {
    emit('entity-selected', { type: 'combined', id: sessionId });
    return;
  }

  try {
    await store.selectCombinedEntity(sessionId);
    emit('entity-selected', { type: 'combined', id: sessionId });
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

async function deleteSessionFromMenu(sessionId: string) {
  sessionMenuOpen[sessionId] = false;
  await deleteSession(sessionId);
}
</script>

<template>
  <div class="workspace-entity-selector">
    <section class="entity-section">
      <div class="section-header">
        <h3 class="section-title">Videos</h3>
        <div class="section-actions">
          <button
            class="icon-button"
            :disabled="isUploading"
            aria-label="Upload video"
            :title="isUploading ? 'Uploading...' : 'Upload video'"
            @click="openUploadPicker"
          >
            <Icon name="mdi:upload" :class="{ spinning: isUploading }" />
          </button>

          <input
            ref="fileInput"
            type="file"
            :accept="VIDEO_UPLOAD_ACCEPT"
            class="hidden-input"
            @change="handleFileSelect"
          />

          <Popover v-model:open="videosHeaderMenuOpen">
            <PopoverTrigger as-child>
              <button
                class="icon-button"
                aria-label="Video actions"
                title="Video actions"
              >
                <Icon name="mdi:dots-horizontal" />
              </button>
            </PopoverTrigger>
            <PopoverContent align="end" class="entity-menu-content">
              <button
                class="menu-item danger"
                :disabled="isClearingAll"
                @click="handleClearAllData"
              >
                {{ isClearingAll ? 'Clearing...' : 'Clear All Data' }}
              </button>
            </PopoverContent>
          </Popover>
        </div>
      </div>

      <div v-if="store.videos.length === 0" class="empty-state">No videos yet.</div>
      <div v-else class="entity-list">
        <div
          v-for="video in store.videos"
          :key="video.id"
          class="entity-item"
          :class="{ active: store.activeEntityType === 'video' && store.activeEntityId === video.id }"
        >
          <div class="entity-item-header">
            <button
              class="entity-main"
              :disabled="editingVideoId === video.id || selectingVideoId === video.id || isDeletingVideoId === video.id"
              @click="selectVideo(video.id)"
            >
              <p class="entity-title">{{ getVideoDisplayName(video) }}</p>
              <p v-if="hasCustomDisplayName(video)" class="entity-subtitle">File: {{ video.filename }}</p>
              <p class="entity-meta">{{ new Date(video.upload_date).toLocaleDateString() }}</p>
            </button>

            <Popover v-model:open="videoMenuOpen[video.id]">
              <PopoverTrigger as-child>
                <button
                  class="item-menu-trigger"
                  :class="{ 'menu-open': Boolean(videoMenuOpen[video.id]) }"
                  :disabled="editingVideoId === video.id || isDeletingVideoId === video.id"
                  aria-label="Video item actions"
                  title="Video item actions"
                >
                  <Icon name="mdi:dots-horizontal" />
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" class="entity-menu-content">
                <button class="menu-item" @click="startRenameVideoFromMenu(video)">Rename</button>
                <button class="menu-item" :disabled="!canReencodeVideo(video)" @click="handleReencodeVideo(video)">
                  {{ isReencodingVideo(video.id) ? 'Re-encoding...' : 'Re-encode' }}
                </button>
                <button
                  class="menu-item danger"
                  :disabled="isDeletingVideoId === video.id"
                  @click="handleDeleteVideo(video)"
                >
                  {{ isDeletingVideoId === video.id ? 'Deleting...' : 'Delete Video' }}
                </button>
              </PopoverContent>
            </Popover>
          </div>

          <div v-if="editingVideoId === video.id" class="entity-actions-row">
            <input
              v-model="videoNameDraft"
              class="rename-input"
              type="text"
              maxlength="200"
              placeholder="Display name (empty to reset)"
              @keyup.enter="saveRenameVideo(video.id)"
              @keyup.escape="cancelRenameVideo"
            />
            <button class="small-button" :disabled="isSavingVideoName" @click="saveRenameVideo(video.id)">
              Save
            </button>
            <button class="small-button" :disabled="isSavingVideoName" @click="cancelRenameVideo">Cancel</button>
          </div>
        </div>
      </div>
    </section>

    <section class="entity-section">
      <div class="section-header">
        <h3 class="section-title">Combined Analyses</h3>
        <button
          class="icon-button"
          aria-label="Create combined analysis"
          title="Create combined analysis"
          @click="emit('create-combined')"
        >
          <Icon name="mdi:plus" />
        </button>
      </div>

      <div v-if="store.multiViewSessions.length === 0" class="empty-state">No combined analyses yet.</div>
      <div v-else class="entity-list">
        <div
          v-for="session in store.multiViewSessions"
          :key="session.id"
          class="entity-item"
          :class="{ active: store.activeEntityType === 'combined' && store.activeEntityId === session.id }"
        >
          <div class="entity-item-header">
            <button class="entity-main" :disabled="editingSessionId === session.id" @click="selectSession(session.id)">
              <p class="entity-title">
                {{ session.name }}
                <span v-if="isSessionAutoAligned(session)" class="auto-aligned-badge">Auto-aligned</span>
              </p>
              <p class="entity-meta">{{ new Date(session.created_at).toLocaleString() }}</p>
            </button>

            <Popover v-model:open="sessionMenuOpen[session.id]">
              <PopoverTrigger as-child>
                <button
                  class="item-menu-trigger"
                  :class="{ 'menu-open': Boolean(sessionMenuOpen[session.id]) }"
                  :disabled="editingSessionId === session.id || deletingSessionId === session.id"
                  aria-label="Combined analysis actions"
                  title="Combined analysis actions"
                >
                  <Icon name="mdi:dots-horizontal" />
                </button>
              </PopoverTrigger>
              <PopoverContent align="end" class="entity-menu-content">
                <button class="menu-item" @click="startRenameSessionFromMenu(session.id, session.name)">Rename</button>
                <button
                  class="menu-item danger"
                  :disabled="deletingSessionId === session.id"
                  @click="deleteSessionFromMenu(session.id)"
                >
                  {{ deletingSessionId === session.id ? 'Deleting...' : 'Delete' }}
                </button>
              </PopoverContent>
            </Popover>
          </div>

          <div v-if="editingSessionId === session.id" class="entity-actions-row">
            <input
              v-model="sessionNameDraft"
              class="rename-input"
              type="text"
              maxlength="200"
              placeholder="Combined analysis name"
              @keyup.enter="saveRenameSession(session.id)"
              @keyup.escape="cancelRenameSession"
            />
            <button class="small-button" :disabled="isSavingSessionName" @click="saveRenameSession(session.id)">
              Save
            </button>
            <button class="small-button" :disabled="isSavingSessionName" @click="cancelRenameSession">Cancel</button>
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

.section-title {
  margin: 0;
  font-size: 0.95rem;
}

.section-actions {
  display: flex;
  align-items: center;
  gap: 0.35rem;
}

.icon-button {
  width: 30px;
  height: 30px;
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  display: inline-flex;
  align-items: center;
  justify-content: center;
}

.icon-button:hover:not(:disabled),
.item-menu-trigger:hover:not(:disabled) {
  background: color-mix(in oklch, var(--bg-secondary) 80%, var(--color-primary-100));
}

.icon-button:focus-visible,
.item-menu-trigger:focus-visible,
.menu-item:focus-visible,
.small-button:focus-visible,
.entity-main:focus-visible {
  outline: 2px solid var(--color-primary-500);
  outline-offset: 2px;
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

.entity-item-header {
  display: flex;
  align-items: flex-start;
}

.entity-main {
  flex: 1;
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
  display: inline-flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
}

.auto-aligned-badge {
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: var(--bg-secondary);
  color: var(--text-secondary);
  font-size: 0.65rem;
  font-weight: 600;
  line-height: 1;
  padding: 0.2rem 0.4rem;
}

.entity-subtitle,
.entity-meta {
  margin: 0.2rem 0 0;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.item-menu-trigger {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  cursor: pointer;
  width: 28px;
  height: 28px;
  margin: 0.45rem 0.45rem 0 0;
  display: inline-flex;
  align-items: center;
  justify-content: center;
  opacity: 0;
  transition: opacity 0.15s ease;
}

.entity-item:hover .item-menu-trigger,
.entity-item:focus-within .item-menu-trigger,
.item-menu-trigger.menu-open {
  opacity: 1;
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

.small-button {
  border: 1px solid var(--border-light);
  border-radius: 6px;
  background: var(--bg-secondary);
  color: var(--text-primary);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.35rem 0.55rem;
}

:deep(.entity-menu-content) {
  width: 180px;
  padding: 0.35rem;
  display: flex;
  flex-direction: column;
  gap: 0.2rem;
}

.menu-item {
  border: 1px solid transparent;
  border-radius: 6px;
  background: transparent;
  color: var(--text-primary);
  font-size: 0.8rem;
  cursor: pointer;
  padding: 0.35rem 0.5rem;
  text-align: left;
}

.menu-item:hover:not(:disabled) {
  background: var(--bg-secondary);
}

.menu-item.danger {
  color: var(--color-error-600);
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

.spinning {
  animation: spin 1s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

@media (hover: none), (pointer: coarse) {
  .item-menu-trigger {
    opacity: 1;
  }
}
</style>

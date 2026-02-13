<script setup lang="ts">
import { ref, computed, onMounted, onUnmounted, watch } from 'vue';
import { useRouter, useRoute } from 'vue-router';
import { useAnalysisStore } from '../stores/analysis';
import type { Video, ReencodeStatistics } from '../lib/api';
import { videoNeedsReencoding } from '../lib/api';

const store = useAnalysisStore();
const router = useRouter();
const route = useRoute();
const fileInput = ref<HTMLInputElement | null>(null);
const isUploading = ref(false);
const selectingVideoId = ref<string | null>(null);
const showModal = ref(false);
const isReencoding = ref(false);
const showSuccessModal = ref(false);
const encodeStats = ref<ReencodeStatistics | null>(null);
const isClearingAll = ref(false);

// Check if current video needs re-encoding
const needsReencoding = computed(() => {
  if (!store.currentVideo?.metadata) return false;
  return videoNeedsReencoding(store.currentVideo.metadata);
});

// Function to load video from URL
async function loadVideoFromUrl() {
  const videoId = route.params.videoId as string | undefined;
  if (!videoId) {
    return;
  }
  
  // Wait for videos to be loaded
  if (store.videos.length === 0) {
    await store.loadVideos();
  }
  
  const video = store.videos.find(v => v.id === videoId);
  if (video && video.id !== store.currentVideo?.id) {
    try {
      await store.selectVideo(video);
    } catch (error) {
      console.error('Failed to load video from URL:', error);
      // Navigate to home if video not found
      router.replace({ name: 'home' });
    }
  } else if (!video) {
    // Video not found, navigate to home
    router.replace({ name: 'home' });
  }
}

onMounted(async () => {
  // Load videos first
  await store.loadVideos();
  
  // Check URL for video parameter and load video if present
  await loadVideoFromUrl();
  
  // Add ESC key listener
  document.addEventListener('keydown', handleKeyDown);
});

// Watch for route changes (e.g., browser back/forward)
watch(() => route.params.videoId, async (videoId) => {
  if (videoId && typeof videoId === 'string') {
    await loadVideoFromUrl();
  }
});

// Watch for video changes and update URL
watch(() => store.currentVideo, (video) => {
  const currentVideoId = route.params.videoId as string | undefined;
  if (video) {
    // Only update URL if it's different from current
    if (currentVideoId !== video.id) {
      router.replace({ name: 'video', params: { videoId: video.id } });
    }
  } else {
    // Navigate to home if no video is selected (only if we're on video route)
    if (currentVideoId) {
      router.replace({ name: 'home' });
    }
  }
});

onUnmounted(() => {
  // Remove ESC key listener
  document.removeEventListener('keydown', handleKeyDown);
});

function handleKeyDown(event: KeyboardEvent) {
  if (event.key === 'Escape' && showModal.value) {
    closeModal();
  }
}

function openModal() {
  showModal.value = true;
  // Load videos when opening modal
  if (store.videos.length === 0) {
    store.loadVideos();
  }
}

function closeModal() {
  showModal.value = false;
}

async function handleFileSelect(event: Event) {
  const target = event.target as HTMLInputElement;
  const file = target.files?.[0];
  if (!file) return;

  isUploading.value = true;
  try {
    await store.handleVideoUpload(file);
    // URL will be updated automatically via the watch on currentVideo
    // Close modal after successful upload
    closeModal();
  } catch (error) {
    console.error('Upload failed:', error);
  } finally {
    isUploading.value = false;
    if (fileInput.value) {
      fileInput.value.value = '';
    }
  }
}

async function selectVideo(video: Video) {
  if (selectingVideoId.value === video.id || store.isLoadingMetadata) {
    return; // Already selecting this video or metadata is loading
  }

  selectingVideoId.value = video.id;
  try {
    await store.selectVideo(video);
    // Close modal after successful selection
    closeModal();
  } catch (error) {
    console.error('Failed to select video:', error);
    // Error is already set in the store, so we don't need to handle it here
  } finally {
    selectingVideoId.value = null;
  }
}

async function handleReencode() {
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
    const stats = await store.reencodeCurrentVideo();
    encodeStats.value = stats;
    showSuccessModal.value = true;
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

  if (!confirmed) return;

  isClearingAll.value = true;
  try {
    await store.clearAllData();
    closeModal();
  } catch (error) {
    console.error('Failed to clear all data:', error);
  } finally {
    isClearingAll.value = false;
  }
}

function formatFileSize(bytes: number): string {
  if (bytes < 1024) return `${bytes} B`;
  if (bytes < 1024 * 1024) return `${(bytes / 1024).toFixed(2)} KB`;
  if (bytes < 1024 * 1024 * 1024) return `${(bytes / (1024 * 1024)).toFixed(2)} MB`;
  return `${(bytes / (1024 * 1024 * 1024)).toFixed(2)} GB`;
}

function formatDuration(seconds: number): string {
  if (seconds < 60) return `${seconds.toFixed(1)}s`;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  return `${minutes}m ${secs}s`;
}

function closeSuccessModal() {
  showSuccessModal.value = false;
  encodeStats.value = null;
}
</script>

<template>
  <div class="video-selector">
    <div class="current-video-display">
      <div v-if="store.currentVideo" class="video-info">
        <div class="video-name">{{ store.currentVideo.filename }}</div>
        <div class="video-date">
          {{ new Date(store.currentVideo.upload_date).toLocaleDateString() }}
        </div>
        <div v-if="store.isLoadingMetadata" class="loading-indicator">
          Loading metadata...
        </div>
      </div>
      <div v-else class="no-video-placeholder">
        No video selected
      </div>
      <div class="button-group">
        <button
          v-if="store.currentVideo && needsReencoding"
          class="reencode-button"
          @click="handleReencode"
          :disabled="store.isLoading || store.isLoadingMetadata || isReencoding"
          :title="`Re-encode: ${store.currentVideo.filename}`"
        >
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <rect x="2" y="2" width="20" height="20" rx="2.18" ry="2.18"></rect>
            <line x1="7" y1="2" x2="7" y2="22"></line>
            <line x1="17" y1="2" x2="17" y2="22"></line>
            <line x1="2" y1="12" x2="22" y2="12"></line>
            <line x1="2" y1="7" x2="7" y2="7"></line>
            <line x1="2" y1="17" x2="7" y2="17"></line>
            <line x1="17" y1="17" x2="22" y2="17"></line>
            <line x1="17" y1="7" x2="22" y2="7"></line>
          </svg>
        </button>
        <button class="change-button" @click="openModal" :disabled="store.isLoadingMetadata" title="Select or upload video">
          <svg xmlns="http://www.w3.org/2000/svg" width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
            <path d="M11 4H4a2 2 0 0 0-2 2v14a2 2 0 0 0 2 2h14a2 2 0 0 0 2-2v-7"></path>
            <path d="M18.5 2.5a2.121 2.121 0 0 1 3 3L12 15l-4 1 1-4 9.5-9.5z"></path>
          </svg>
        </button>
      </div>
    </div>

    <!-- Encoding Progress Overlay -->
    <Teleport to="body">
      <div v-if="isReencoding" class="encoding-overlay">
        <div class="encoding-modal">
          <div class="encoding-spinner">
            <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round" class="spinner-icon">
              <circle cx="12" cy="12" r="10"></circle>
              <path d="M12 6v6l4 2"></path>
            </svg>
          </div>
          <h2>Re-encoding Video</h2>
          <p class="encoding-message">
            Please wait while the video is being re-encoded.<br>
            This may take several minutes depending on the video size.
          </p>
          <p class="encoding-warning">Do not close this window or navigate away.</p>
        </div>
      </div>
    </Teleport>

    <!-- Success Statistics Modal -->
    <Teleport to="body">
      <div v-if="showSuccessModal && encodeStats" class="encoding-overlay" @click.self="closeSuccessModal">
        <div class="success-modal">
          <div class="success-icon">
            <svg xmlns="http://www.w3.org/2000/svg" width="64" height="64" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
              <path d="M22 11.08V12a10 10 0 1 1-5.93-9.14"></path>
              <polyline points="22 4 12 14.01 9 11.01"></polyline>
            </svg>
          </div>
          <h2>Re-encoding Complete!</h2>
          <div class="stats-grid">
            <div class="stat-item">
              <div class="stat-label">Duration</div>
              <div class="stat-value">{{ formatDuration(encodeStats.duration_seconds) }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">Original Size</div>
              <div class="stat-value">{{ formatFileSize(encodeStats.original_size_bytes) }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">New Size</div>
              <div class="stat-value">{{ formatFileSize(encodeStats.new_size_bytes) }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">Size Reduction</div>
              <div class="stat-value" :class="{ positive: encodeStats.size_reduction_percent > 0 }">
                {{ encodeStats.size_reduction_percent > 0 ? '-' : '+' }}{{ Math.abs(encodeStats.size_reduction_percent).toFixed(1) }}%
              </div>
            </div>
            <div class="stat-item" v-if="encodeStats.original_codec">
              <div class="stat-label">Original Codec</div>
              <div class="stat-value">{{ encodeStats.original_codec }}</div>
            </div>
            <div class="stat-item">
              <div class="stat-label">New Codec</div>
              <div class="stat-value">{{ encodeStats.new_codec }}</div>
            </div>
          </div>
          <button class="dismiss-button" @click="closeSuccessModal">Done</button>
        </div>
      </div>
    </Teleport>

    <!-- Modal Overlay -->
    <Teleport to="body">
      <div v-if="showModal" class="modal-overlay" @click.self="closeModal">
        <div class="modal-container">
          <div class="modal-header">
            <h2>Select Video</h2>
            <button class="close-button" @click="closeModal" aria-label="Close">
              <svg xmlns="http://www.w3.org/2000/svg" width="20" height="20" viewBox="0 0 24 24" fill="none" stroke="currentColor" stroke-width="2" stroke-linecap="round" stroke-linejoin="round">
                <line x1="18" y1="6" x2="6" y2="18"></line>
                <line x1="6" y1="6" x2="18" y2="18"></line>
              </svg>
            </button>
          </div>

          <div class="modal-content">
            <div class="upload-section">
              <label for="file-input" class="upload-button">
                <span v-if="!isUploading">Upload New Video</span>
                <span v-else>Uploading...</span>
              </label>
              <input
                id="file-input"
                ref="fileInput"
                type="file"
                accept="video/*"
                @change="handleFileSelect"
                style="display: none"
              />
            </div>

            <div class="video-list">
              <h3>Available Videos</h3>
              <div v-if="store.isLoading && store.videos.length === 0" class="loading">
                Loading videos...
              </div>
              <div v-else-if="store.videos.length === 0" class="empty">
                No videos available. Upload a video to get started.
              </div>
              <div v-else class="video-items">
                <button
                  v-for="video in store.videos"
                  :key="video.id"
                  class="video-item"
                  :class="{ 
                    active: store.currentVideo?.id === video.id,
                    loading: selectingVideoId === video.id || (store.isLoadingMetadata && store.currentVideo?.id === video.id)
                  }"
                  :disabled="store.isLoadingMetadata || selectingVideoId === video.id"
                  @click="selectVideo(video)"
                >
                  <div class="video-name">{{ video.filename }}</div>
                  <div class="video-date">
                    {{ new Date(video.upload_date).toLocaleDateString() }}
                  </div>
                  <div v-if="selectingVideoId === video.id || (store.isLoadingMetadata && store.currentVideo?.id === video.id)" class="loading-indicator">
                    Loading metadata...
                  </div>
                </button>
              </div>
            </div>

            <div v-if="store.error" class="error">
              {{ store.error }}
            </div>

            <div class="clear-all-section">
              <button
                class="clear-all-button"
                :disabled="isClearingAll"
                @click="handleClearAllData"
              >
                {{ isClearingAll ? 'Clearing...' : 'Clear All Data' }}
              </button>
            </div>
          </div>
        </div>
      </div>
    </Teleport>
  </div>
</template>

<style scoped>
.video-selector {
  padding: 0.75rem;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
}

.current-video-display {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 0.75rem;
}

.video-info {
  flex: 1;
  min-width: 0;
}

.video-info .video-name {
  font-weight: 500;
  font-size: 0.9rem;
  margin-bottom: 0.25rem;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.video-info .video-date {
  font-size: 0.8rem;
  color: var(--text-secondary);
}

.no-video-placeholder {
  flex: 1;
  color: var(--color-neutral-500);
  font-style: italic;
  font-size: 0.9rem;
}

.button-group {
  flex-shrink: 0;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.change-button,
.reencode-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.change-button:hover:not(:disabled) {
  background: var(--color-neutral-200);
  border-color: var(--color-success-500);
  color: var(--color-success-500);
}

.reencode-button:hover:not(:disabled) {
  background: var(--color-neutral-200);
  border-color: #f97316;
  color: #f97316;
}

.change-button:disabled,
.reencode-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.loading-indicator {
  font-size: 0.75rem;
  color: var(--color-success-500);
  margin-top: 0.25rem;
  font-style: italic;
}

/* Modal Styles */
.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: color-mix(in oklch, var(--color-neutral-900) 80%, transparent);
  backdrop-filter: blur(2px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
  animation: fadeIn 0.2s ease-out;
}

@keyframes fadeIn {
  from {
    opacity: 0;
  }
  to {
    opacity: 1;
  }
}

.modal-container {
  background: var(--bg-primary);
  border-radius: 8px;
  box-shadow: var(--shadow-lg);
  max-width: 600px;
  width: 90%;
  max-height: 80vh;
  display: flex;
  flex-direction: column;
  animation: slideUp 0.2s ease-out;
}

@keyframes slideUp {
  from {
    transform: translateY(20px);
    opacity: 0;
  }
  to {
    transform: translateY(0);
    opacity: 1;
  }
}

.modal-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 1.25rem 1.5rem;
  border-bottom: 1px solid var(--color-neutral-200);
}

.modal-header h2 {
  margin: 0;
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.close-button {
  display: flex;
  align-items: center;
  justify-content: center;
  width: 32px;
  height: 32px;
  padding: 0;
  background: transparent;
  border: none;
  border-radius: 4px;
  cursor: pointer;
  color: var(--text-secondary);
  transition: all 0.2s;
}

.close-button:hover {
  background: var(--bg-secondary);
  color: var(--text-primary);
}

.modal-content {
  padding: 1.5rem;
  overflow-y: auto;
  flex: 1;
}

.upload-section {
  margin-bottom: 1.5rem;
}

.upload-button {
  display: inline-block;
  padding: 0.75rem 1.5rem;
  background: var(--color-success-500);
  color: var(--text-inverted);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.9rem;
  transition: background 0.2s;
}

.upload-button:hover {
  background: var(--color-success-600);
}

.video-list {
  margin-top: 1rem;
}

h3 {
  margin-top: 0;
  margin-bottom: 0.75rem;
  font-size: 1rem;
  font-weight: 600;
}

.loading,
.empty {
  padding: 1rem;
  text-align: center;
  color: var(--text-secondary);
}

.video-items {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.video-item {
  padding: 0.75rem;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  background: var(--bg-primary);
  cursor: pointer;
  text-align: left;
  transition: all 0.2s;
}

.video-item:hover:not(:disabled) {
  border-color: var(--color-success-500);
  background: var(--bg-secondary);
}

.video-item.active {
  border-color: var(--color-success-500);
  background: var(--color-success-100);
}

.video-item.loading {
  opacity: 0.7;
  cursor: wait;
}

.video-item:disabled {
  cursor: not-allowed;
}

.video-item .video-name {
  font-weight: 500;
  margin-bottom: 0.25rem;
}

.video-item .video-date {
  font-size: 0.85rem;
  color: var(--text-secondary);
}

.video-item .loading-indicator {
  font-size: 0.8rem;
  color: var(--color-success-500);
  margin-top: 0.25rem;
  font-style: italic;
}

.error {
  margin-top: 1rem;
  padding: 0.75rem;
  background: var(--color-error-100);
  color: var(--color-error-600);
  border-radius: 4px;
  border: 1px solid var(--color-error-200);
}

/* Clear All Data */
.clear-all-section {
  margin-top: 1.5rem;
  padding-top: 1.5rem;
  border-top: 1px solid var(--border-light);
}

.clear-all-button {
  width: 100%;
  padding: 0.625rem 1rem;
  background: transparent;
  color: var(--color-error-600);
  border: 1px solid var(--color-error-300);
  border-radius: 4px;
  cursor: pointer;
  font-size: 0.875rem;
  font-weight: 500;
  transition: all 0.2s;
}

.clear-all-button:hover:not(:disabled) {
  background: var(--color-error-100);
  border-color: var(--color-error-500);
}

.clear-all-button:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

/* Encoding Overlay */
.encoding-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: color-mix(in oklch, var(--color-neutral-900) 95%, transparent);
  backdrop-filter: blur(4px);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 2000;
  animation: fadeIn 0.3s ease-out;
}

.encoding-modal {
  background: var(--bg-primary);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  padding: 2.5rem;
  max-width: 500px;
  width: 90%;
  text-align: center;
  animation: slideUp 0.3s ease-out;
}

.encoding-spinner {
  display: flex;
  justify-content: center;
  margin-bottom: 1.5rem;
}

.spinner-icon {
  color: #f97316;
  animation: spin 2s linear infinite;
}

@keyframes spin {
  from {
    transform: rotate(0deg);
  }
  to {
    transform: rotate(360deg);
  }
}

.encoding-modal h2 {
  margin: 0 0 1rem 0;
  font-size: 1.5rem;
  font-weight: 600;
  color: var(--text-primary);
}

.encoding-message {
  margin: 0 0 1rem 0;
  font-size: 1rem;
  color: var(--text-secondary);
  line-height: 1.6;
}

.encoding-warning {
  margin: 0;
  font-size: 0.875rem;
  color: #f97316;
  font-weight: 500;
}

/* Success Modal */
.success-modal {
  background: var(--bg-primary);
  border-radius: 12px;
  box-shadow: var(--shadow-lg);
  padding: 2.5rem;
  max-width: 600px;
  width: 90%;
  text-align: center;
  animation: slideUp 0.3s ease-out;
}

.success-icon {
  display: flex;
  justify-content: center;
  margin-bottom: 1.5rem;
}

.success-icon svg {
  color: #10b981;
}

.success-modal h2 {
  margin: 0 0 2rem 0;
  font-size: 1.75rem;
  font-weight: 600;
  color: var(--text-primary);
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(2, 1fr);
  gap: 1.5rem;
  margin-bottom: 2rem;
  text-align: left;
}

.stat-item {
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 8px;
  border: 1px solid var(--border-light);
}

.stat-label {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
  font-family: 'SF Mono', 'Monaco', 'Courier New', monospace;
}

.stat-value.positive {
  color: #10b981;
}

.dismiss-button {
  width: 100%;
  padding: 0.875rem 2rem;
  background: var(--color-success-500);
  color: var(--text-inverted);
  border: none;
  border-radius: 6px;
  font-size: 1rem;
  font-weight: 600;
  cursor: pointer;
  transition: background 0.2s;
}

.dismiss-button:hover {
  background: var(--color-success-600);
}

/* Responsive */
@media (max-width: 640px) {
  .modal-container {
    width: 95%;
    max-height: 90vh;
  }

  .modal-header,
  .modal-content {
    padding: 1rem;
  }

  .encoding-modal,
  .success-modal {
    padding: 2rem 1.5rem;
  }

  .stats-grid {
    grid-template-columns: 1fr;
    gap: 1rem;
  }

  .success-modal h2 {
    font-size: 1.5rem;
  }
}
</style>


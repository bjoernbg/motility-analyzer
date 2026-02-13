<script setup lang="ts">
import { computed, ref, watch } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import { Slider } from './ui/slider';
import { ButtonGroup } from './ui/button-group';
import { Button } from './ui/button';
import { Icon } from './ui/icon';

const store = useAnalysisStore();

// Get current frame and total frames from store
// In combined mode, use synced frame and max synced frame
const currentFrame = computed(() => {
  if (store.isInCombinedMode) {
    return store.syncedFrame ?? 0;
  }
  return store.currentFrame ?? 0;
});

const totalFrames = computed(() => {
  if (store.isInCombinedMode) {
    // Use max synced frame (min of both videos)
    return store.maxSyncedFrame !== null ? store.maxSyncedFrame + 1 : 1;
  }
  const frames = store.currentVideo?.metadata?.total_frames;
  return frames && frames > 0 ? frames : 1; // Ensure at least 1 to avoid division by zero
});

const videoFps = computed(() => {
  if (store.isInCombinedMode && store.video1) {
    return store.video1.metadata?.fps ?? 30;
  }
  return store.currentVideo?.metadata?.fps ?? 30;
});

// Local state for timeline slider
const timelineValue = ref([0]);

// Sync timeline with current frame (but don't update during user drag)
const isDragging = ref(false);

// Watch currentFrame and update timeline (unless user is dragging)
watch(currentFrame, (newFrame) => {
  if (!isDragging.value && newFrame !== null && newFrame >= 0) {
    const clampedFrame = Math.max(0, Math.min(newFrame, totalFrames.value - 1));
    timelineValue.value = [clampedFrame];
  }
}, { immediate: true });

const emit = defineEmits<{
  seek: [frame: number];
}>();

// Handle timeline slider changes (only when not dragging)
function handleTimelineChange() {
  if (!isDragging.value && timelineValue.value.length > 0 && timelineValue.value[0] !== null && timelineValue.value[0] !== undefined) {
    const frame = Math.round(timelineValue.value[0]);
    const clampedFrame = Math.max(0, Math.min(frame, totalFrames.value - 1));
    if (clampedFrame !== currentFrame.value) {
      // In combined mode, use synced seek
      if (store.isInCombinedMode) {
        store.seekToSyncedFrame(clampedFrame);
      } else {
        emit('seek', clampedFrame);
      }
    }
  }
}

// Handle pointer down to start seeking
function handlePointerDown() {
  isDragging.value = true;
  store.setUserSeeking(true);
}

// Handle pointer up to finalize seek
function handlePointerUp() {
  isDragging.value = false;
  store.setUserSeeking(false);
  handleTimelineChange();
}

// Handle pointer cancel (e.g., pointer leaves while dragging)
function handlePointerCancel() {
  isDragging.value = false;
  store.setUserSeeking(false);
}

// Frame stepping functions
function stepFrame(delta: number) {
  const newFrame = Math.max(0, Math.min(totalFrames.value - 1, currentFrame.value + delta));
  // In combined mode, use synced seek
  if (store.isInCombinedMode) {
    store.seekToSyncedFrame(newFrame);
  } else {
    emit('seek', newFrame);
  }
}

function stepBack50() {
  stepFrame(-50);
}

function stepBack1() {
  stepFrame(-1);
}

function stepForward1() {
  stepFrame(1);
}

function stepForward50() {
  stepFrame(50);
}

// Progress text for analysis status
const progressText = computed(() => {
  if (store.progressStatus === 'pending') {
    return '— Analysis not started';
  }
  if (store.progressStatus === 'processing') {
    return `— Analysing... ${store.progress.toFixed(1)}%`;
  }
  if (store.progressStatus === 'completed') {
    return '— Analysis completed.';
  }
  if (store.progressStatus === 'failed') {
    return '— Analysis failed';
  }
  if (store.progressStatus === 'cancelled') {
    return '— Analysis cancelled';
  }
  return '';
});

// Show analysis progress only during analysis
const showAnalysisProgress = computed(() => store.isProcessing || store.progressStatus !== 'pending');

// Format time from frame number
function formatTime(frame: number): string {
  if (videoFps.value <= 0) return '0:00.00';
  const seconds = frame / videoFps.value;
  const minutes = Math.floor(seconds / 60);
  const secs = Math.floor(seconds % 60);
  const frameNum = Math.floor(frame % videoFps.value);
  if (minutes > 0) {
    return `${minutes}:${secs.toString().padStart(2, '0')}.${frameNum.toString().padStart(2, '0')}`;
  }
  return `${secs}.${frameNum.toString().padStart(2, '0')}`;
}

// Current time display
const currentTimeDisplay = computed(() => {
  if (currentFrame.value === null || totalFrames.value === 0) {
    return '0:00.00';
  }
  return formatTime(currentFrame.value);
});

const totalTimeDisplay = computed(() => {
  if (totalFrames.value === 0) {
    return '0:00.00';
  }
  return formatTime(totalFrames.value - 1);
});
</script>

<template>
  <div class="media-controller">

    <!-- Timeline container -->
    <div class="timeline-container">
      <!-- Timeline slider with integrated progress -->
      <div class="timeline-wrapper">
        <div class="time-display">
          <span class="current-time">{{ currentTimeDisplay }}</span>
          <span class="separator">/</span>
          <span class="total-time">{{ totalTimeDisplay }}</span>
          <span class="frame-info">(Frame {{ currentFrame }} / {{ totalFrames }})</span>
          <span v-if="showAnalysisProgress" class="frame-info">{{ progressText }}</span>
        </div>

        <div class="slider-container">
          <!-- Timeline slider -->
          <Slider v-model="timelineValue" :min="0" :max="Math.max(0, totalFrames - 1)" :step="1" class="timeline-slider"
            :disabled="!store.currentVideo || totalFrames <= 1" @pointerdown="handlePointerDown"
            @pointerup="handlePointerUp" @pointercancel="handlePointerCancel">
            <!-- Analysis progress overlay (only during analysis) -->
            <template #progress>
              <div v-if="showAnalysisProgress" class="progress-overlay" :class="{
                processing: store.isProcessing,
                completed: store.isCompleted,
                failed: store.progressStatus === 'failed',
                cancelled: store.progressStatus === 'cancelled',
              }" :style="{ '--progress': `${store.progress}%` }" />
            </template>
          </Slider>
        </div>
      </div>

      <!-- Frame stepping buttons -->
      <div class="frame-controls">

        <ButtonGroup>
          <Button @click="stepBack50" :disabled="!store.currentVideo || currentFrame <= 0" size="sm" variant="outline"
            title="Step back 50 frames">
            <Icon name="lucide:rewind" size="1.1em" />
            <span class="button-label">-50</span>
          </Button>
          <Button @click="stepBack1" :disabled="!store.currentVideo || currentFrame <= 0" size="sm" variant="outline"
            title="Step back 1 frame">
            <Icon name="lucide:step-back" size="1.1em" />
          </Button>
          <Button @click="stepForward1" :disabled="!store.currentVideo || currentFrame >= totalFrames - 1" size="sm"
            variant="outline" title="Step forward 1 frame">
            <Icon name="lucide:step-forward" size="1.1em" />
          </Button>
          <Button @click="stepForward50" :disabled="!store.currentVideo || currentFrame >= totalFrames - 1" size="sm"
            variant="outline" title="Step forward 50 frames">
            <span class="button-label">+50</span>
            <Icon name="lucide:fast-forward" size="1.1em" />
          </Button>
        </ButtonGroup>
      </div>
    </div>
  </div>
</template>

<style scoped>
.media-controller {
  padding: 1rem;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.analysis-status {
  padding: 0.5rem 0.75rem;
  background: var(--bg-secondary);
  border-radius: 4px;
  text-align: center;
}

.status-text {
  font-size: 0.9rem;
  color: var(--text-secondary);
  font-weight: 500;
}

.timeline-container {
  display: flex;
  flex-direction: column;
  gap: 0.75rem;
}

.frame-controls {
  display: flex;
  gap: 0.5rem;
  justify-content: center;
  align-items: center;
}

.button-label {
  margin-left: 0.25rem;
  font-size: 0.65rem;
}

.timeline-wrapper {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.time-display {
  display: flex;
  align-items: center;
  justify-content: center;
  gap: 0.5rem;
  font-size: 0.875rem;
  color: var(--text-primary);
}

.current-time {
  font-weight: 600;
}

.separator {
  color: var(--text-secondary);
}

.total-time {
  color: var(--text-secondary);
}

.frame-info {
  margin-left: 0.5rem;
  color: var(--text-secondary);
  font-size: 0.8rem;
}

.slider-container {
  position: relative;
  width: 100%;
  height: 24px;
  display: flex;
  align-items: center;
}

.progress-overlay {
  position: absolute;
  left: 1px;
  top: 50%;
  transform: translateY(-50%);
  height: 4px;
  background: var(--color-success-500);
  border-radius: 12px;
  pointer-events: none;
  z-index: 1;
  transition: width 0.5s ease;
  width: calc(var(--progress) - 2px);
}

.progress-overlay.processing {
  background: linear-gradient(90deg, var(--color-success-500), var(--color-success-600));
  animation: pulse 1.5s ease-in-out infinite;
}

.progress-overlay.completed {
  background: var(--color-success-500);
}

.progress-overlay.failed {
  background: var(--color-error-500);
}

.progress-overlay.cancelled {
  background: var(--color-warning-500);
}

@keyframes pulse {

  0%,
  100% {
    opacity: 1;
  }

  50% {
    opacity: 0.8;
  }
}

.timeline-slider {
  position: relative;
  z-index: 2;
  width: 100%;
}

/* Ensure slider thumb is above progress overlay */
.timeline-slider :deep([data-slot="slider-thumb"]) {
  z-index: 3;
}
</style>

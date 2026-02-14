<script setup lang="ts">
import { computed } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import ContractionDetectionControls from './ContractionDetectionControls.vue';
import ContractionEventsList from './ContractionEventsList.vue';

const store = useAnalysisStore();

// Computed statistics
const videoDuration = computed(() => {
  return store.currentVideo?.metadata?.duration ?? null;
});

const videoFrames = computed(() => {
  return store.currentVideo?.metadata?.total_frames ?? null;
});

const numTrackingPointPairs = computed(() => {
  return store.currentAnalysis?.parameters?.num_tracking_points ?? null;
});

const totalContractionEvents = computed(() => {
  return store.contractionEvents.length;
});

const videoFps = computed(() => {
  return store.currentVideo?.metadata?.fps ?? null;
});

// Calculate events per minute with deviations
const eventsPerMinuteWithDeviation = computed(() => {
  const duration = videoDuration.value;
  const fps = videoFps.value;
  const events = store.contractionEvents;
  
  if (duration === null || fps === null || events.length === 0 || duration <= 0) {
    return null;
  }
  
  // Calculate overall events per minute
  const durationMinutes = duration / 60;
  const overallEventsPerMinute = events.length / durationMinutes;
  
  // Calculate deviations by dividing video into 1-minute windows
  const windowSizeMinutes = 1.0;
  const numWindows = Math.max(1, Math.ceil(durationMinutes / windowSizeMinutes));
  const eventsPerWindow: number[] = [];
  
  // Initialize window counts
  for (let i = 0; i < numWindows; i++) {
    eventsPerWindow.push(0);
  }
  
  // Count events in each window based on their start time
  for (const event of events) {
    const [startFrame] = event.t_range_frames;
    const startTimeSeconds = startFrame / fps;
    const windowIndex = Math.min(
      Math.floor(startTimeSeconds / (windowSizeMinutes * 60)),
      numWindows - 1
    );
    if (eventsPerWindow[windowIndex] !== undefined) {
      eventsPerWindow[windowIndex]++;
    }
  }
  
  // Convert to events per minute for each window
  const eventsPerMinutePerWindow = eventsPerWindow.map(count => count / windowSizeMinutes);
  
  // Calculate mean and standard deviation from per-window rates
  const mean = eventsPerMinutePerWindow.reduce((sum, val) => sum + val, 0) / eventsPerMinutePerWindow.length;
  const variance = eventsPerMinutePerWindow.reduce((sum, val) => sum + Math.pow(val - mean, 2), 0) / eventsPerMinutePerWindow.length;
  const stdDev = Math.sqrt(variance);
  
  // Use overall rate as the mean (more accurate for short videos with few windows)
  // The overall rate is the true mean: total events / total time
  return {
    mean: overallEventsPerMinute,
    stdDev: stdDev,
  };
});

const hasResults = computed(() => {
  return store.currentAnalysis !== null;
});

</script>

<template>
  <div class="analysis-results">
    <div class="header">
      <h2>Analysis Results</h2>
    </div>
    
    <div v-if="!store.currentAnalysis" class="no-analysis">
      No analysis has been run yet.
    </div>
    
    <div v-else-if="store.isProcessing" class="processing">
      Analysis in progress... Results will appear here when complete.
    </div>
    
    <div v-else-if="store.progressStatus === 'failed'" class="failed">
      Analysis failed. Please try again.
    </div>
    
    <div v-else-if="store.progressStatus === 'cancelled'" class="cancelled">
      Analysis was cancelled.
    </div>
    
    <div v-else-if="!hasResults" class="no-results">
      No results available yet.
    </div>
    
    <div v-else class="results-content">
      <h3>Global Statistics</h3>
      <div class="stats-grid">
        <div v-if="videoDuration !== null || videoFrames !== null" class="stat-item">
          <div class="stat-label">Video Duration & Frames</div>
          <div class="stat-value">
            <span v-if="videoDuration !== null">{{ videoDuration.toFixed(2) }}s</span>
            <span v-if="videoDuration !== null && videoFrames !== null"> / </span>
            <span v-if="videoFrames !== null">{{ videoFrames }} frames</span>
          </div>
        </div>
        
        <div v-if="numTrackingPointPairs !== null" class="stat-item">
          <div class="stat-label">Number of Tracking Point Pairs</div>
          <div class="stat-value">{{ numTrackingPointPairs }}</div>
        </div>
        
        <div class="stat-item">
          <div class="stat-label">Total Number of Contraction Events</div>
          <div class="stat-value">{{ totalContractionEvents }}</div>
        </div>
        
        <div class="stat-item">
          <div class="stat-label">Contraction Events per Minute (incl. error bars)</div>
          <div class="stat-value">
            <span v-if="eventsPerMinuteWithDeviation !== null">
              {{ eventsPerMinuteWithDeviation.mean.toFixed(2) }} ± {{ eventsPerMinuteWithDeviation.stdDev.toFixed(2) }}
            </span>
            <span v-else>N/A</span>
          </div>
        </div>
      </div>
      
      <div v-if="store.currentAnalysis" class="frame-info">
        <h3>Frame Data</h3>
        <p>
          {{ store.currentAnalysis.processed_frames || store.liveFrameData.size || 0 }} frames analyzed.
          View overlays on the video player.
        </p>
      </div>

      <div v-if="store.currentAnalysis" class="contraction-detection-section">
        <ContractionDetectionControls />
        <div class="mt-4">
          <ContractionEventsList />
        </div>
      </div>
    </div>
  </div>
</template>

<style scoped>
.analysis-results {
  padding: 1rem;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
}

.header {
  display: flex;
  justify-content: space-between;
  align-items: center;
  margin-bottom: 1rem;
}

h2 {
  margin: 0;
}

h3 {
  margin-top: 1.5rem;
  margin-bottom: 0.75rem;
  font-size: 1rem;
  font-weight: 600;
}

.no-analysis,
.processing,
.failed,
.cancelled,
.no-results {
  padding: 1.5rem;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
}

.failed {
  color: var(--color-error-600);
  background: var(--color-error-100);
  border-radius: 4px;
}

.cancelled {
  color: var(--color-warning-600);
  background: var(--color-warning-100);
  border-radius: 4px;
}

.results-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.stats-grid {
  display: grid;
  grid-template-columns: repeat(auto-fit, minmax(200px, 1fr));
  gap: 1rem;
}

.stat-item {
  padding: 1rem;
  border: 1px solid var(--color-neutral-200);
  border-radius: 4px;
  background: var(--bg-secondary);
}

.stat-label {
  font-size: 0.85rem;
  color: var(--text-secondary);
  margin-bottom: 0.5rem;
  font-weight: 500;
}

.stat-value {
  font-size: 1.25rem;
  font-weight: 600;
  color: var(--text-primary);
}

.frame-info {
  padding: 1rem;
  background: var(--bg-secondary);
  border-radius: 4px;
}

.frame-info p {
  margin: 0;
  color: var(--text-secondary);
}

.contraction-detection-section {
  margin-top: 2rem;
}

</style>

<script setup lang="ts">
import { ref, reactive, watch, computed, onUnmounted } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import type { AnalysisParameters } from '../lib/api';
import { Slider } from './ui/slider';
import { debounce } from '../lib/utils';
import { Popover, PopoverTrigger, PopoverContent } from './ui/popover';
import { Icon } from './ui/icon';
import { RadioGroup, RadioGroupItem } from './ui/radio-group';
import { Button } from './ui/button';
import { Label } from './ui/label';

const store = useAnalysisStore();

// Edge detection method
const edgeDetectionMethod = ref<"costmap" | "signal_1d">("costmap");

// Costmap parameters (only used when edge_detection_method="costmap")
const alpha = ref(1.5);
const band = ref(20);
const thresholdPercentile = ref(80.0);

// Smoothing factor (used by both methods)
const smoothingFactor = ref(0.2);

// 1D Signal method parameters (only used when edge_detection_method="signal_1d")
const stripWidth = ref(5);
const bandHeight = ref(30);
const sigma = ref(2.0);

// Measurement configuration parameters
const numTrackingPoints = ref(30);
const distributionMethod = ref<"center_line_projection" | "x_axis_even">("center_line_projection");

const isRunning = ref(false);

// Computed properties to convert between number and array for Slider component
const alphaModel = computed({
  get: () => [alpha.value],
  set: (value: number[]) => { alpha.value = value[0] ?? 1.5; }
});

const bandModel = computed({
  get: () => [band.value],
  set: (value: number[]) => { band.value = value[0] ?? 20; }
});

const smoothingFactorModel = computed({
  get: () => [smoothingFactor.value],
  set: (value: number[]) => { smoothingFactor.value = value[0] ?? 0.2; }
});

const thresholdPercentileModel = computed({
  get: () => [thresholdPercentile.value],
  set: (value: number[]) => { thresholdPercentile.value = value[0] ?? 80.0; }
});

const numTrackingPointsModel = computed({
  get: () => [numTrackingPoints.value],
  set: (value: number[]) => { numTrackingPoints.value = value[0] ?? 30; }
});

const stripWidthModel = computed({
  get: () => [stripWidth.value],
  set: (value: number[]) => { stripWidth.value = value[0] ?? 5; }
});

const bandHeightModel = computed({
  get: () => [bandHeight.value],
  set: (value: number[]) => { bandHeight.value = value[0] ?? 30; }
});

const sigmaModel = computed({
  get: () => [sigma.value],
  set: (value: number[]) => { sigma.value = value[0] ?? 2.0; }
});

// Function to sync local refs with store parameters
function syncParamsFromStore() {
  const params = store.currentParameters;
  if (params) {
    edgeDetectionMethod.value = params.edge_detection_method ?? "costmap";
    alpha.value = params.alpha ?? 1.5;
    band.value = params.band ?? 20;
    smoothingFactor.value = params.smoothing_factor ?? 0.2;
    thresholdPercentile.value = params.threshold_percentile ?? 80.0;
    stripWidth.value = params.strip_width ?? 5;
    bandHeight.value = params.band_height ?? 30;
    sigma.value = params.sigma ?? 2.0;
    numTrackingPoints.value = params.num_tracking_points ?? 30;
    distributionMethod.value = params.distribution_method ?? "center_line_projection";
  } else {
    // Reset to defaults if no saved settings
    edgeDetectionMethod.value = "costmap";
    alpha.value = 1.5;
    band.value = 20;
    smoothingFactor.value = 0.2;
    thresholdPercentile.value = 80.0;
    stripWidth.value = 5;
    bandHeight.value = 30;
    sigma.value = 2.0;
    numTrackingPoints.value = 30;
    distributionMethod.value = "center_line_projection";
  }
}

// Watch for video changes
watch(() => store.currentVideo, () => {
  // Load parameters from store (which may have loaded saved settings)
  syncParamsFromStore();
}, { immediate: true });

// Watch for parameter changes (e.g., when settings are loaded asynchronously)
watch(() => store.currentParameters, () => {
  // Sync local refs when store parameters change (e.g., after settings are loaded)
  if (store.currentVideo) {
    syncParamsFromStore();
  }
}, { immediate: true });

// Debounced analysis function to avoid too many requests
const debouncedAnalyze = debounce(() => {
  if (store.currentVideo && !store.isProcessing && store.currentFrame !== null) {
    // Trigger single-frame analysis when parameters change
    store.analyzeCurrentFrame(getCurrentParameters());
  }
}, 500); // 500ms debounce delay

// Debounced function to save settings
const debouncedSaveSettings = debounce(async () => {
  if (store.currentVideo) {
    const params = getCurrentParameters();
    // Update store's current parameters
    store.currentParameters = params;
    // Save to file
    await store.saveCurrentSettings();
  }
}, 1000); // 1 second debounce for saving

// Watch for parameter changes and trigger debounced single-frame analysis and save
watch(
  [
    edgeDetectionMethod,
    alpha,
    band,
    smoothingFactor,
    thresholdPercentile,
    stripWidth,
    bandHeight,
    sigma,
    numTrackingPoints,
    distributionMethod,
  ],
  () => {
    debouncedAnalyze();
    debouncedSaveSettings();
  }
);

onUnmounted(() => {
  // Cleanup: cancel any pending debounced calls
  // The debounce function handles cleanup internally via setTimeout
});

function getCurrentParameters(): AnalysisParameters {
  // Get horizontal window values from store's current parameters if available
  const currentParams = store.currentParameters;
  return {
    edge_detection_method: edgeDetectionMethod.value,
    alpha: alpha.value,
    band: band.value,
    smoothing_factor: smoothingFactor.value,
    threshold_percentile: thresholdPercentile.value,
    strip_width: stripWidth.value,
    band_height: bandHeight.value,
    sigma: sigma.value,
    horizontal_window_x_left: currentParams?.horizontal_window_x_left ?? null,
    horizontal_window_x_right: currentParams?.horizontal_window_x_right ?? null,
    num_tracking_points: numTrackingPoints.value,
    distribution_method: distributionMethod.value,
  };
}

async function startAnalysis() {
  if (!store.currentVideo) {
    return;
  }

  // Proceed with starting analysis
  isRunning.value = true;
  try {
    await store.runAnalysis(getCurrentParameters());
  } catch (error) {
    console.error('Failed to start analysis:', error);
  } finally {
    isRunning.value = false;
  }
}

async function rerunAnalysis() {
  if (!store.currentAnalysis || !store.currentVideo) {
    return;
  }

  isRunning.value = true;
  try {
    // Start a new analysis with the same parameters as the current analysis
    const parameters = store.currentAnalysis.parameters as AnalysisParameters;
    await store.runAnalysis(parameters);
  } catch (error) {
    console.error('Failed to re-run analysis:', error);
  } finally {
    isRunning.value = false;
  }
}

function createNewAnalysis() {
  // Clear current analysis to allow creating a new one
  store.currentAnalysis = null;
}

function removeSelectedAnalysis() {
  if (!store.currentAnalysis) {
    return;
  }

  deletingAnalysisId.value = store.currentAnalysis.id;
  deletePopoverOpen[store.currentAnalysis.id] = true;
}

async function stopAnalysis() {
  try {
    await store.stopCurrentAnalysis();
  } catch (error) {
    console.error('Failed to stop analysis:', error);
  }
}

// Analysis selection functions
const sortedAnalyses = computed(() => {
  // Sort by created_at descending (newest first)
  return [...store.availableAnalyses].sort((a, b) =>
    new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
  );
});

const matchingAnalysis = computed(() => {
  if (!store.currentParameters) {
    return null;
  }
  return store.findMatchingAnalysis(getCurrentParameters());
});

// Helper function to compare parameters (same logic as store)
function parametersMatch(params1: Record<string, unknown>, params2: AnalysisParameters): boolean {
  const tolerance = 0.001;

  // Check if all keys match
  const keys1 = Object.keys(params1).filter(k => params1[k] !== undefined && params1[k] !== null);
  const keys2 = Object.keys(params2).filter(k => (params2 as Record<string, unknown>)[k] !== undefined && (params2 as Record<string, unknown>)[k] !== null);

  if (keys1.length !== keys2.length) {
    return false;
  }

  for (const key of keys1) {
    const val1 = params1[key];
    const val2 = (params2 as Record<string, unknown>)[key];

    // Handle None/null values
    if (val1 === null && val2 === null) continue;
    if (val1 === null || val2 === null) return false;

    // Compare floating-point numbers with tolerance
    if (typeof val1 === 'number' && typeof val2 === 'number') {
      if (Math.abs(val1 - val2) > tolerance) {
        return false;
      }
    } else if (val1 !== val2) {
      return false;
    }
  }

  return true;
}

function getProcessedFrames(analysis: { processed_frames?: number | null }): number { return analysis.processed_frames ?? 0; }
const totalFrames = computed(() => { return store.currentVideo?.metadata?.total_frames ?? 0; });

// Track which analysis is being confirmed for deletion
const deletingAnalysisId = ref<string | null>(null);
// Track open state for each analysis's delete popover using reactive object
const deletePopoverOpen = reactive<Record<string, boolean>>({});

function formatAnalysisDate(createdAt: string): string {
  const date = new Date(createdAt);
  const dateStr = date.toLocaleDateString();
  const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `${dateStr} ${timeStr}`;
}

async function handleAnalysisClick(analysisId: string, event?: Event) {
  // Prevent click if clicking on delete button or other interactive elements
  if (event && (event.target as HTMLElement).closest('button, [role="button"]')) {
    return;
  }

  if (analysisId && analysisId !== store.currentAnalysis?.id && !store.isProcessing) {
    // Select analysis directly - parameters will be auto-loaded
    await store.selectAnalysis(analysisId);
  }
}

function openDeleteConfirmation(analysisId: string, event: Event) {
  event.stopPropagation(); // Prevent triggering the row click
  deletePopoverOpen[analysisId] = true;
  deletingAnalysisId.value = analysisId;
}

function closeDeleteConfirmation() {
  if (deletingAnalysisId.value) {
    deletePopoverOpen[deletingAnalysisId.value] = false;
    deletingAnalysisId.value = null;
  }
}

async function confirmDeleteAnalysis() {
  if (!deletingAnalysisId.value) {
    return;
  }

  const analysisId = deletingAnalysisId.value;
  closeDeleteConfirmation(); // Close popover immediately

  try {
    await store.deleteAnalysisById(analysisId);
  } catch (error) {
    console.error('Failed to delete analysis:', error);
    // Re-open popover with error state or show error message
    // For now, just log the error
  }
}

// Helper to check if analysis can be re-run
const canRerunAnalysis = computed(() => {
  return store.currentAnalysis &&
    (store.currentAnalysis.status === 'completed' ||
      store.currentAnalysis.status === 'cancelled' ||
      store.currentAnalysis.status === 'failed');
});



</script>

<template>
  <div class="analysis-params">
    <div v-if="!store.currentVideo" class="no-video">
      Please select a video first.
    </div>

    <form v-else @submit.prevent="() => startAnalysis()" class="params-form">

      <h3 v-if="store.availableAnalyses.length > 0">Completed Analyses</h3>
      <div class="param-group">
        <label>
          Select Analysis
          <Popover>
            <PopoverTrigger class="float-right">
              <Icon name="mdi:information-outline" />
            </PopoverTrigger>
            <PopoverContent>
              <div>Switch between completed analyses for this video. The newest analysis is automatically selected when
                opening a video.</div>
            </PopoverContent>
          </Popover>
        </label>

        <div v-if="sortedAnalyses.length > 0" v-for="analysis in sortedAnalyses" :key="analysis.id"
          :class="['analysis-item', { 'analysis-item-active': analysis.id === store.currentAnalysis?.id }]"
          @click="handleAnalysisClick(analysis.id, $event)">
          <span :class="{
            'text-green-500': analysis.status === 'completed',
            'text-red-500': analysis.status === 'failed',
            'text-blue-500': analysis.status === 'processing',
            'text-yellow-500': analysis.status === 'pending' || analysis.status === 'cancelled'
          }">
            <Icon :size="16" class="mt-1" :name="analysis.status === 'completed'
              ? 'mdi:check-circle-outline'
              : analysis.status === 'failed'
                ? 'mdi:alert-circle-outline'
                : analysis.status === 'processing'
                  ? 'mdi:progress-clock'
                  : 'mdi:file-outline'" />
          </span>
          <div class="analysis-item-info">
            <p class="text-sm">{{ formatAnalysisDate(analysis.created_at) }}</p>
            <p class="text-xs frame-count" v-if="totalFrames > 0">
              {{ getProcessedFrames(analysis) }} / {{ totalFrames }} frames
            </p>
            <div class="analysis-params-info">
              <span class="text-xs param-tag">
                {{ (analysis.parameters.num_tracking_points as number) ?? 30 }} points
              </span>
              <span class="text-xs param-tag">
                {{ (analysis.parameters.distribution_method as string) === 'center_line_projection' ? 'Center Line' :
                  'X-Axis Even' }}
              </span>
              <span class="text-xs param-tag"
                v-if="analysis.parameters.horizontal_window_x_left != null && analysis.parameters.horizontal_window_x_right != null">
                {{ analysis.parameters.horizontal_window_x_left }} ↔︎ {{ analysis.parameters.horizontal_window_x_right
                }}
              </span>
            </div>
          </div>
        </div>
        <div v-else class="no-analyses">
          No analyses available for this video.
        </div>
        <div v-if="matchingAnalysis && store.currentAnalysis?.id !== matchingAnalysis.id"
          class="matching-analysis-hint">
          <Icon name="mdi:check-circle" class="match-icon" />
          Current parameters match an available analysis
        </div>
      </div>


      <!-- Selected Analysis Actions -->
      <div v-if="store.currentAnalysis" class="selected-analysis-actions">
        <div class="button-group">
          <Button v-if="store.isProcessing" type="button" variant="destructive" @click="stopAnalysis" :disabled="!store.isProcessing">
            Stop
          </Button>
          <template v-else>
            <Button v-if="canRerunAnalysis" type="button" variant="default" @click="rerunAnalysis"
              :disabled="isRunning || store.isProcessing">
              Re-run
            </Button>
            <Button type="button" variant="default" @click="createNewAnalysis"
              :disabled="isRunning || store.isProcessing">
              Create New Analysis
            </Button>
          </template>

          <Popover v-model:open="deletePopoverOpen[store.currentAnalysis.id]">
            <PopoverTrigger as-child>
              <Button type="button" variant="destructive" @click="removeSelectedAnalysis" :disabled="isRunning || store.isProcessing">
                <Icon name="mdi:delete" />
              </Button>
            </PopoverTrigger>
            <PopoverContent>
              <div class="delete-confirmation">
                <p class="confirmation-message">Are you sure you want to delete this analysis?</p>
                <p class="confirmation-warning">This action cannot be undone.</p>
                <div class="confirmation-buttons">
                  <Button type="button" variant="outline" size="sm" @click="closeDeleteConfirmation">Cancel</Button>
                  <Button type="button" variant="destructive" size="sm" @click="confirmDeleteAnalysis">Delete</Button>
                </div>
              </div>
            </PopoverContent>
          </Popover>
        </div>
      </div>

      <!-- Start/Stop buttons when no analysis selected -->
      <div v-else class="button-group">
        <button type="submit" class="start-button" :disabled="isRunning || store.isProcessing">
          <span v-if="isRunning || store.isProcessing">Running...</span>
          <span v-else>Start Analysis</span>
        </button>

        <button v-if="store.isProcessing" type="button" class="stop-button" @click="stopAnalysis"
          :disabled="!store.isProcessing">
          Stop
        </button>
      </div>

      <h3>Edge Detection</h3>

      <div class="param-group">
        <Label for="edge-detection-method">
          Edge Detection Method
          <Popover>
            <PopoverTrigger class="float-right">
              <Icon name="mdi:information-outline" />
            </PopoverTrigger>
            <PopoverContent>
              <div>
                <div><strong>Costmap:</strong> Original gradient-based method using costmap</div>
                <div><strong>1D Signal:</strong> Alternative method using 1D signal analysis with median collapse and edge center detection</div>
              </div>
            </PopoverContent>
          </Popover>
        </Label>
        <RadioGroup id="edge-detection-method" v-model="edgeDetectionMethod" :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null">
          <div class="radio-option">
            <RadioGroupItem value="costmap" id="costmap" />
            <Label for="costmap" class="radio-label">Costmap</Label>
          </div>
          <div class="radio-option">
            <RadioGroupItem value="signal_1d" id="signal-1d" />
            <Label for="signal-1d" class="radio-label">1D Signal</Label>
          </div>
        </RadioGroup>
      </div>

      <!-- Costmap method parameters -->
      <template v-if="edgeDetectionMethod === 'costmap'">
        <div class="param-group">
          <label for="alpha">
            Alpha: {{ alpha.toFixed(2) }}
            <Popover>
              <PopoverTrigger class="float-right">
                <Icon name="mdi:information-outline" />
              </PopoverTrigger>
              <PopoverContent>
                <div>Contrast enhancement factor (0.0 - 5.0)</div>
              </PopoverContent>
            </Popover>
          </label>
          <Slider v-model="alphaModel" :min="0" :max="5" :step="0.1" :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null" />
        </div>

        <div class="param-group">
          <label for="band">
            Band: {{ band }}
            <Popover>
              <PopoverTrigger class="float-right">
                <Icon name="mdi:information-outline" />
              </PopoverTrigger>
              <PopoverContent>
                <div>Search band width in pixels (1 - 100)</div>
              </PopoverContent>
            </Popover>
          </label>
          <Slider v-model="bandModel" :min="1" :max="100" :step="1" :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null" />
        </div>

        <div class="param-group">
          <label for="threshold-percentile">
            Threshold Percentile: {{ thresholdPercentile.toFixed(1) }}
            <Popover>
              <PopoverTrigger class="float-right">
                <Icon name="mdi:information-outline" />
              </PopoverTrigger>
              <PopoverContent>
                <div>Percentile threshold for brightest pixels (0.0 - 100.0)</div>
              </PopoverContent>
            </Popover>
          </label>
          <Slider v-model="thresholdPercentileModel" :min="0" :max="100" :step="0.1"
            :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null" />
        </div>
      </template>

      <!-- 1D Signal method parameters -->
      <template v-if="edgeDetectionMethod === 'signal_1d'">
        <div class="param-group">
          <label for="strip-width">
            Strip Width: {{ stripWidth }}
            <Popover>
              <PopoverTrigger class="float-right">
                <Icon name="mdi:information-outline" />
              </PopoverTrigger>
              <PopoverContent>
                <div>Width of horizontal strip for 1D signal collapse (1 - 20 pixels)</div>
              </PopoverContent>
            </Popover>
          </label>
          <Slider v-model="stripWidthModel" :min="1" :max="20" :step="1" :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null" />
        </div>

        <div class="param-group">
          <label for="band-height">
            Band Height: {{ bandHeight }}
            <Popover>
              <PopoverTrigger class="float-right">
                <Icon name="mdi:information-outline" />
              </PopoverTrigger>
              <PopoverContent>
                <div>Height of vertical band for 1D signal (10 - 100 pixels)</div>
              </PopoverContent>
            </Popover>
          </label>
          <Slider v-model="bandHeightModel" :min="10" :max="100" :step="1" :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null" />
        </div>

        <div class="param-group">
          <label for="sigma">
            Sigma: {{ sigma.toFixed(2) }}
            <Popover>
              <PopoverTrigger class="float-right">
                <Icon name="mdi:information-outline" />
              </PopoverTrigger>
              <PopoverContent>
                <div>Gaussian sigma parameter for smoothing (0.5 - 10.0)</div>
              </PopoverContent>
            </Popover>
          </label>
          <Slider v-model="sigmaModel" :min="0.5" :max="10" :step="0.1" :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null" />
        </div>
      </template>

      <!-- Smoothing factor (shared by both methods) -->
      <div class="param-group">
        <label for="smoothing-factor">
          Smoothing Factor: {{ smoothingFactor.toFixed(2) }}
          <Popover>
            <PopoverTrigger class="float-right">
              <Icon name="mdi:information-outline" />
            </PopoverTrigger>
            <PopoverContent>
              <div>Smoothing factor (0.0 - 1.0, higher = more smoothing)</div>
            </PopoverContent>
          </Popover>
        </label>
        <Slider v-model="smoothingFactorModel" :min="0" :max="1" :step="0.01"
          :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null" />
      </div>

      <h3>Measurement Configuration</h3>

      <div class="param-group">
        <label for="num-tracking-points">
          Number of Tracking Points: {{ numTrackingPoints }}
          <Popover>
            <PopoverTrigger class="float-right">
              <Icon name="mdi:information-outline" />
            </PopoverTrigger>
            <PopoverContent>
              <div>Number of points to track for measurement (5 - 200)</div>
            </PopoverContent>
          </Popover>
        </label>
        <Slider v-model="numTrackingPointsModel" :min="5" :max="200" :step="1"
          :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null" />
      </div>

      <div class="param-group">
        <Label for="distribution-method">
          Distribution Method
          <Popover>
            <PopoverTrigger class="float-right">
              <Icon name="mdi:information-outline" />
            </PopoverTrigger>
            <PopoverContent>
              <div>
                <div><strong>Center Line Projection:</strong> Distribute points evenly along the center line, projecting
                  to top and bottom paths</div>
                <div><strong>X-Axis Even Distribution:</strong> Distribute points evenly along the x-axis, using point
                  pairs at x positions</div>
              </div>
            </PopoverContent>
          </Popover>
        </Label>
        <RadioGroup id="distribution-method" v-model="distributionMethod" :disabled="isRunning || store.isProcessing || store.currentAnalysis !== null">
          <div class="radio-option">
            <RadioGroupItem value="center_line_projection" id="center-line-projection" />
            <Label for="center-line-projection" class="radio-label">Center Line Projection</Label>
          </div>
          <div class="radio-option">
            <RadioGroupItem value="x_axis_even" id="x-axis-even" />
            <Label for="x-axis-even" class="radio-label">X-Axis Even Distribution</Label>
          </div>
        </RadioGroup>
      </div>

    </form>
  </div>
</template>

<style scoped>
.analysis-params {
  padding: 1rem;
  border: 1px solid var(--border-light);
  border-radius: 8px;
  background: var(--bg-primary);
}


.no-video {
  padding: 1rem;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
}

.params-form {
  display: flex;
  flex-direction: column;
  gap: 1.2rem;
}

.param-group {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
}

.param-group label {
  font-weight: 500;
  font-size: 0.9rem;
  display: flex;
  align-items: center;
  justify-content: space-between;
}

h3:not(:first-child) {
  margin-top: 2rem;
}

.float-right {
  margin-left: auto;
  cursor: pointer;
  display: inline-flex;
  align-items: center;
}

.start-button {
  padding: 0.75rem 1.5rem;
  background: var(--color-success-500);
  color: var(--text-inverted);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 500;
  transition: background 0.2s;
}

.start-button:hover:not(:disabled) {
  background: var(--color-success-600);
}

.start-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.button-group {
  display: flex;
  flex-wrap: wrap;
  justify-content: start;
  gap: 0.5rem;
}
.button-group::after {
  content: "";
  border-top: 3px solid var(--border-light);
  margin-inline: -1rem;
  padding: 0;
  margin-top: .5rem;
  width: calc(100% + 2rem);
  height: 1px;
}
.button-group + h3,
.selected-analysis-actions + h3 {
  margin-top: 0;
}

.stop-button {
  padding: 0.75rem 1.5rem;
  background: var(--color-error-500);
  color: var(--text-inverted);
  border: none;
  border-radius: 4px;
  cursor: pointer;
  font-size: 1rem;
  font-weight: 500;
  transition: background 0.2s;
}

.stop-button:hover:not(:disabled) {
  background: var(--color-error-600);
}

.stop-button:disabled {
  opacity: 0.6;
  cursor: not-allowed;
}

.section-divider {
  margin-top: 1rem;
  margin-bottom: 0.5rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-light);
}


.param-group input[type="number"] {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  font-size: 0.9rem;
  background: var(--bg-primary);
  color: var(--text-primary);
}

.param-group input[type="number"]:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.param-group input[type="checkbox"] {
  margin-right: 0.5rem;
  cursor: pointer;
}

.param-group input[type="checkbox"]:disabled {
  cursor: not-allowed;
}

.button-group-inline {
  display: flex;
  gap: 0.5rem;
}

.radio-option {
  display: flex;
  align-items: center;
  gap: 0.5rem;
  cursor: pointer;
  padding: 0.25rem;
  border-radius: 4px;
  transition: background 0.2s;
}

.radio-option:hover:not(:has([data-slot="radio-group-item"][disabled])) {
  background: var(--bg-secondary);
}

.radio-label {
  cursor: pointer;
  user-select: none;
  margin: 0;
}

.analysis-selection {
  margin-top: 1rem;
  padding-top: 1rem;
  border-top: 1px solid var(--border-light);
}

.analysis-select {
  width: 100%;
  padding: 0.5rem;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  font-size: 0.9rem;
  background: var(--bg-primary);
  color: var(--text-primary);
  cursor: pointer;
}

.analysis-select:disabled {
  opacity: 0.5;
  cursor: not-allowed;
}

.matching-analysis-hint {
  margin-top: 0.5rem;
  padding: 0.5rem;
  background: var(--color-success-50);
  border: 1px solid var(--color-success-200);
  border-radius: 4px;
  color: var(--color-success-700);
  font-size: 0.875rem;
  display: flex;
  align-items: center;
  gap: 0.5rem;
}

.match-icon {
  color: var(--color-success-600);
}

.analyses-list {
  display: flex;
  flex-direction: column;
  gap: 0.5rem;
  margin-top: 0.5rem;
}

.analysis-item {
  text-align: left;
  cursor: pointer;
  transition: all 0.2s;
  display: grid;
  grid-template-columns: min-content 1fr;
  align-items: start;
  gap: 0.5rem;
  padding: 0.5rem;
  border-bottom: 1px solid var(--border-light);
  border-top: 1px solid transparent;
  border-left: 3px solid transparent;
  border-right: 1px solid transparent;
  margin-inline: calc(-.5rem - 3px) calc(-.5rem - 1px);
  margin-bottom: -1px;
  border-radius: 4px;
}

.analysis-item-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.frame-count {
  color: var(--text-secondary);
  font-size: 0.75rem;
}

.analysis-params-info {
  display: flex;
  flex-wrap: wrap;
  gap: 0.125rem;
  margin-top: 0.25rem;
}

.param-tag {
  display: inline-block;
  padding: 0.125rem 0.25rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 3px;
  color: var(--text-secondary);
  font-size: 0.7rem;
}

.analysis-item:hover:not(.analysis-item-disabled) {
  background: var(--bg-secondary);
}


.analysis-item-active {
  background: var(--color-primary-50);
  border-left: 3px solid var(--color-primary-500);
  border-color: var(--color-primary-200);
  font-weight: 500;
}

.analysis-item:hover:not(.analysis-item-disabled) {
  background: var(--color-primary-100);
}


.no-analyses {
  padding: 1rem;
  text-align: center;
  color: var(--text-secondary);
  font-style: italic;
  margin-top: 0.5rem;
}

.match-badge {
  display: inline-flex;
  align-items: center;
  gap: 0.25rem;
  margin-left: 0.5rem;
  color: var(--color-success-600);
  font-size: 0.875rem;
}

.status-icon-completed {
  color: var(--color-success-600);
}

.status-icon-failed {
  color: var(--color-error-600);
}

.status-icon-processing {
  color: var(--color-warning-600);
}

.status-icon-pending {
  color: var(--text-secondary);
}

.modal-overlay {
  position: fixed;
  top: 0;
  left: 0;
  right: 0;
  bottom: 0;
  background: rgba(0, 0, 0, 0.5);
  display: flex;
  align-items: center;
  justify-content: center;
  z-index: 1000;
}

.modal-container {
  background: var(--bg-primary);
  border-radius: 8px;
  padding: 0;
  min-width: 400px;
  max-width: 90vw;
  box-shadow: 0 4px 6px rgba(0, 0, 0, 0.1);
}

.modal-header {
  padding: 1rem 1.5rem;
  border-bottom: 1px solid var(--border-light);
}

.modal-header h3 {
  margin: 0;
  font-size: 1.125rem;
  font-weight: 600;
}

.modal-content {
  padding: 1.5rem;
}

.modal-content p {
  margin: 0;
  color: var(--text-primary);
}

.modal-footer {
  padding: 1rem 1.5rem;
  border-top: 1px solid var(--border-light);
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
}

.delete-confirmation {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}

.confirmation-message {
  font-weight: 500;
  margin: 0;
}

.confirmation-warning {
  font-size: 0.875rem;
  color: var(--text-secondary);
  margin: 0;
}

.confirmation-buttons {
  display: flex;
  gap: 0.5rem;
  justify-content: flex-end;
  margin-top: 0.5rem;
}
</style>

<script setup lang="ts">
import { ref, reactive, watch, computed, onUnmounted } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import type { AnalysisParameters, Analysis, MultiViewSession } from '../lib/api';
import { Slider } from './ui/slider';
import { debounce } from '../lib/utils';
import { Popover, PopoverTrigger, PopoverContent } from './ui/popover';
import { Icon } from './ui/icon';
import { RadioGroup, RadioGroupItem } from './ui/radio-group';
import { Button } from './ui/button';
import { Label } from './ui/label';

const store = useAnalysisStore();

// Smoothing factor
const smoothingFactor = ref(0.2);

// Silhouette method parameters
const silhouetteBlurKsize = ref(7);
const silhouetteBlurSigma = ref(1.6);
const silhouetteCloseK = ref(5);
const silhouetteXStep = ref(7);
const silhouetteBand = ref(60);
const silhouetteMedianK = ref(3);

// Measurement configuration parameters
const trackingPointPresets = [30, 50, 80, 120, 200] as const;
const numTrackingPoints = ref<30 | 50 | 80 | 120 | 200>(30);
const distributionMethod = ref<"center_line_projection" | "x_axis_even">("center_line_projection");

const isRunning = ref(false);

// Computed properties to convert between number and array for Slider component
const smoothingFactorModel = computed({
  get: () => [smoothingFactor.value],
  set: (value: number[]) => { smoothingFactor.value = value[0] ?? 0.2; }
});

const silhouetteBlurKsizeModel = computed({
  get: () => [silhouetteBlurKsize.value],
  set: (value: number[]) => { silhouetteBlurKsize.value = value[0] ?? 7; }
});

const silhouetteBlurSigmaModel = computed({
  get: () => [silhouetteBlurSigma.value],
  set: (value: number[]) => { silhouetteBlurSigma.value = value[0] ?? 1.6; }
});

const silhouetteCloseKModel = computed({
  get: () => [silhouetteCloseK.value],
  set: (value: number[]) => { silhouetteCloseK.value = value[0] ?? 5; }
});

const silhouetteXStepModel = computed({
  get: () => [silhouetteXStep.value],
  set: (value: number[]) => { silhouetteXStep.value = value[0] ?? 7; }
});

const silhouetteBandModel = computed({
  get: () => [silhouetteBand.value],
  set: (value: number[]) => { silhouetteBand.value = value[0] ?? 60; }
});

const silhouetteMedianKModel = computed({
  get: () => [silhouetteMedianK.value],
  set: (value: number[]) => { silhouetteMedianK.value = value[0] ?? 3; }
});

// Function to sync local refs with store parameters
function syncParamsFromStore() {
  const params = store.currentParameters;
  if (params) {
    smoothingFactor.value = params.smoothing_factor ?? 0.2;
    // Migration logic for blur kernel: if x and y differ, take max
    silhouetteBlurKsize.value = Math.max(
      params.silhouette_blur_ksize_x ?? 7,
      params.silhouette_blur_ksize_y ?? 7
    );
    silhouetteBlurSigma.value = params.silhouette_blur_sigma ?? 1.6;
    silhouetteCloseK.value = params.silhouette_close_k ?? 5;
    silhouetteXStep.value = params.silhouette_x_step ?? 7;
    silhouetteBand.value = params.silhouette_band ?? 60;
    silhouetteMedianK.value = params.silhouette_median_k ?? 3;
    // Snap to nearest valid preset for num_tracking_points
    const raw = params.num_tracking_points ?? 30;
    const closest = trackingPointPresets.reduce((prev, curr) =>
      Math.abs(curr - raw) < Math.abs(prev - raw) ? curr : prev
    );
    numTrackingPoints.value = closest;
    distributionMethod.value = params.distribution_method ?? "center_line_projection";
  } else {
    // Reset to defaults if no saved settings
    smoothingFactor.value = 0.2;
    silhouetteBlurKsize.value = 7;
    silhouetteBlurSigma.value = 1.6;
    silhouetteCloseK.value = 5;
    silhouetteXStep.value = 7;
    silhouetteBand.value = 60;
    silhouetteMedianK.value = 3;
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
    smoothingFactor,
    silhouetteBlurKsize,
    silhouetteBlurSigma,
    silhouetteCloseK,
    silhouetteXStep,
    silhouetteBand,
    silhouetteMedianK,
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
    smoothing_factor: smoothingFactor.value,
    silhouette_blur_ksize_x: silhouetteBlurKsize.value,
    silhouette_blur_ksize_y: silhouetteBlurKsize.value,
    silhouette_blur_sigma: silhouetteBlurSigma.value,
    silhouette_close_k: silhouetteCloseK.value,
    silhouette_x_step: silhouetteXStep.value,
    silhouette_band: silhouetteBand.value,
    silhouette_median_k: silhouetteMedianK.value,
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

const relatedSessionsByAnalysisId = computed<Record<string, MultiViewSession[]>>(() => {
  const index: Record<string, MultiViewSession[]> = {};
  for (const session of store.multiViewSessions) {
    const ids = [session.left_analysis_id, session.right_analysis_id];
    for (const analysisId of ids) {
      if (!index[analysisId]) {
        index[analysisId] = [];
      }
      index[analysisId].push(session);
    }
  }

  for (const analysisId of Object.keys(index)) {
    const sessions = index[analysisId];
    if (sessions) {
      sessions.sort(
        (a, b) => new Date(b.created_at).getTime() - new Date(a.created_at).getTime()
      );
    }
  }

  return index;
});

const currentAnalysisRelatedSessions = computed<MultiViewSession[]>(() => {
  if (!store.currentAnalysis) {
    return [];
  }
  return relatedSessionsByAnalysisId.value[store.currentAnalysis.id] ?? [];
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
const renamingAnalysisId = ref<string | null>(null);
const analysisNameDraft = ref('');
const isSavingAnalysisName = ref(false);

function formatAnalysisDate(createdAt: string): string {
  const date = new Date(createdAt);
  const dateStr = date.toLocaleDateString();
  const timeStr = date.toLocaleTimeString([], { hour: '2-digit', minute: '2-digit' });
  return `${dateStr} ${timeStr}`;
}

async function handleAnalysisClick(analysisId: string, event?: Event) {
  // Prevent click if clicking on delete button or other interactive elements
  if (event && (event.target as HTMLElement).closest('button, [role="button"], input, textarea')) {
    return;
  }

  if (analysisId && analysisId !== store.currentAnalysis?.id && !store.isProcessing) {
    // Select analysis directly - parameters will be auto-loaded
    await store.selectAnalysis(analysisId);
  }
}

function getAnalysisPrimaryName(analysis: Analysis): string {
  const customName = analysis.display_name?.trim();
  if (customName && customName.length > 0) {
    return customName;
  }
  return formatAnalysisDate(analysis.created_at);
}

function hasCustomAnalysisName(analysis: Analysis): boolean {
  const customName = analysis.display_name?.trim();
  return Boolean(customName && customName.length > 0);
}

function getCombinedSessionCount(analysisId: string): number {
  return (relatedSessionsByAnalysisId.value[analysisId] ?? []).length;
}

function getCombinedBadgeLabel(analysisId: string): string {
  const count = getCombinedSessionCount(analysisId);
  return count > 1 ? `Combined x${count}` : 'Combined';
}

async function openCombinedSession(sessionId: string, event?: Event): Promise<void> {
  event?.stopPropagation();
  try {
    await store.selectCombinedEntity(sessionId);
  } catch (error) {
    console.error('Failed to open combined analysis session:', error);
  }
}

function startRenameAnalysis(analysis: Analysis, event: Event) {
  event.stopPropagation();
  renamingAnalysisId.value = analysis.id;
  analysisNameDraft.value = analysis.display_name?.trim() ?? '';
}

function cancelRenameAnalysis(event?: Event) {
  event?.stopPropagation();
  renamingAnalysisId.value = null;
  analysisNameDraft.value = '';
}

async function saveRenameAnalysis(analysisId: string, event?: Event) {
  event?.stopPropagation();
  if (isSavingAnalysisName.value) {
    return;
  }

  try {
    isSavingAnalysisName.value = true;
    const trimmed = analysisNameDraft.value.trim();
    await store.renameAnalysis(analysisId, trimmed.length > 0 ? trimmed : null);
    cancelRenameAnalysis();
  } catch (error) {
    console.error('Failed to rename analysis:', error);
  } finally {
    isSavingAnalysisName.value = false;
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
            <div v-if="renamingAnalysisId === analysis.id" class="analysis-rename-row">
              <input
                v-model="analysisNameDraft"
                class="analysis-rename-input"
                type="text"
                maxlength="200"
                placeholder="Display name (empty to reset)"
                @click.stop
                @keyup.enter="saveRenameAnalysis(analysis.id, $event)"
                @keyup.escape="cancelRenameAnalysis($event)"
              />
              <Button type="button" variant="outline" size="sm" @click="saveRenameAnalysis(analysis.id, $event)"
                :disabled="isSavingAnalysisName">
                Save
              </Button>
              <Button type="button" variant="outline" size="sm" @click="cancelRenameAnalysis($event)"
                :disabled="isSavingAnalysisName">
                Cancel
              </Button>
            </div>
            <template v-else>
              <div class="analysis-name-row">
                <p class="analysis-name">{{ getAnalysisPrimaryName(analysis) }}</p>
                <span
                  v-if="getCombinedSessionCount(analysis.id) > 0"
                  class="combined-badge"
                >
                  {{ getCombinedBadgeLabel(analysis.id) }}
                </span>
              </div>
              <p class="text-sm" v-if="hasCustomAnalysisName(analysis)">{{ formatAnalysisDate(analysis.created_at) }}</p>
            </template>
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

          <Button v-if="renamingAnalysisId !== analysis.id" type="button" variant="ghost" size="sm"
            class="analysis-rename-button" @click="startRenameAnalysis(analysis, $event)"
            :disabled="isRunning || store.isProcessing">
            <Icon name="mdi:pencil" :size="16" />
          </Button>

          <!-- Delete button - only visible on hover -->
          <Popover v-model:open="deletePopoverOpen[analysis.id]">
            <PopoverTrigger as-child>
              <Button type="button" variant="ghost" size="sm" class="analysis-delete-button"
                @click="openDeleteConfirmation(analysis.id, $event)"
                :disabled="isRunning || store.isProcessing">
                <Icon name="mdi:delete" :size="16" />
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
        <div v-else class="no-analyses">
          No analyses available for this video.
        </div>
        <div v-if="matchingAnalysis && store.currentAnalysis?.id !== matchingAnalysis.id"
          class="matching-analysis-hint">
          <Icon name="mdi:check-circle" class="match-icon" />
          Current parameters match an available analysis
        </div>
        <div
          v-if="store.currentAnalysis && currentAnalysisRelatedSessions.length > 0"
          class="combined-analysis-hint"
        >
          <p class="combined-analysis-hint-title">Part of combined analysis</p>
          <p class="combined-analysis-hint-copy">Open related combined sessions:</p>
          <div class="combined-analysis-session-list">
            <button
              v-for="session in currentAnalysisRelatedSessions"
              :key="session.id"
              type="button"
              class="combined-session-chip"
              @click="openCombinedSession(session.id, $event)"
            >
              {{ session.name }}
            </button>
          </div>
        </div>
      </div>

      <!-- Start/Stop buttons -->
      <div class="button-group">
        <button type="submit" class="start-button" :disabled="isRunning || store.isProcessing">
          <span v-if="isRunning || store.isProcessing">Running...</span>
          <span v-else>Start Analysis</span>
        </button>

        <button v-if="store.isProcessing" type="button" class="stop-button" @click="stopAnalysis"
          :disabled="!store.isProcessing">
          Stop
        </button>
      </div>

      <h3>Measurement Configuration</h3>

      <div class="param-group">
        <label for="num-tracking-points">
          Tracking Points: {{ numTrackingPoints }}
          <Popover>
            <PopoverTrigger class="float-right">
              <Icon name="mdi:information-outline" />
            </PopoverTrigger>
            <PopoverContent>
              <div>Number of points to track for measurement along the detected edge</div>
            </PopoverContent>
          </Popover>
        </label>
        <div class="tracking-points-presets">
          <Button
            v-for="preset in trackingPointPresets"
            :key="preset"
            type="button"
            :variant="numTrackingPoints === preset ? 'default' : 'outline'"
            size="sm"
            :disabled="isRunning || store.isProcessing"
            @click="numTrackingPoints = preset"
          >
            {{ preset }}
          </Button>
        </div>
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
        <RadioGroup id="distribution-method" v-model="distributionMethod"
          :disabled="isRunning || store.isProcessing">
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

      <details class="advanced-settings">
        <summary>
          <span>Advanced Settings</span>
          <Icon name="mdi:chevron-down" class="chevron-icon" />
        </summary>
        <div class="advanced-content">
            <div class="param-group">
              <label for="silhouette-blur-ksize">
                Blur Kernel Size: {{ silhouetteBlurKsize }}
                <Popover>
                  <PopoverTrigger class="float-right">
                    <Icon name="mdi:information-outline" />
                  </PopoverTrigger>
                  <PopoverContent>
                    <div>Gaussian blur kernel size for both width and height (1 - 50)</div>
                  </PopoverContent>
                </Popover>
              </label>
              <Slider v-model="silhouetteBlurKsizeModel" :min="1" :max="50" :step="1"
                :disabled="isRunning || store.isProcessing" />
            </div>

            <div class="param-group">
              <label for="silhouette-blur-sigma">
                Blur Sigma: {{ silhouetteBlurSigma.toFixed(2) }}
                <Popover>
                  <PopoverTrigger class="float-right">
                    <Icon name="mdi:information-outline" />
                  </PopoverTrigger>
                  <PopoverContent>
                    <div>Gaussian blur sigma (0.1 - 10.0)</div>
                  </PopoverContent>
                </Popover>
              </label>
              <Slider v-model="silhouetteBlurSigmaModel" :min="0.1" :max="10" :step="0.1"
                :disabled="isRunning || store.isProcessing" />
            </div>

            <div class="param-group">
              <label for="silhouette-close-k">
                Morph Kernel Size: {{ silhouetteCloseK }}
                <Popover>
                  <PopoverTrigger class="float-right">
                    <Icon name="mdi:information-outline" />
                  </PopoverTrigger>
                  <PopoverContent>
                    <div>Morphology kernel size for close/open operations (1 - 50)</div>
                  </PopoverContent>
                </Popover>
              </label>
              <Slider v-model="silhouetteCloseKModel" :min="1" :max="50" :step="1"
                :disabled="isRunning || store.isProcessing" />
            </div>

            <div class="param-group">
              <label for="silhouette-x-step">
                X Step: {{ silhouetteXStep }}
                <Popover>
                  <PopoverTrigger class="float-right">
                    <Icon name="mdi:information-outline" />
                  </PopoverTrigger>
                  <PopoverContent>
                    <div>Step size for x-coordinate sampling (1 - 20)</div>
                  </PopoverContent>
                </Popover>
              </label>
              <Slider v-model="silhouetteXStepModel" :min="1" :max="20" :step="1"
                :disabled="isRunning || store.isProcessing" />
            </div>

            <div class="param-group">
              <label for="silhouette-band">
                Vertical Band: {{ silhouetteBand }}
                <Popover>
                  <PopoverTrigger class="float-right">
                    <Icon name="mdi:information-outline" />
                  </PopoverTrigger>
                  <PopoverContent>
                    <div>Vertical band width around previous paths (1 - 200)</div>
                  </PopoverContent>
                </Popover>
              </label>
              <Slider v-model="silhouetteBandModel" :min="1" :max="200" :step="1"
                :disabled="isRunning || store.isProcessing" />
            </div>

            <div class="param-group">
              <label for="silhouette-median-k">
                Median Filter Size: {{ silhouetteMedianK }}
                <Popover>
                  <PopoverTrigger class="float-right">
                    <Icon name="mdi:information-outline" />
                  </PopoverTrigger>
                  <PopoverContent>
                    <div>Median filter kernel size for 1D smoothing (must be odd, 3 - 101)</div>
                  </PopoverContent>
                </Popover>
              </label>
              <Slider v-model="silhouetteMedianKModel" :min="3" :max="101" :step="2"
                :disabled="isRunning || store.isProcessing" />
            </div>

          <!-- Smoothing factor -->
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
              :disabled="isRunning || store.isProcessing" />
          </div>

        </div>
      </details>

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

.button-group+h3 {
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

.combined-analysis-hint {
  margin-top: 0.5rem;
  padding: 0.6rem;
  background: var(--bg-secondary);
  border: 1px solid var(--border-light);
  border-radius: 4px;
}

.combined-analysis-hint-title {
  margin: 0;
  font-size: 0.8rem;
  font-weight: 600;
  color: var(--text-primary);
}

.combined-analysis-hint-copy {
  margin: 0.2rem 0 0;
  font-size: 0.75rem;
  color: var(--text-secondary);
}

.combined-analysis-session-list {
  display: flex;
  flex-wrap: wrap;
  gap: 0.35rem;
  margin-top: 0.5rem;
}

.combined-session-chip {
  border: 1px solid var(--border-light);
  border-radius: 999px;
  background: var(--bg-primary);
  color: var(--text-primary);
  font-size: 0.75rem;
  padding: 0.2rem 0.55rem;
  cursor: pointer;
}

.combined-session-chip:hover {
  background: var(--bg-secondary);
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
  position: relative;
}

.analysis-item-info {
  display: flex;
  flex-direction: column;
  gap: 0.25rem;
}

.analysis-name-row {
  display: flex;
  align-items: center;
  gap: 0.4rem;
  padding-right: 5.5rem;
}

.analysis-name {
  font-size: 0.9rem;
  font-weight: 600;
  line-height: 1.2;
  margin: 0;
  padding-right: 0;
}

.combined-badge {
  display: inline-flex;
  align-items: center;
  border: 1px solid var(--border-light);
  background: var(--bg-secondary);
  color: var(--text-secondary);
  border-radius: 999px;
  font-size: 0.65rem;
  font-weight: 600;
  line-height: 1;
  padding: 0.2rem 0.4rem;
  white-space: nowrap;
}

.analysis-rename-row {
  display: flex;
  align-items: center;
  gap: 0.35rem;
  flex-wrap: wrap;
  padding-right: 5.5rem;
}

.analysis-rename-input {
  min-width: 200px;
  flex: 1;
  border: 1px solid var(--border-light);
  border-radius: 4px;
  padding: 0.3rem 0.45rem;
  font-size: 0.8rem;
  background: var(--bg-primary);
  color: var(--text-primary);
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

.analysis-delete-button {
  position: absolute;
  top: 0.5rem;
  right: 0.5rem;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
}

.analysis-rename-button {
  position: absolute;
  top: 0.5rem;
  right: 2.75rem;
  opacity: 0;
  transition: opacity 0.2s;
  pointer-events: none;
  background: var(--bg-primary);
  border: 1px solid var(--border-light);
}

.analysis-rename-button:hover {
  background: var(--bg-secondary);
  border-color: var(--color-primary-300);
}

.analysis-delete-button:hover {
  background: var(--color-error-50);
  color: var(--color-error-600);
  border-color: var(--color-error-300);
}

.analysis-item:hover .analysis-delete-button {
  opacity: 1;
  pointer-events: auto;
}

.analysis-item:hover .analysis-rename-button {
  opacity: 1;
  pointer-events: auto;
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

/* Advanced settings collapsible section */
.advanced-settings {
  /* margin-top: 1rem; */
  /* border: 1px solid var(--border-light); */
  /* border-radius: 6px; */
  padding-inline: 0.75rem;
  /* background: rgba(0, 0, 0, 0.02); */
}

.advanced-settings summary {
  display: flex;
  align-items: center;
  justify-content: space-between;
  font-size: 0.9rem;
  user-select: none;
  cursor: pointer;
  padding: .25rem 0.5rem;
  margin: -.25rem -0.5rem;
  transition: background 0.2s;
  border-radius: 4px;
  list-style: none;
}

.advanced-settings summary::-webkit-details-marker {
  display: none;
}

.advanced-settings summary:hover {
  background: rgba(0, 0, 0, 0.03);
}

.advanced-settings[open] summary {
  margin-bottom: 1rem;
  padding-bottom: 0.75rem;
  border-bottom: 1px solid var(--border-light);
}

.advanced-settings[open] summary .chevron-icon {
  transform: rotate(180deg);
}

.advanced-settings summary .chevron-icon {
  transition: transform 0.2s;
}

.tracking-points-presets {
  display: flex;
  gap: 0.375rem;
}

.tracking-points-presets > * {
  flex: 1;
}

.advanced-content {
  display: flex;
  flex-direction: column;
  gap: 1rem;
}
</style>

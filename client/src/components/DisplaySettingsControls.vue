<template>
  <div class="w-64 max-w-[90vw] space-y-3">
    <div class="flex items-center justify-between">
      <h3 class="font-semibold text-sm">Measurement Settings</h3>
      <Button @click="loadSuggestions" :disabled="isLoadingSuggestions" size="sm" variant="ghost">
        <Icon name="lucide-sparkles" class="w-3 h-3" />
      </Button>
    </div>

    <div v-if="error" class="text-xs text-red-600 bg-red-50 p-2 rounded">
      {{ error }}
    </div>

    <div v-if="saveSuccess" class="text-xs text-green-600 bg-green-50 p-2 rounded">
      Saved!
    </div>

    <!-- Pixel to MM Factor -->
    <div class="space-y-1">
      <Label for="pixel-to-mm-factor" class="text-xs">Pixel/MM Factor</Label>
      <div class="flex items-center gap-1">
        <input
          id="pixel-to-mm-factor"
          v-model.number="localSettings.pixel_to_mm_factor"
          type="number"
          step="0.1"
          min="0.1"
          class="flex-1 min-w-0 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <Button
          @click="runCalibration"
          :disabled="isCalibrating"
          size="sm"
          variant="outline"
          title="Auto-detect from tube"
        >
          {{ isCalibrating ? '...' : 'Calibrate' }}
        </Button>
      </div>
      <div v-if="calibrationInfo" class="text-xs text-gray-500">
        Tube: {{ calibrationInfo }} px
      </div>
    </div>

    <!-- Color Scale -->
    <div class="space-y-1">
      <Label class="text-xs">Color Scale (mm)</Label>
      <div class="flex items-center gap-1">
        <input
          v-model.number="localSettings.heatmap_min_mm"
          type="number"
          step="0.1"
          min="0"
          class="shrink min-w-0 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
        <span class="text-xs text-gray-500">–</span>
        <input
          v-model.number="localSettings.heatmap_max_mm"
          type="number"
          step="0.1"
          min="0"
          class="shrink min-w-0 px-2 py-1 text-sm border border-gray-300 rounded focus:outline-none focus:ring-1 focus:ring-blue-500"
        />
      </div>
    </div>

    <!-- Data Stats (compact) -->
    <div v-if="suggestions" class="bg-gray-50 p-2 rounded text-xs space-y-1">
      <div class="flex justify-between">
        <span class="text-gray-600">Data range:</span>
        <span class="font-mono">{{ suggestions.data_min_mm.toFixed(1) }}–{{ suggestions.data_max_mm.toFixed(1) }}</span>
      </div>
      <div class="flex justify-between">
        <span class="text-gray-600">Suggested:</span>
        <span class="font-mono">{{ suggestions.heatmap_min_mm }}–{{ suggestions.heatmap_max_mm }}</span>
      </div>
      <Button @click="applySuggestions" size="sm" variant="outline" class="w-full mt-1">
        Use Suggested
      </Button>
    </div>

    <!-- Actions -->
    <div class="flex gap-2 pt-2 border-t">
      <Button @click="applySettings" :disabled="!hasChanges || isSaving" size="sm" class="flex-1">
        {{ isSaving ? 'Saving...' : 'Apply' }}
      </Button>
      <Button @click="resetToDefaults" :disabled="isSaving" size="sm" variant="outline">
        Reset
      </Button>
    </div>
  </div>
</template>

<script setup lang="ts">
import { ref, computed, onMounted, watch } from 'vue';
import { getVideoDisplaySettings, updateVideoDisplaySettings, getSuggestedDisplaySettings, calibrateVideo, type DisplaySettings, type SuggestedDisplaySettings, type CalibrationResult } from '../lib/api';
import { useAnalysisStore } from '../stores/analysis';
import { Button } from './ui/button';
import { Label } from './ui/label';
import { Icon } from './ui/icon';

const props = defineProps<{
  analysisId: string;
  videoId: string;
}>();

const emit = defineEmits<{
  'settings-updated': [settings: DisplaySettings];
  'calibration-result': [result: CalibrationResult];
}>();

const store = useAnalysisStore();

// State
const originalSettings = ref<DisplaySettings>({
  pixel_to_mm_factor: 11.0,
  heatmap_min_mm: 3.0,
  heatmap_max_mm: 30.0,
});

const localSettings = ref<DisplaySettings>({
  pixel_to_mm_factor: 11.0,
  heatmap_min_mm: 3.0,
  heatmap_max_mm: 30.0,
});

const suggestions = ref<SuggestedDisplaySettings | null>(null);
const isLoadingSuggestions = ref(false);
const isCalibrating = ref(false);
const calibrationInfo = ref<string | null>(null);
const isSaving = ref(false);
const error = ref<string | null>(null);
const saveSuccess = ref(false);

// Computed
const hasChanges = computed(() => {
  return (
    localSettings.value.pixel_to_mm_factor !== originalSettings.value.pixel_to_mm_factor ||
    localSettings.value.heatmap_min_mm !== originalSettings.value.heatmap_min_mm ||
    localSettings.value.heatmap_max_mm !== originalSettings.value.heatmap_max_mm
  );
});

// Methods
async function loadCurrentSettings() {
  try {
    error.value = null;
    const settings = await getVideoDisplaySettings(props.videoId);
    originalSettings.value = { ...settings };
    localSettings.value = { ...settings };
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to load settings';
    console.error('Failed to load display settings:', err);
  }
}

async function loadSuggestions() {
  try {
    error.value = null;
    isLoadingSuggestions.value = true;
    suggestions.value = await getSuggestedDisplaySettings(props.analysisId);
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to calculate suggestions';
    console.error('Failed to load suggestions:', err);
  } finally {
    isLoadingSuggestions.value = false;
  }
}

function applySuggestions() {
  if (!suggestions.value) return;

  localSettings.value.heatmap_min_mm = suggestions.value.heatmap_min_mm;
  localSettings.value.heatmap_max_mm = suggestions.value.heatmap_max_mm;
}

async function runCalibration() {
  try {
    error.value = null;
    isCalibrating.value = true;
    calibrationInfo.value = null;

    const frameNumber = store.currentFrame ?? 0;
    const result = await calibrateVideo(props.videoId, frameNumber);

    localSettings.value.pixel_to_mm_factor = result.pixel_to_mm_factor;
    calibrationInfo.value = result.tube_width_px.toFixed(1);
    emit('calibration-result', result);

    // Auto-compute min/max from current frame's mpp data
    const frameData = store.liveFrameData.get(store.currentFrame ?? 0);
    if (frameData?.mpp && frameData.mpp.length > 0) {
      const distances = frameData.mpp.map(mpp => mpp[6]); // distance is index 6
      const sorted = [...distances].sort((a, b) => a - b);
      const medianPx = sorted[Math.floor(sorted.length / 2)];
      const medianMm = medianPx / result.pixel_to_mm_factor;
      localSettings.value.heatmap_min_mm = Math.round(0.5 * medianMm * 10) / 10;
      localSettings.value.heatmap_max_mm = Math.round(1.5 * medianMm * 10) / 10;
    }

    // Auto-save calibration + computed min/max
    await applySettings();
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Calibration failed';
    console.error('Calibration failed:', err);
  } finally {
    isCalibrating.value = false;
  }
}

async function applySettings() {
  // Validate
  if (localSettings.value.heatmap_max_mm <= localSettings.value.heatmap_min_mm) {
    error.value = 'Maximum value must be greater than minimum value';
    return;
  }

  if (localSettings.value.pixel_to_mm_factor <= 0) {
    error.value = 'Pixel to MM factor must be greater than 0';
    return;
  }

  try {
    error.value = null;
    saveSuccess.value = false;
    isSaving.value = true;

    const updated = await updateVideoDisplaySettings(props.videoId, localSettings.value);
    originalSettings.value = { ...updated };
    localSettings.value = { ...updated };

    saveSuccess.value = true;
    emit('settings-updated', updated);

    // Clear success message after 3 seconds
    setTimeout(() => {
      saveSuccess.value = false;
    }, 3000);
  } catch (err) {
    error.value = err instanceof Error ? err.message : 'Failed to save settings';
    console.error('Failed to save settings:', err);
  } finally {
    isSaving.value = false;
  }
}

function resetToDefaults() {
  localSettings.value = {
    pixel_to_mm_factor: 11.0,
    heatmap_min_mm: 3.0,
    heatmap_max_mm: 30.0,
  };
  calibrationInfo.value = null;
  emit('calibration-result', null as unknown as CalibrationResult); // Clear calibration overlay
}

// Load settings on mount and when analysis ID changes
onMounted(() => {
  loadCurrentSettings();
});

watch(() => props.videoId, () => {
  loadCurrentSettings();
  suggestions.value = null;
  calibrationInfo.value = null;
  error.value = null;
  saveSuccess.value = false;
});
</script>

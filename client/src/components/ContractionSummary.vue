<script setup lang="ts">
import { computed } from 'vue';

import type { ContractionEvent } from '../lib/api';
import {
  isLegacyContractionDetection,
  type ContractionSummary as ContractionSummaryData,
} from '../lib/domain/contractions';
import ContractionTrendChart from './ContractionTrendChart.vue';

interface SummaryMetric {
  key: string;
  label: string;
  value: string;
  secondary?: string;
  tooltip: string;
}

const props = defineProps<{
  summary: ContractionSummaryData | null;
  detectionVersion: string | null;
  events: ContractionEvent[];
  fps: number | null;
  selectedContractionId?: string | null;
}>();

const emit = defineEmits<{
  'select-contraction': [contractionId: string];
}>();

const hasLegacyResults = computed(() =>
  isLegacyContractionDetection(props.detectionVersion)
);

const summaryMetrics = computed<SummaryMetric[]>(() => {
  if (!props.summary) {
    return [];
  }

  return [
    {
      key: 'total',
      label: 'Total contractions',
      value: props.summary.totalEvents.toString(),
      tooltip: 'Number of detected contraction events in this analysis',
    },
    {
      key: 'rate',
      label: 'Frequency',
      value: `${props.summary.overallRatePerMinute.toFixed(2)} / min`,
      secondary: `SD ${props.summary.standardDeviationPerMinute.toFixed(2)}`,
      tooltip: 'Average contractions per minute across the full recording',
    },
    {
      key: 'duration',
      label: 'Median duration',
      value: `${props.summary.medianDurationSeconds.toFixed(2)} s`,
      tooltip: 'Typical contraction event length (median)',
    },
    {
      key: 'speed',
      label: 'Median speed',
      value: `${props.summary.medianAbsSpeedMmPerS.toFixed(2)} mm/s`,
      tooltip: 'Absolute median propagation speed of contraction wave',
    },
    {
      key: 'area',
      label: 'Median area',
      value: `${props.summary.medianAreaMm2S.toFixed(2)} mm²·s`,
      tooltip: 'Integrated contraction strength over time (median)',
    },
  ];
});

function handleContractionSelection(contractionId: string) {
  emit('select-contraction', contractionId);
}
</script>

<template>
  <section class="contraction-summary">
    <div class="summary-header">
      <h3>Contraction Overview</h3>
      <span v-if="props.detectionVersion" class="version-subtitle">
        Detection model: {{ hasLegacyResults ? 'Legacy' : props.detectionVersion.toUpperCase() }}
      </span>
    </div>

    <div v-if="hasLegacyResults" class="legacy-note">
      These results predate Contraction Detection V2. Re-detect to refresh merge behavior and area semantics.
    </div>

    <div v-if="props.summary" class="metrics-grid">
      <div
        v-for="metric in summaryMetrics"
        :key="metric.key"
        class="metric-card"
        :title="metric.tooltip"
      >
        <div class="metric-label">{{ metric.label }}</div>
        <div class="metric-value">{{ metric.value }}</div>
        <div v-if="metric.secondary" class="metric-secondary">{{ metric.secondary }}</div>
      </div>
    </div>

    <ContractionTrendChart
      v-if="props.summary"
      :summary="props.summary"
      :events="props.events"
      :fps="props.fps"
      :selected-contraction-id="props.selectedContractionId"
      @select-contraction="handleContractionSelection"
    />

    <div v-else class="summary-empty">
      Contraction summary will appear once video timing metadata is available.
    </div>
  </section>
</template>

<style scoped>
.contraction-summary {
  padding: 1rem;
  border: 1px solid hsl(var(--border));
  border-radius: 0.85rem;
  background: hsl(var(--card));
  display: grid;
  gap: 0.85rem;
}

.summary-header h3 {
  margin: 0;
  font-size: 1.05rem;
  font-weight: 650;
}

.version-subtitle {
  display: block;
  margin-top: 0.15rem;
  font-size: 0.8rem;
  color: hsl(var(--muted-foreground));
}

.summary-empty {
  color: hsl(var(--muted-foreground));
  font-size: 0.9rem;
}

.legacy-note {
  border: 1px solid hsl(var(--border));
  border-radius: 0.65rem;
  background: hsl(var(--muted) / 0.45);
  padding: 0.7rem 0.85rem;
  font-size: 0.88rem;
}

.metrics-grid {
  display: grid;
  grid-template-columns: repeat(auto-fill, minmax(135px, 1fr));
  gap: 0.5rem;
}

.metric-card {
  padding: 0.6rem 0.75rem;
  border: 1px solid hsl(var(--border));
  border-radius: 0.55rem;
  background: hsl(var(--background));
  display: grid;
  gap: 0.15rem;
  cursor: default;
}

.metric-label {
  font-size: 0.7rem;
  font-weight: 700;
  text-transform: uppercase;
  letter-spacing: 0.04em;
  color: hsl(var(--muted-foreground));
}

.metric-value {
  font-size: 1.3rem;
  font-weight: 700;
  line-height: 1.15;
}

.metric-secondary {
  font-size: 0.78rem;
  color: hsl(var(--muted-foreground));
}
</style>

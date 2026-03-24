<script setup lang="ts">
import { computed, shallowRef, useTemplateRef } from 'vue';
import type { ChartComponentRef } from 'vue-chartjs';
import { Chart, getElementAtEvent } from 'vue-chartjs';
import {
  Chart as ChartJS,
  registerables,
  type ChartData,
  type ChartOptions,
  type ChartType,
} from 'chart.js';

import type { ContractionEvent } from '../lib/api';
import {
  buildContractionTrendChartModel,
  getContractionOverlayMetricLabel,
  type ContractionOverlayMetric,
  type ContractionSummary,
  type ContractionTrendBarDatum,
  type ContractionTrendOverlayDatum,
} from '../lib/domain/contractions';
import { formatTimestampWithMilliseconds } from '../lib/domain/formatting';
import { Button } from './ui/button';
import { ButtonGroup } from './ui/button-group';

ChartJS.register(...registerables);

type TrendChartType = 'bar' | 'scatter';
type TrendChartPoint = ContractionTrendBarDatum | ContractionTrendOverlayDatum;

interface OverlayOption {
  id: ContractionOverlayMetric;
  label: string;
}

const props = defineProps<{
  summary: ContractionSummary;
  events: ContractionEvent[];
  fps: number | null;
  selectedContractionId?: string | null;
}>();

const emit = defineEmits<{
  'select-contraction': [contractionId: string];
}>();

const chartRef = useTemplateRef<ChartComponentRef<TrendChartType, TrendChartPoint[], number>>('chart');
const overlayMetric = shallowRef<ContractionOverlayMetric>('none');

const overlayOptions: OverlayOption[] = [
  { id: 'none', label: 'None' },
  { id: 'speed', label: 'Speed' },
  { id: 'duration', label: 'Duration' },
  { id: 'area', label: 'Area' },
];

function withAlpha(color: string, alphaPercent: number): string {
  if (color.endsWith(')')) {
    return `${color.slice(0, -1)} / ${alphaPercent}%)`;
  }
  return color;
}

const colorPalette = computed(() => {
  if (typeof window === 'undefined') {
    return {
      background: 'oklch(1 0 0)',
      border: 'oklch(0.922 0 0)',
      foreground: 'oklch(0.145 0 0)',
      mutedForeground: 'oklch(0.556 0 0)',
      primary: 'oklch(0.205 0 0)',
      accent: 'oklch(0.6 0.118 184.704)',
    };
  }

  const styles = window.getComputedStyle(document.documentElement);
  return {
    background: styles.getPropertyValue('--background').trim() || 'oklch(1 0 0)',
    border: styles.getPropertyValue('--border').trim() || 'oklch(0.922 0 0)',
    foreground: styles.getPropertyValue('--foreground').trim() || 'oklch(0.145 0 0)',
    mutedForeground: styles.getPropertyValue('--muted-foreground').trim() || 'oklch(0.556 0 0)',
    primary: styles.getPropertyValue('--primary').trim() || 'oklch(0.205 0 0)',
    accent: styles.getPropertyValue('--chart-2').trim() || 'oklch(0.6 0.118 184.704)',
  };
});

const chartModel = computed(() =>
  buildContractionTrendChartModel(
    props.summary,
    props.events,
    props.fps,
    overlayMetric.value
  )
);

const overlayAxisLabel = computed(() =>
  getContractionOverlayMetricLabel(overlayMetric.value)
);

const chartData = computed<ChartData<TrendChartType, TrendChartPoint[], number>>(() => {
  const model = chartModel.value;
  const palette = colorPalette.value;
  if (!model) {
    return {
      datasets: [],
    };
  }

  return {
    datasets: [
      {
        datasetId: 'rate-bars',
        type: 'bar',
        label: 'Contractions / min',
        yAxisID: 'yRate',
        data: model.bars,
        backgroundColor: (context) => {
          const raw = context.raw as ContractionTrendBarDatum | undefined;
          return raw?.isPartial
            ? withAlpha(palette.primary, 55)
            : withAlpha(palette.primary, 88);
        },
        borderColor: palette.primary,
        borderWidth: 1,
        borderRadius: 8,
        maxBarThickness: 28,
        parsing: {
          xAxisKey: 'xMinutes',
          yAxisKey: 'ratePerMinute',
        },
      },
      {
        datasetId: 'overlay-points',
        type: 'scatter',
        label: overlayAxisLabel.value ?? 'Overlay',
        yAxisID: 'yOverlay',
        data: model.overlayPoints,
        hidden: overlayMetric.value === 'none',
        parsing: {
          xAxisKey: 'xMinutes',
          yAxisKey: 'y',
        },
        pointRadius: (context) => {
          const raw = context.raw as ContractionTrendOverlayDatum | undefined;
          return raw?.eventId === props.selectedContractionId ? 6 : 4;
        },
        pointHoverRadius: 7,
        pointBorderWidth: (context) => {
          const raw = context.raw as ContractionTrendOverlayDatum | undefined;
          return raw?.eventId === props.selectedContractionId ? 2 : 1;
        },
        pointBackgroundColor: (context) => {
          const raw = context.raw as ContractionTrendOverlayDatum | undefined;
          return raw?.eventId === props.selectedContractionId
            ? palette.background
            : palette.accent;
        },
        pointBorderColor: palette.accent,
      },
    ],
  };
});

const chartOptions = computed<ChartOptions<TrendChartType>>(() => {
  const model = chartModel.value;
  const palette = colorPalette.value;

  return {
    responsive: true,
    maintainAspectRatio: false,
    animation: false,
    interaction: {
      mode: 'nearest',
      intersect: false,
    },
    plugins: {
      legend: {
        display: false,
      },
      tooltip: {
        callbacks: {
          title(items) {
            const firstItem = items[0];
            if (!firstItem) {
              return '';
            }

            const raw = firstItem.raw as TrendChartPoint | undefined;
            if (firstItem.dataset.yAxisID === 'yOverlay') {
              const overlayPoint = raw as ContractionTrendOverlayDatum | undefined;
              if (!overlayPoint) {
                return '';
              }
              return formatTimestampWithMilliseconds(overlayPoint.startTimeSeconds);
            }

            const barPoint = raw as ContractionTrendBarDatum | undefined;
            if (!barPoint) {
              return '';
            }

            return `${(barPoint.startTimeSeconds / 60).toFixed(1)} to ${(barPoint.endTimeSeconds / 60).toFixed(1)} min`;
          },
          label(item) {
            const raw = item.raw as TrendChartPoint | undefined;
            if (!raw) {
              return '';
            }

            if (item.dataset.yAxisID === 'yOverlay') {
              const overlayPoint = raw as ContractionTrendOverlayDatum;
              const overlayValueLabel = overlayAxisLabel.value;
              const formattedOverlayValue = item.formattedValue;

              return [
                `${overlayValueLabel}: ${formattedOverlayValue}`,
                `Duration: ${overlayPoint.durationSeconds.toFixed(2)} s`,
                `Speed: ${overlayPoint.speedMmPerS.toFixed(2)} mm/s`,
                `Area: ${overlayPoint.areaMm2S.toFixed(2)} mm²·s`,
              ];
            }

            const barPoint = raw as ContractionTrendBarDatum;
            const lines = [
              `${barPoint.count} contraction${barPoint.count === 1 ? '' : 's'}`,
              `${barPoint.ratePerMinute.toFixed(2)} per minute`,
            ];

            if (barPoint.isPartial) {
              lines.push(`Normalized to ${barPoint.durationSeconds.toFixed(0)} s`);
            }

            return lines;
          },
        },
      },
    },
    scales: {
      x: {
        type: 'linear',
        min: 0,
        max: Math.max(model?.xMaxMinutes ?? 0, 1),
        title: {
          display: true,
          text: 'Time (min)',
          color: palette.foreground,
          font: {
            weight: 600,
          },
        },
        grid: {
          color: palette.border,
          drawBorder: false,
        },
        ticks: {
          color: palette.mutedForeground,
          callback(value) {
            return Number(value).toFixed(Number(value) % 1 === 0 ? 0 : 1);
          },
        },
      },
      yRate: {
        type: 'linear',
        position: 'left',
        beginAtZero: true,
        title: {
          display: true,
          text: 'Contractions / min',
          color: palette.foreground,
          font: {
            weight: 600,
          },
        },
        grid: {
          color: palette.border,
          drawBorder: false,
        },
        ticks: {
          color: palette.mutedForeground,
        },
      },
      yOverlay: {
        type: 'linear',
        display: overlayMetric.value !== 'none',
        position: 'right',
        beginAtZero: overlayMetric.value !== 'speed',
        title: {
          display: overlayMetric.value !== 'none',
          text: overlayAxisLabel.value ?? '',
          color: palette.foreground,
          font: {
            weight: 600,
          },
        },
        grid: {
          drawOnChartArea: false,
          drawBorder: false,
        },
        ticks: {
          color: palette.mutedForeground,
        },
      },
    },
  };
});

const chartDataProps = computed(() =>
  chartData.value as unknown as ChartData<ChartType>
);

const chartOptionsProps = computed(() =>
  chartOptions.value as unknown as ChartOptions<ChartType>
);

function handleOverlayMetricChange(nextMetric: ContractionOverlayMetric) {
  overlayMetric.value = nextMetric;
}

function handleChartClick(event: MouseEvent) {
  const chart = chartRef.value?.chart;
  if (!chart) {
    return;
  }

  const [element] = getElementAtEvent(chart as never, event);
  if (!element) {
    return;
  }

  const dataset = chart.data.datasets[element.datasetIndex];
  if (dataset?.yAxisID !== 'yOverlay') {
    return;
  }

  const rawPoint = dataset.data[element.index] as ContractionTrendOverlayDatum | undefined;
  if (rawPoint?.eventId) {
    emit('select-contraction', rawPoint.eventId);
  }
}

defineExpose({
  chartOptions,
  chartData,
});
</script>

<template>
  <div class="trend-chart">
    <div class="chart-toolbar">
      <div class="chart-title-group">
        <h4>Contractions over time</h4>
        <span class="chart-subtitle">1-minute bins</span>
      </div>

      <div class="overlay-controls">
        <span class="overlay-label">Color by</span>
        <ButtonGroup class="overlay-switcher">
          <Button
            v-for="option in overlayOptions"
            :key="option.id"
            size="sm"
            :variant="overlayMetric === option.id ? 'default' : 'outline'"
            @click="handleOverlayMetricChange(option.id)"
          >
            {{ option.label }}
          </Button>
        </ButtonGroup>
      </div>
    </div>

    <div class="chart-frame">
      <Chart
        ref="chart"
        type="bar"
        :data="chartDataProps"
        :options="chartOptionsProps"
        dataset-id-key="datasetId"
        aria-label="Contraction trend chart"
        @click="handleChartClick"
      />
    </div>

    <div class="chart-footer">
      <span class="chart-caption">
        {{ props.summary.bins.length }}-minute recording
      </span>
      <span v-if="chartModel?.partialBinNote" class="chart-caption">
        Final partial bin: {{ chartModel.partialBinNote }}
      </span>
    </div>
  </div>
</template>

<style scoped>
.trend-chart {
  display: grid;
  gap: 0.9rem;
}

.chart-toolbar {
  display: flex;
  align-items: flex-start;
  justify-content: space-between;
  gap: 1rem;
}

.chart-title-group {
  display: grid;
  gap: 0.1rem;
}

.chart-toolbar h4 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 650;
}

.chart-subtitle {
  font-size: 0.8rem;
  color: hsl(var(--muted-foreground));
}

.chart-caption,
.overlay-label {
  color: hsl(var(--muted-foreground));
  font-size: 0.82rem;
}

.overlay-controls {
  display: grid;
  gap: 0.35rem;
  justify-items: end;
}

.overlay-switcher {
  flex-wrap: wrap;
}

.chart-frame {
  height: 280px;
  border: 1px solid hsl(var(--border));
  border-radius: 0.65rem;
  background: hsl(var(--background));
  padding: 0.75rem;
}

.chart-footer {
  display: flex;
  justify-content: space-between;
  gap: 1rem;
  flex-wrap: wrap;
}

@media (max-width: 900px) {
  .chart-toolbar {
    flex-direction: column;
  }

  .overlay-controls {
    justify-items: start;
  }

  .chart-frame {
    height: 240px;
    padding: 0.6rem;
  }
}
</style>

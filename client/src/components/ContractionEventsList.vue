<script setup lang="ts">
import { computed, ref } from 'vue';

import type { ContractionEvent } from '../lib/api';
import { formatTimestampWithMilliseconds } from '../lib/domain/formatting';
import { getContractionStartTimeSeconds } from '../lib/domain/contractions';

const props = defineProps<{
  events: ContractionEvent[];
  fps: number | null;
  selectedContractionId?: string | null;
}>();

const emit = defineEmits<{
  'jump-to-frame': [frame: number];
  'select-contraction': [contractionId: string];
}>();

const sortBy = ref<'timestamp' | 'duration' | 'speed' | 'area'>('timestamp');
const sortOrder = ref<'asc' | 'desc'>('asc');

const sortedEvents = computed(() => {
  const events = [...props.events];

  events.sort((left, right) => {
    let leftValue: number;
    let rightValue: number;

    switch (sortBy.value) {
      case 'timestamp':
        leftValue = left.t_range_frames[0];
        rightValue = right.t_range_frames[0];
        break;
      case 'duration':
        leftValue = left.duration_s;
        rightValue = right.duration_s;
        break;
      case 'speed':
        leftValue = Math.abs(left.velocity_phys_per_s);
        rightValue = Math.abs(right.velocity_phys_per_s);
        break;
      case 'area':
        leftValue = left.area_exact;
        rightValue = right.area_exact;
        break;
      default:
        leftValue = left.t_range_frames[0];
        rightValue = right.t_range_frames[0];
        break;
    }

    return sortOrder.value === 'asc' ? leftValue - rightValue : rightValue - leftValue;
  });

  return events;
});

function setSortBy(field: typeof sortBy.value) {
  if (sortBy.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc';
    return;
  }

  sortBy.value = field;
  sortOrder.value = 'asc';
}

function formatDuration(seconds: number): string {
  if (seconds < 1) {
    return `${(seconds * 1000).toFixed(0)} ms`;
  }
  return `${seconds.toFixed(2)} s`;
}

function formatSpeed(speed: number): string {
  return `${speed.toFixed(2)} mm/s`;
}

function formatArea(area: number): string {
  return `${area.toFixed(2)} mm²·s`;
}

function formatTimestamp(event: ContractionEvent): string {
  if (!props.fps || props.fps <= 0) {
    return `Frame ${event.t_range_frames[0]}`;
  }
  return formatTimestampWithMilliseconds(
    getContractionStartTimeSeconds(event, props.fps)
  );
}

function exportToCSV() {
  const headers = [
    'Timestamp',
    'Start Frame',
    'Duration (s)',
    'Speed (mm/s)',
    'Area (mm²·s)',
  ];

  const rows = sortedEvents.value.map((event) => [
    formatTimestamp(event),
    event.t_range_frames[0],
    event.duration_s.toFixed(2),
    event.velocity_phys_per_s.toFixed(2),
    event.area_exact.toFixed(2),
  ]);

  const csv = [
    headers.join(','),
    ...rows.map((row) => row.join(',')),
  ].join('\n');

  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const anchor = document.createElement('a');
  anchor.href = url;
  anchor.download = `contraction_events_${Date.now()}.csv`;
  anchor.click();
  URL.revokeObjectURL(url);
}

function handleSelectContraction(event: ContractionEvent) {
  emit('select-contraction', event.id);
}

function handleJumpToEvent(event: ContractionEvent) {
  emit('select-contraction', event.id);
  emit('jump-to-frame', event.t_range_frames[0]);
}
</script>

<template>
  <div class="contraction-events-list">
    <div class="list-header">
      <h3>Contractions ({{ props.events.length }})</h3>
      <button
        v-if="props.events.length > 0"
        class="export-button"
        @click="exportToCSV"
      >
        Export CSV
      </button>
    </div>

    <div v-if="props.events.length === 0" class="empty-state">
      No contraction events detected. Run contraction detection to see results.
    </div>

    <div v-else class="table-wrapper">
      <table class="events-table">
        <thead>
          <tr>
            <th
              class="sortable timestamp-header"
              :aria-sort="sortBy === 'timestamp' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setSortBy('timestamp')"
            >
              Timestamp
              <span v-if="sortBy === 'timestamp'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th
              class="sortable numeric-header"
              :aria-sort="sortBy === 'duration' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setSortBy('duration')"
            >
              Duration
              <span v-if="sortBy === 'duration'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th
              class="sortable numeric-header"
              :aria-sort="sortBy === 'speed' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setSortBy('speed')"
            >
              Speed
              <span v-if="sortBy === 'speed'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
            <th
              class="sortable numeric-header"
              :aria-sort="sortBy === 'area' ? (sortOrder === 'asc' ? 'ascending' : 'descending') : 'none'"
              @click="setSortBy('area')"
            >
              Area
              <span v-if="sortBy === 'area'">{{ sortOrder === 'asc' ? '↑' : '↓' }}</span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="event in sortedEvents"
            :key="event.id"
            class="event-row"
            :data-selected="props.selectedContractionId === event.id"
            @click="handleSelectContraction(event)"
          >
            <td class="timestamp-cell">
              <button
                class="timestamp-button"
                @click.stop="handleJumpToEvent(event)"
              >
                {{ formatTimestamp(event) }}
              </button>
            </td>
            <td class="numeric-cell">{{ formatDuration(event.duration_s) }}</td>
            <td class="numeric-cell">{{ formatSpeed(event.velocity_phys_per_s) }}</td>
            <td class="numeric-cell">{{ formatArea(event.area_exact) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.contraction-events-list {
  padding: 0.85rem;
  border: 1px solid hsl(var(--border));
  border-radius: 0.85rem;
  background: hsl(var(--card));
}

.list-header {
  display: flex;
  align-items: center;
  justify-content: space-between;
  gap: 1rem;
  margin-bottom: 0.55rem;
}

.list-header h3 {
  margin: 0;
  font-size: 0.95rem;
  font-weight: 650;
}

.export-button {
  border: 1px solid hsl(var(--border));
  border-radius: 0.5rem;
  background: hsl(var(--background));
  padding: 0.35rem 0.65rem;
  font: inherit;
  font-size: 0.82rem;
  cursor: pointer;
}

.empty-state {
  color: hsl(var(--muted-foreground));
  font-size: 0.9rem;
}

.table-wrapper {
  overflow-x: auto;
  border: 1px solid hsl(var(--border));
  border-radius: 0.8rem;
}

.events-table {
  width: 100%;
  border-collapse: separate;
  border-spacing: 0;
  font-size: 0.87rem;
  font-variant-numeric: tabular-nums;
}

.events-table th,
.events-table td {
  padding: 0.55rem 0.75rem;
  border-bottom: 1px solid hsl(var(--border));
  text-align: left;
}

.events-table th {
  position: sticky;
  top: 0;
  z-index: 1;
  background: hsl(var(--background));
  color: hsl(var(--muted-foreground));
  font-size: 0.72rem;
  font-weight: 700;
  letter-spacing: 0.04em;
  text-transform: uppercase;
}

.sortable {
  cursor: pointer;
  user-select: none;
}

.numeric-header,
.numeric-cell {
  text-align: right;
}

.timestamp-header,
.timestamp-cell {
  min-width: 180px;
}

.event-row:hover {
  background: hsl(var(--muted) / 0.26);
}

.event-row[data-selected='true'] {
  background: hsl(var(--primary) / 0.08);
}

.event-row[data-selected='true'] td {
  border-bottom-color: hsl(var(--primary) / 0.28);
}

.timestamp-button {
  border: none;
  background: transparent;
  padding: 0;
  color: hsl(var(--foreground));
  font: inherit;
  font-weight: 500;
  cursor: pointer;
  text-decoration: none;
}

.timestamp-button:hover {
  color: hsl(var(--primary));
  text-decoration: underline;
  text-underline-offset: 0.14em;
}

.timestamp-button:focus-visible {
  outline: none;
  box-shadow: 0 0 0 3px hsl(var(--primary) / 0.18);
  border-radius: 0.25rem;
}

@media (max-width: 900px) {
  .list-header {
    flex-direction: column;
  }

  .events-table th,
  .events-table td {
    padding: 0.45rem 0.55rem;
  }
}
</style>

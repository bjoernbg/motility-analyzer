<script setup lang="ts">
import { ref, computed } from 'vue';
import { useAnalysisStore } from '../stores/analysis';
import type { ContractionEvent } from '../lib/api';

const store = useAnalysisStore();

const sortBy = ref<'start_time' | 'duration' | 'velocity' | 'area'>('start_time');
const sortOrder = ref<'asc' | 'desc'>('asc');

const sortedEvents = computed(() => {
  const events = [...store.contractionEvents];
  
  events.sort((a, b) => {
    let aVal: number;
    let bVal: number;
    
    switch (sortBy.value) {
      case 'start_time':
        aVal = a.t_range_frames[0];
        bVal = b.t_range_frames[0];
        break;
      case 'duration':
        aVal = a.duration_s;
        bVal = b.duration_s;
        break;
      case 'velocity':
        aVal = Math.abs(a.velocity_phys_per_s);
        bVal = Math.abs(b.velocity_phys_per_s);
        break;
      case 'area':
        aVal = a.area_exact;
        bVal = b.area_exact;
        break;
      default:
        return 0;
    }
    
    if (sortOrder.value === 'asc') {
      return aVal - bVal;
    } else {
      return bVal - aVal;
    }
  });
  
  return events;
});

function setSortBy(field: typeof sortBy.value) {
  if (sortBy.value === field) {
    sortOrder.value = sortOrder.value === 'asc' ? 'desc' : 'asc';
  } else {
    sortBy.value = field;
    sortOrder.value = 'asc';
  }
}

function formatTime(seconds: number): string {
  if (seconds < 1) {
    return `${(seconds * 1000).toFixed(0)}ms`;
  }
  return `${seconds.toFixed(2)}s`;
}

function formatVelocity(velocity: number): string {
  return `${velocity.toFixed(2)} mm/s`;
}

function formatArea(area: number): string {
  return `${area.toFixed(2)} mm²·s`;
}

function exportToCSV() {
  const headers = [
    'Label',
    'Start Frame',
    'End Frame',
    'Duration (s)',
    'Height (mm)',
    'Velocity (mm/s)',
    'Area Exact (mm²·s)',
    'Area Triangle (mm²·s)',
  ];
  
  const rows = sortedEvents.value.map(event => [
    event.label,
    event.t_range_frames[0],
    event.t_range_frames[1],
    event.duration_s.toFixed(2),
    event.height_phys.toFixed(2),
    event.velocity_phys_per_s.toFixed(2),
    event.area_exact.toFixed(2),
    event.area_triangle.toFixed(2),
  ]);
  
  const csv = [
    headers.join(','),
    ...rows.map(row => row.join(',')),
  ].join('\n');
  
  const blob = new Blob([csv], { type: 'text/csv' });
  const url = URL.createObjectURL(blob);
  const a = document.createElement('a');
  a.href = url;
  a.download = `contraction_events_${Date.now()}.csv`;
  a.click();
  URL.revokeObjectURL(url);
}
</script>

<template>
  <div class="contraction-events-list">
    <div class="flex items-center justify-between mb-4">
      <h3 class="text-lg font-semibold">Contraction Events ({{ store.contractionEvents.length }})</h3>
      <button
        v-if="store.contractionEvents.length > 0"
        @click="exportToCSV"
        class="text-sm px-3 py-1 border rounded hover:bg-muted"
      >
        Export CSV
      </button>
    </div>

    <div v-if="store.contractionEvents.length === 0" class="text-sm text-muted-foreground">
      No contraction events detected. Run contraction detection to see results.
    </div>

    <div v-else class="overflow-x-auto">
      <table class="w-full text-sm">
        <thead>
          <tr class="border-b">
            <th
              class="text-left p-2 cursor-pointer hover:bg-muted"
              @click="setSortBy('start_time')"
            >
              Start Frame
              <span v-if="sortBy === 'start_time'">
                {{ sortOrder === 'asc' ? '↑' : '↓' }}
              </span>
            </th>
            <th class="text-left p-2">End Frame</th>
            <th
              class="text-left p-2 cursor-pointer hover:bg-muted"
              @click="setSortBy('duration')"
            >
              Duration
              <span v-if="sortBy === 'duration'">
                {{ sortOrder === 'asc' ? '↑' : '↓' }}
              </span>
            </th>
            <th class="text-left p-2">Height (mm)</th>
            <th
              class="text-left p-2 cursor-pointer hover:bg-muted"
              @click="setSortBy('velocity')"
            >
              Velocity (mm/s)
              <span v-if="sortBy === 'velocity'">
                {{ sortOrder === 'asc' ? '↑' : '↓' }}
              </span>
            </th>
            <th
              class="text-left p-2 cursor-pointer hover:bg-muted"
              @click="setSortBy('area')"
            >
              Area (mm²·s)
              <span v-if="sortBy === 'area'">
                {{ sortOrder === 'asc' ? '↑' : '↓' }}
              </span>
            </th>
          </tr>
        </thead>
        <tbody>
          <tr
            v-for="event in sortedEvents"
            :key="event.id"
            class="border-b hover:bg-muted/50"
          >
            <td class="p-2">{{ event.t_range_frames[0] }}</td>
            <td class="p-2">{{ event.t_range_frames[1] }}</td>
            <td class="p-2">{{ formatTime(event.duration_s) }}</td>
            <td class="p-2">{{ event.height_phys.toFixed(2) }}</td>
            <td class="p-2">{{ formatVelocity(event.velocity_phys_per_s) }}</td>
            <td class="p-2">{{ formatArea(event.area_exact) }}</td>
          </tr>
        </tbody>
      </table>
    </div>
  </div>
</template>

<style scoped>
.contraction-events-list {
  padding: 1rem;
  border: 1px solid hsl(var(--border));
  border-radius: 0.5rem;
  background: hsl(var(--card));
}
</style>


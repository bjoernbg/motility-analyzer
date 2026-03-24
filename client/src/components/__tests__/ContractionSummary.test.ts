import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';

import type { ContractionEvent } from '../../lib/api';
import { buildContractionSummary } from '../../lib/domain/contractions';
import ContractionSummary from '../ContractionSummary.vue';

function createEvent(
  startFrame: number,
  durationSeconds: number,
  area = 10,
  speed = 1.5
): ContractionEvent {
  const endFrame = startFrame + Math.round(durationSeconds * 10) - 1;
  return {
    id: `event-${startFrame}`,
    label: startFrame,
    n_pixels: 10,
    threshold_used: -1,
    t_range_frames: [startFrame, endFrame],
    y_range_idx: [0, 5],
    duration_s: durationSeconds,
    height_phys: 5,
    velocity_phys_per_s: speed,
    line_fit: {
      a_idx_per_frame: 0.1,
      b: 0,
    },
    area_exact: area,
    area_triangle: area,
    created_at: '2026-03-16T12:00:00',
  };
}

describe('ContractionSummary', () => {
  it('renders five KPI cards and passes chart inputs to the trend chart', () => {
    const events = [
      createEvent(100, 3, 10, 0.5),
      createEvent(1400, 5, 20, -1.5),
    ];
    const summary = buildContractionSummary(events, 10, 150);

    const wrapper = mount(ContractionSummary, {
      props: {
        summary,
        detectionVersion: 'v2',
        events,
        fps: 10,
        selectedContractionId: 'event-100',
      },
      global: {
        stubs: {
          ContractionTrendChart: {
            props: ['summary', 'events', 'fps', 'selectedContractionId'],
            template: '<div class="trend-chart-stub">{{ summary?.bins.length }} bins / {{ events.length }} events</div>',
          },
        },
      },
    });

    expect(wrapper.findAll('.metric-card')).toHaveLength(5);
    expect(wrapper.text()).toContain('Contraction Overview');
    expect(wrapper.text()).toContain('Median duration');
    expect(wrapper.text()).toContain('Median speed');
    expect(wrapper.text()).toContain('Median area');
    expect(wrapper.text()).toContain('3 bins / 2 events');
  });

  it('shows the legacy warning and empty state when summary data is unavailable', () => {
    const wrapper = mount(ContractionSummary, {
      props: {
        summary: null,
        detectionVersion: 'legacy-v1',
        events: [],
        fps: null,
        selectedContractionId: null,
      },
    });

    expect(wrapper.text()).toContain('Detection model: Legacy');
    expect(wrapper.text()).toContain('Contraction summary will appear once video timing metadata is available.');
  });
});

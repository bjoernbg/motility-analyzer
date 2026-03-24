import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';
import { nextTick } from 'vue';

import type { ContractionEvent } from '../../lib/api';
import ContractionEventsList from '../ContractionEventsList.vue';

function createEvent(
  id: string,
  startFrame: number,
  durationSeconds: number,
  area: number
): ContractionEvent {
  return {
    id,
    label: startFrame,
    n_pixels: 10,
    threshold_used: -1,
    t_range_frames: [startFrame, startFrame + 9],
    y_range_idx: [0, 6],
    duration_s: durationSeconds,
    height_phys: 6,
    velocity_phys_per_s: 1.2,
    line_fit: {
      a_idx_per_frame: 0.1,
      b: 0,
    },
    area_exact: area,
    area_triangle: area,
    created_at: '2026-03-16T12:00:00',
  };
}

describe('ContractionEventsList', () => {
  it('emits the start frame when the timestamp is clicked', async () => {
    const wrapper = mount(ContractionEventsList, {
      props: {
        events: [createEvent('a', 120, 4.5, 20)],
        fps: 10,
        selectedContractionId: null,
      },
    });

    await wrapper.get('.timestamp-button').trigger('click');

    expect(wrapper.emitted('jump-to-frame')).toEqual([[120]]);
    expect(wrapper.emitted('select-contraction')).toEqual([['a']]);
  });

  it('sorts by area when the area header is clicked', async () => {
    const wrapper = mount(ContractionEventsList, {
      props: {
        events: [
          createEvent('a', 120, 4.5, 20),
          createEvent('b', 40, 5.0, 8),
          createEvent('c', 80, 3.5, 35),
        ],
        fps: 10,
        selectedContractionId: null,
      },
    });

    const before = wrapper.findAll('tbody tr').map((row) => row.text());
    expect(before[0]).toContain('0:04.000');

    await wrapper.get('th:nth-child(4)').trigger('click');
    await nextTick();

    const ascending = wrapper.findAll('tbody tr').map((row) => row.text());
    expect(ascending[0]).toContain('8.00 mm²·s');

    await wrapper.get('th:nth-child(4)').trigger('click');
    await nextTick();

    const descending = wrapper.findAll('tbody tr').map((row) => row.text());
    expect(descending[0]).toContain('35.00 mm²·s');
  });

  it('emits selection and highlights the active row', async () => {
    const events = [
      createEvent('a', 120, 4.5, 20),
      createEvent('b', 40, 5.0, 8),
    ];

    const wrapper = mount(ContractionEventsList, {
      props: {
        events,
        fps: 10,
        selectedContractionId: 'b',
      },
    });

    const rows = wrapper.findAll('tbody tr');
    expect(rows[0]?.attributes('data-selected')).toBe('true');

    await rows[0]?.trigger('click');

    expect(wrapper.emitted('select-contraction')).toContainEqual(['b']);
  });
});

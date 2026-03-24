import { describe, expect, it, vi } from 'vitest';
import { mount } from '@vue/test-utils';

import type { ContractionEvent } from '../../lib/api';
import { buildContractionSummary } from '../../lib/domain/contractions';
import ContractionTrendChart from '../ContractionTrendChart.vue';

const { getElementAtEventMock } = vi.hoisted(() => ({
  getElementAtEventMock: vi.fn(() => []),
}));

vi.mock('vue-chartjs', async () => {
  const { defineComponent, h } = await import('vue');

  return {
    Chart: defineComponent({
      name: 'Chart',
      props: {
        data: { type: Object, required: true },
        options: { type: Object, required: true },
        type: { type: String, required: true },
        datasetIdKey: { type: String, default: '' },
        ariaLabel: { type: String, default: '' },
      },
      emits: ['click'],
      setup(props, { emit, expose }) {
        const chart = {
          get data() {
            return props.data;
          },
        };

        expose({ chart });

        return () => h('button', {
          class: 'chart-stub',
          type: 'button',
          onClick: (event: MouseEvent) => emit('click', event),
        });
      },
    }),
    getElementAtEvent: getElementAtEventMock,
  };
});

function createEvent(
  id: string,
  startFrame: number,
  durationSeconds: number,
  area: number,
  speed: number
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

function getButtonByText(wrapper: ReturnType<typeof mount>, label: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text() === label);
  if (!button) {
    throw new Error(`Button not found: ${label}`);
  }
  return button;
}

describe('ContractionTrendChart', () => {
  it('switches overlays and exposes tooltip content for the selected metric', async () => {
    const events = [
      createEvent('a', 120, 4.5, 20, 1.2),
      createEvent('b', 480, 5.0, 8, -0.8),
    ];
    const summary = buildContractionSummary(events, 10, 150);

    const wrapper = mount(ContractionTrendChart, {
      props: {
        summary: summary!,
        events,
        fps: 10,
        selectedContractionId: null,
      },
    });

    let chartStub = wrapper.getComponent({ name: 'Chart' });
    let options = chartStub.props('options') as Record<string, any>;
    expect(options.scales.yOverlay.display).toBe(false);

    await getButtonByText(wrapper, 'Speed').trigger('click');

    chartStub = wrapper.getComponent({ name: 'Chart' });
    options = chartStub.props('options') as Record<string, any>;
    const data = chartStub.props('data') as Record<string, any>;
    const overlayDataset = data.datasets[1];
    const callbacks = options.plugins.tooltip.callbacks;
    const tooltipLines = callbacks.label({
      dataset: overlayDataset,
      raw: overlayDataset.data[0],
      formattedValue: '1.2',
    });

    expect(options.scales.yOverlay.display).toBe(true);
    expect(options.scales.yOverlay.title.text).toBe('Propagation speed (mm/s)');
    expect(tooltipLines[0]).toContain('Propagation speed (mm/s): 1.2');
    expect(tooltipLines).toContain('Duration: 4.50 s');
    expect(tooltipLines).toContain('Speed: 1.20 mm/s');
    expect(tooltipLines).toContain('Area: 20.00 mm²·s');
  });

  it('emits contraction selection when an overlay point is clicked', async () => {
    const events = [
      createEvent('a', 120, 4.5, 20, 1.2),
      createEvent('b', 480, 5.0, 8, -0.8),
    ];
    const summary = buildContractionSummary(events, 10, 150);

    getElementAtEventMock.mockReturnValue([{ datasetIndex: 1, index: 0 }]);

    const wrapper = mount(ContractionTrendChart, {
      props: {
        summary: summary!,
        events,
        fps: 10,
        selectedContractionId: null,
      },
    });

    await getButtonByText(wrapper, 'Speed').trigger('click');
    await wrapper.get('.chart-stub').trigger('click');

    expect(wrapper.emitted('select-contraction')).toEqual([['a']]);
  });
});

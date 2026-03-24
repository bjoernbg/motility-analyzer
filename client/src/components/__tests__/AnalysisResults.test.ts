import { beforeEach, describe, expect, it } from 'vitest';
import { createPinia, setActivePinia } from 'pinia';
import { mount } from '@vue/test-utils';

import type { Analysis, ContractionEvent, Video } from '../../lib/api';
import { createContractionDetectionParameters } from '../../lib/domain/contractions';
import { useAnalysisStore } from '../../stores/analysis';
import AnalysisResults from '../AnalysisResults.vue';

function createEvent(startFrame: number, durationSeconds: number, area = 10): ContractionEvent {
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
    velocity_phys_per_s: 1.5,
    line_fit: {
      a_idx_per_frame: 0.1,
      b: 0,
    },
    area_exact: area,
    area_triangle: area,
    created_at: '2026-03-16T12:00:00',
  };
}

function createVideo(): Video {
  return {
    id: 'video-1',
    filename: 'video.mp4',
    upload_date: '2026-03-16T12:00:00',
    file_path: '/tmp/video.mp4',
    metadata: {
      total_frames: 1500,
      fps: 10,
      frame_multiplier: 1,
      width: 1920,
      height: 1080,
      display_aspect_ratio: null,
      duration: 150,
      file_size: 1024,
      codec: 'h264',
    },
  };
}

function createAnalysis(): Analysis {
  return {
    id: 'analysis-1',
    video_id: 'video-1',
    parameters: {},
    status: 'completed',
    progress: 100,
    processed_frames: 1500,
    results_path: '/tmp/results.json',
    global_data: {},
    created_at: '2026-03-16T12:00:00',
  };
}

describe('AnalysisResults', () => {
  let pinia: ReturnType<typeof createPinia>;

  beforeEach(() => {
    pinia = createPinia();
    setActivePinia(pinia);
  });

  it('keeps the redesigned contraction sections in order', () => {
    const store = useAnalysisStore();
    store.currentAnalysis = createAnalysis();
    store.currentVideo = createVideo();
    store.progressStatus = 'completed';
    store.contractionEvents = [createEvent(100, 3)];
    store.contractionDetectionVersion = 'v2';
    store.contractionDetectionParametersUsed = createContractionDetectionParameters();

    const wrapper = mount(AnalysisResults, {
      global: {
        plugins: [pinia],
        stubs: {
          ContractionTrendChart: {
            template: '<div class="trend-chart-stub" />',
          },
        },
      },
    });

    expect(wrapper.find('.stats-grid').exists()).toBe(false);
    expect(wrapper.find('.results-shell').exists()).toBe(true);

    const text = wrapper.text();
    expect(text.indexOf('Contraction Overview')).toBeLessThan(text.indexOf('Contraction Detection'));
    expect(text.indexOf('Contraction Detection')).toBeLessThan(text.indexOf('Contractions (1)'));
  });

  it('propagates contraction selection from the table', async () => {
    const store = useAnalysisStore();
    store.currentAnalysis = createAnalysis();
    store.currentVideo = createVideo();
    store.progressStatus = 'completed';
    store.contractionEvents = [createEvent(100, 3)];
    store.contractionDetectionVersion = 'v2';
    store.contractionDetectionParametersUsed = createContractionDetectionParameters();

    const wrapper = mount(AnalysisResults, {
      global: {
        plugins: [pinia],
        stubs: {
          ContractionTrendChart: {
            template: '<div class="trend-chart-stub" />',
          },
        },
      },
    });

    await wrapper.get('.event-row').trigger('click');

    expect(wrapper.emitted('select-contraction')).toEqual([['event-100']]);
  });

  it('hydrates saved custom detection parameters as custom workflow state', () => {
    const store = useAnalysisStore();
    store.currentAnalysis = createAnalysis();
    store.currentVideo = createVideo();
    store.progressStatus = 'completed';
    store.contractionEvents = [createEvent(100, 3)];
    store.contractionDetectionVersion = 'v2';
    store.contractionDetectionParametersUsed = createContractionDetectionParameters({
      min_duration_s: 8.5,
    });

    const wrapper = mount(AnalysisResults, {
      global: {
        plugins: [pinia],
        stubs: {
          ContractionTrendChart: {
            template: '<div class="trend-chart-stub" />',
          },
        },
      },
    });

    expect(wrapper.text()).toContain('Current: Custom');
  });
});

import { describe, expect, it } from 'vitest';
import { mount } from '@vue/test-utils';

import ContractionDetectionControls from '../ContractionDetectionControls.vue';
import {
  createContractionDetectionParameters,
  getContractionDetectionPreset,
} from '../../lib/domain/contractions';

function getButtonByText(wrapper: ReturnType<typeof mount>, label: string) {
  const button = wrapper.findAll('button').find((candidate) => candidate.text() === label);
  if (!button) {
    throw new Error(`Button not found: ${label}`);
  }
  return button;
}

describe('ContractionDetectionControls', () => {
  it('shows preset-first controls and emits a full preset bundle', async () => {
    const modelValue = createContractionDetectionParameters();

    const wrapper = mount(ContractionDetectionControls, {
      props: {
        modelValue,
        parametersUsed: modelValue,
        draftPresetId: 'balanced',
        loadedPresetId: 'balanced',
        isDirty: false,
        hasContractionEvents: true,
        canDetect: true,
        isDetecting: false,
        detectionError: null,
      },
    });

    expect(wrapper.findAll('.preset-button')).toHaveLength(3);
    expect(wrapper.text()).toContain('Current: Balanced');
    expect(wrapper.get('.advanced-panel').attributes('open')).toBeUndefined();

    await wrapper.get('.preset-button').trigger('click');

    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toEqual(
      createContractionDetectionParameters(getContractionDetectionPreset('conservative').parameters)
    );
  });

  it('shows custom expert state when advanced values diverge from presets', async () => {
    const loadedParameters = createContractionDetectionParameters();

    const wrapper = mount(ContractionDetectionControls, {
      props: {
        modelValue: loadedParameters,
        parametersUsed: loadedParameters,
        draftPresetId: 'custom',
        loadedPresetId: 'balanced',
        isDirty: true,
        hasContractionEvents: true,
        canDetect: true,
        isDetecting: false,
        detectionError: null,
      },
    });

    await wrapper.get('#threshold-percentile').setValue('12.5');

    expect(wrapper.text()).toContain('Draft: Custom');
    expect(wrapper.text()).toContain('Reset changes');
    expect(wrapper.emitted('update:modelValue')?.[0]?.[0]).toMatchObject({
      threshold_percentile: 12.5,
    });

    await getButtonByText(wrapper, 'Run detection again').trigger('click');
    expect(wrapper.emitted('detect')).toHaveLength(1);
  });
});

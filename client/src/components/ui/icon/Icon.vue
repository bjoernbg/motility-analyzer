<script setup lang="ts">
import { Icon as IconifyIcon } from '@iconify/vue';
import { computed } from 'vue';

interface Props {
  name: string;
  size?: string | number;
  color?: string;
}

const props = withDefaults(defineProps<Props>(), {
  size: '1.1em',
  color: 'currentColor',
});

const iconStyle = computed(() => ({
  color: props.color,
}));
</script>

<template>
  <IconifyIcon
    :icon="name"
    :width="size"
    :height="size"
    :style="iconStyle"
  />
</template>


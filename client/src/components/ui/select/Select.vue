<script setup lang="ts">
import type { SelectRootEmits, SelectRootProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { SelectRoot, useForwardPropsEmits } from "reka-ui"

const props = defineProps<SelectRootProps & { class?: HTMLAttributes["class"] }>()
const emits = defineEmits<SelectRootEmits>()

const delegatedProps = reactiveOmit(props, "class")

const forwarded = useForwardPropsEmits(delegatedProps, emits)
</script>

<template>
  <SelectRoot v-bind="forwarded">
    <slot />
  </SelectRoot>
</template>

<script setup lang="ts">
import type { SelectValueProps } from "reka-ui"
import type { HTMLAttributes } from "vue"
import { reactiveOmit } from "@vueuse/core"
import { SelectValue, useForwardProps } from "reka-ui"
import { cn } from "@/lib/utils"

const props = defineProps<SelectValueProps & { class?: HTMLAttributes["class"] }>()

const delegatedProps = reactiveOmit(props, "class")

const forwardedProps = useForwardProps(delegatedProps)
</script>

<template>
  <SelectValue
    data-slot="select-value"
    v-bind="forwardedProps"
    :class="cn('', props.class)"
  >
    <slot />
  </SelectValue>
</template>

<template>
  <span class="status-dot-wrap" :class="`is-${status}`">
    <span class="status-dot-slot" aria-hidden="true">
      <span class="status-dot" :class="{ 'is-pulse': shouldPulse }" />
    </span>
    <span v-if="label" class="status-dot-label">{{ label }}</span>
  </span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  status: { type: String, default: 'neutral' }, // online | active | offline | warning | danger | neutral
  label: { type: String, default: '' },
  pulse: { type: Boolean, default: undefined },
})

const shouldPulse = computed(() => {
  if (typeof props.pulse === 'boolean') return props.pulse
  return props.status === 'online' || props.status === 'active'
})
</script>

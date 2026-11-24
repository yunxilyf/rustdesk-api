<template>
  <span v-if="label" class="os-badge" :title="label">
    <span class="os-badge-icon" :class="`os-${kind}`" aria-hidden="true">
      <svg v-if="kind === 'windows'" viewBox="0 0 16 16" width="13" height="13" fill="currentColor">
        <path d="M1.5 2.7 7.3 1.9v5.5H1.5V2.7zm6.7-.9 6.3-.9v6.5H8.2V1.8zM1.5 8.5h5.8v5.5l-5.8-.8V8.5zm6.7 0h6.3v6.6l-6.3-.9V8.5z" />
      </svg>
      <svg v-else-if="kind === 'apple'" viewBox="0 0 16 16" width="13" height="13" fill="currentColor">
        <path d="M11.3 8.4c0-1.6 1.3-2.4 1.4-2.5-.8-1.1-2-1.3-2.4-1.3-1-.1-2 .6-2.5.6-.5 0-1.3-.6-2.1-.6-1.1 0-2.1.6-2.7 1.6-1.2 2-.3 5 .8 6.6.5.8 1.2 1.6 2 1.6.8 0 1.1-.5 2.1-.5 1 0 1.3.5 2.1.5.9 0 1.4-.8 1.9-1.6.6-.9.9-1.7.9-1.8 0 0-1.5-.6-1.5-2.6zM9.7 3.4c.4-.5.7-1.3.6-2-.7 0-1.4.4-1.9 1-.4.4-.7 1.2-.6 1.9.7.1 1.4-.4 1.9-.9z" />
      </svg>
      <svg v-else-if="kind === 'linux'" viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.5" stroke-linecap="round" stroke-linejoin="round">
        <rect x="2" y="2.5" width="12" height="11" rx="2" />
        <path d="M5 6.5 7.2 8.3 5 10.1M8.5 10.1H11" />
      </svg>
      <svg v-else-if="kind === 'android'" viewBox="0 0 16 16" width="13" height="13" fill="currentColor">
        <path d="M4.2 6.5h7.6v5.2a1.3 1.3 0 0 1-1.3 1.3H5.5a1.3 1.3 0 0 1-1.3-1.3V6.5zm.5-1a3.3 3.3 0 0 1 6.6 0H4.7zm1.1-2.7-.8-1.2a.4.4 0 0 1 .7-.4l.8 1.2a3.9 3.9 0 0 1 3 0l.8-1.2a.4.4 0 1 1 .7.4l-.8 1.2" />
      </svg>
      <svg v-else viewBox="0 0 16 16" width="13" height="13" fill="none" stroke="currentColor" stroke-width="1.4">
        <rect x="2" y="2.5" width="12" height="8.5" rx="1.5" />
        <path d="M6 13.5h4M8 11v2.5" stroke-linecap="round" />
      </svg>
    </span>
    <span class="os-badge-text">{{ label }}</span>
  </span>
  <span v-else class="muted">-</span>
</template>

<script setup>
import { computed } from 'vue'

const props = defineProps({
  os: { type: String, default: '' },
})

const label = computed(() => String(props.os || '').trim())

const kind = computed(() => {
  const s = label.value.toLowerCase()
  if (!s) return 'other'
  if (s.includes('win')) return 'windows'
  if (s.includes('mac') || s.includes('darwin') || s.includes('ios') || s.includes('os x')) return 'apple'
  if (s.includes('android')) return 'android'
  if (
    s.includes('linux') ||
    s.includes('ubuntu') ||
    s.includes('debian') ||
    s.includes('centos') ||
    s.includes('fedora') ||
    s.includes('arch') ||
    s.includes('alpine') ||
    s.includes('redhat') ||
    s.includes('rocky') ||
    s.includes('manjaro')
  ) {
    return 'linux'
  }
  return 'other'
})
</script>

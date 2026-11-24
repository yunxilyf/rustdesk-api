<template>
  <span class="user-avatar" :style="avatarStyle" :aria-hidden="true">{{ initials }}</span>
</template>

<script setup>
import { computed } from 'vue'

const PALETTE = [
  ['#1868f2', '#3b82f6'],
  ['#0f766e', '#14b8a6'],
  ['#4f46e5', '#6366f1'],
  ['#0369a1', '#0ea5e9'],
  ['#7c3aed', '#8b5cf6'],
  ['#b45309', '#d97706'],
]

const props = defineProps({
  name: { type: String, default: '' },
  size: { type: Number, default: 28 },
})

const initials = computed(() => {
  const raw = String(props.name || '').trim()
  if (!raw) return '?'
  // 中文取首字，英文取首字母大写
  const first = raw[0]
  return /[a-zA-Z]/.test(first) ? first.toUpperCase() : first
})

const avatarStyle = computed(() => {
  const raw = String(props.name || 'u')
  let hash = 0
  for (let i = 0; i < raw.length; i += 1) {
    hash = (hash * 31 + raw.charCodeAt(i)) >>> 0
  }
  const [c1, c2] = PALETTE[hash % PALETTE.length]
  const fontSize = Math.max(11, Math.round(props.size * 0.44))
  return {
    width: `${props.size}px`,
    height: `${props.size}px`,
    fontSize: `${fontSize}px`,
    background: `linear-gradient(135deg, ${c1}, ${c2})`,
  }
})
</script>

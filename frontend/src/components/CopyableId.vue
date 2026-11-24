<template>
  <span v-if="displayText" class="copy-id" :class="{ 'is-dim': dim }">
    <span class="mono copy-id-text" :title="displayText">{{ displayText }}</span>
    <button
      type="button"
      class="copy-id-btn"
      :class="{ 'is-copied': copied }"
      :title="copied ? t('common.copied') : t('common.copy')"
      :aria-label="`${t('common.copy')} ${displayText}`"
      @click.stop="copy"
    >
      <t-icon :name="copied ? 'check' : 'copy'" size="13px" />
    </button>
  </span>
  <span v-else class="muted">{{ empty }}</span>
</template>

<script setup>
import { computed, onBeforeUnmount, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { t } from '../i18n'

const props = defineProps({
  value: { type: [String, Number], default: '' },
  empty: { type: String, default: '-' },
  dim: { type: Boolean, default: false },
})

const copied = ref(false)
let timer = null

const displayText = computed(() => {
  if (props.value === null || props.value === undefined) return ''
  return String(props.value).trim()
})

async function copy() {
  const text = displayText.value
  if (!text) return
  try {
    if (navigator.clipboard && window.isSecureContext) {
      await navigator.clipboard.writeText(text)
    } else {
      const el = document.createElement('textarea')
      el.value = text
      el.setAttribute('readonly', '')
      el.style.position = 'fixed'
      el.style.opacity = '0'
      document.body.appendChild(el)
      el.select()
      document.execCommand('copy')
      document.body.removeChild(el)
    }
    copied.value = true
    MessagePlugin.success(t('common.copiedValue', { value: text }))
    clearTimeout(timer)
    timer = setTimeout(() => {
      copied.value = false
    }, 1500)
  } catch (e) {
    MessagePlugin.warning(t('common.copyFailed'))
  }
}

onBeforeUnmount(() => clearTimeout(timer))
</script>

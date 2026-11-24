<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ t('fileLogs.title') }}</h2>
        <p class="page-sub">{{ t('fileLogs.sub') }}</p>
      </div>
      <div class="page-head-actions">
        <t-button variant="outline" :loading="loading" @click="load">
          <template #icon><t-icon name="refresh" /></template>
          {{ t('common.refresh') }}
        </t-button>
      </div>
    </div>

    <div class="table-card">
      <div class="card-toolbar">
        <t-input
          v-model="keyword"
          class="filter-input"
          :placeholder="t('fileLogs.searchPlaceholder')"
          clearable
          @enter="search"
          @clear="search"
        >
          <template #prefix-icon><t-icon name="search" /></template>
        </t-input>
        <t-button theme="primary" @click="search">{{ t('common.search') }}</t-button>
      </div>

      <t-table :data="rows" :columns="columns" row-key="id" :loading="loading" hover size="medium">
        <template #direction="{ row }">
          <t-tag :theme="Number(row.direction) === 1 ? 'warning' : 'success'" variant="light" size="small">
            <span class="dir-badge">
              <t-icon :name="Number(row.direction) === 1 ? 'upload' : 'download'" size="12px" />
              <span>{{ Number(row.direction) === 1 ? t('fileLogs.upload') : t('fileLogs.download') }}</span>
            </span>
          </t-tag>
        </template>
        <template #file="{ row }">
          <span v-if="row.file" class="mono">{{ row.file }}</span>
          <span v-else class="muted">{{ t('fileLogs.noFilename') }}</span>
        </template>
        <template #filesize="{ row }">
          <span class="mono text-secondary">{{ fmtSize(row.filesize) }}</span>
        </template>
        <template #remote_id="{ row }">
          <CopyableId :value="row.remote_id" />
        </template>
        <template #user_ip="{ row }">
          <span v-if="row.user_ip" class="mono text-secondary">{{ row.user_ip }}</span>
          <span v-else class="muted">-</span>
        </template>
        <template #logged_at="{ row }">
          <span class="num text-secondary">{{ row.logged_at || '-' }}</span>
        </template>
      </t-table>

      <div class="card-footer">
        <t-pagination
          v-model="page.current"
          v-model:page-size="page.pageSize"
          :total="total"
          :page-size-options="[10, 20, 50, 100]"
          @change="load"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import { t } from '../i18n'
import CopyableId from '../components/CopyableId.vue'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')
const page = reactive({ current: 1, pageSize: 20 })

const columns = computed(() => [
  { colKey: 'file', title: t('fileLogs.colFile'), ellipsis: true, minWidth: 200 },
  { colKey: 'direction', title: t('fileLogs.colDirection'), width: 112 },
  { colKey: 'filesize', title: t('fileLogs.colSize'), width: 108 },
  { colKey: 'remote_id', title: t('fileLogs.colRemoteId'), width: 152 },
  { colKey: 'user_ip', title: t('fileLogs.colSourceIp'), width: 140 },
  { colKey: 'logged_at', title: t('fileLogs.colTime'), width: 186 },
])

function fmtSize(value) {
  // 后端存的是 convert_filesize 生成的可读字符串（如 "1.2 MB"），直接展示；
  // 兼容历史行里的 "0B" 与纯数字字节数。
  if (value === null || value === undefined || value === '') return '-'
  const text = String(value).trim()
  const m = text.match(/^([\d.]+)\s*(B|KB|MB|GB|TB|PB)$/i)
  if (m) {
    const n = Number(m[1]) || 0
    return `${n} ${m[2].toUpperCase()}`
  }
  const bytes = Number(text)
  if (Number.isNaN(bytes)) return text
  const units = ['B', 'KB', 'MB', 'GB', 'TB']
  let i = 0
  let n = bytes
  while (n >= 1024 && i < units.length - 1) {
    n /= 1024
    i += 1
  }
  return `${n.toFixed(n >= 10 || i === 0 ? 0 : 1)} ${units[i]}`
}

async function load() {
  loading.value = true
  try {
    const data = await api.fileLogs({ current: page.current, pageSize: page.pageSize, keyword: keyword.value })
    rows.value = data.list || []
    total.value = data.total || 0
  } catch (e) {
    MessagePlugin.error(e.message || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

function search() {
  page.current = 1
  load()
}

onMounted(load)
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">文件日志</h2>
      </div>
    </div>

    <div class="toolbar">
      <t-input v-model="keyword" placeholder="搜索文件名 / 设备" clearable style="width: 240px" @enter="search" />
      <t-button theme="primary" @click="search">查询</t-button>
      <div class="spacer" />
      <span class="muted">共 {{ total }} 条</span>
    </div>

    <t-table :data="rows" :columns="columns" row-key="id" :loading="loading" hover size="medium">
      <template #direction="{ row }">
        <t-tag :theme="Number(row.direction) === 1 ? 'warning' : 'success'" variant="light" size="small">
          {{ Number(row.direction) === 1 ? '上传' : '下载' }}
        </t-tag>
      </template>
      <template #file="{ row }">
        <span v-if="row.file" class="mono">{{ row.file }}</span>
        <span v-else class="muted">未记录文件名</span>
      </template>
      <template #filesize="{ row }">{{ fmtSize(row.filesize) }}</template>
      <template #remote_id="{ row }"><span class="mono">{{ row.remote_id || '-' }}</span></template>
    </t-table>

    <div class="toolbar" style="justify-content: flex-end; margin-top: 16px">
      <t-pagination v-model="page.current" v-model:page-size="page.pageSize" :total="total" :page-size-options="[10, 20, 50, 100]" @change="load" />
    </div>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')
const page = reactive({ current: 1, pageSize: 20 })

const columns = [
  { colKey: 'file', title: '文件', ellipsis: true },
  { colKey: 'direction', title: '方向', width: 90 },
  { colKey: 'filesize', title: '大小', width: 110 },
  { colKey: 'remote_id', title: '对端设备', width: 170 },
  { colKey: 'user_ip', title: '来源 IP', width: 150 },
  { colKey: 'logged_at', title: '时间', width: 170 },
]

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
    MessagePlugin.error(e.message || '加载失败')
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

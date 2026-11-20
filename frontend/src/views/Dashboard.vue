<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">概览</h2>
      </div>
      <t-button variant="outline" :loading="loading" @click="load">
        <template #icon><t-icon name="refresh" /></template>
        刷新
      </t-button>
    </div>

    <div class="stat-grid">
      <div v-for="card in cards" :key="card.label" class="stat-card">
        <div class="stat-label">{{ card.label }}</div>
        <div class="stat-value">{{ card.value }}</div>
        <div class="muted" style="font-size: 12px; margin-top: 4px">{{ card.hint }}</div>
      </div>
    </div>

    <div class="panel">
      <div class="page-head" style="margin-bottom: 12px">
        <h3 style="margin: 0; font-size: 16px">最近连接</h3>
        <t-link theme="primary" @click="$router.push('/conn-logs')">查看全部</t-link>
      </div>
      <t-table :data="recent" :columns="columns" row-key="id" :loading="loading" size="small" hover>
        <template #conn_start="{ row }">{{ row.conn_start || '-' }}</template>
        <template #duration="{ row }">{{ row.duration || '-' }}</template>
        <template #status="{ row }">
          <t-tag v-if="!row.conn_end" theme="success" variant="light" size="small">进行中</t-tag>
          <span v-else class="muted">已结束</span>
        </template>
      </t-table>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'

const loading = ref(false)
const stats = ref(null)
const recent = ref([])

const columns = [
  { colKey: 'from_id', title: '发起方', ellipsis: true },
  { colKey: 'rid', title: '目标设备', ellipsis: true },
  { colKey: 'conn_start', title: '开始时间', width: 170 },
  { colKey: 'duration', title: '时长', width: 90 },
  { colKey: 'status', title: '状态', width: 100 },
]

const cards = computed(() => {
  const s = stats.value || {}
  const devices = s.devices || {}
  const users = s.users || {}
  const abs = s.addressbooks || {}
  const logs = s.logs || {}
  return [
    { label: '设备总数', value: devices.total ?? '-', hint: `在线 ${devices.online ?? 0}` },
    { label: '用户', value: users.total ?? '-', hint: `启用 ${users.active ?? 0}` },
    { label: '地址簿', value: abs.total ?? '-', hint: `联系人 ${abs.peers ?? 0}` },
    { label: '今日连接', value: logs.conn_today ?? '-', hint: '来自审计日志' },
    { label: '今日文件传输', value: logs.file_today ?? '-', hint: '来自文件日志' },
  ]
})

async function load() {
  loading.value = true
  try {
    const [s, logs] = await Promise.all([api.stats(), api.connLogs({ current: 1, pageSize: 8 })])
    stats.value = s
    recent.value = logs.list || []
  } catch (e) {
    MessagePlugin.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

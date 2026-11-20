<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">连接日志</h2>
      </div>
    </div>

    <div class="toolbar">
      <t-input v-model="filters.keyword" placeholder="搜索设备 / 来源 IP" clearable style="width: 220px" @enter="search" />
      <t-date-range-picker v-model="filters.range" clearable style="width: 280px" @change="search" />
      <t-button theme="primary" @click="search">查询</t-button>
      <div class="spacer" />
      <span class="muted">共 {{ total }} 条</span>
    </div>

    <t-table :data="rows" :columns="columns" row-key="id" :loading="loading" hover size="medium">
      <template #from_id="{ row }"><span class="mono">{{ row.from_id || '-' }}</span></template>
      <template #rid="{ row }"><span class="mono">{{ row.rid || '-' }}</span></template>
      <template #conn_end="{ row }">
        <span v-if="row.conn_end">{{ row.conn_end }}</span>
        <t-tag v-else theme="success" variant="light" size="small">进行中</t-tag>
      </template>
      <template #duration="{ row }">{{ row.duration || '-' }}</template>
      <template #note="{ row }">
        <span v-if="row.note">{{ row.note }}</span>
        <span v-else class="muted">-</span>
      </template>
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
const filters = reactive({ keyword: '', range: [] })
const page = reactive({ current: 1, pageSize: 20 })

const columns = [
  { colKey: 'from_ip', title: '来源 IP', width: 150 },
  { colKey: 'from_id', title: '发起方', width: 170 },
  { colKey: 'rid', title: '目标设备', width: 170 },
  { colKey: 'conn_start', title: '开始时间', width: 170 },
  { colKey: 'conn_end', title: '结束时间', width: 170 },
  { colKey: 'duration', title: '时长', width: 90 },
  { colKey: 'note', title: '备注', ellipsis: true },
]

async function load() {
  loading.value = true
  try {
    const [start, end] = filters.range || []
    const data = await api.connLogs({
      current: page.current,
      pageSize: page.pageSize,
      keyword: filters.keyword,
      start,
      end,
    })
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

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ t('connLogs.title') }}</h2>
        <p class="page-sub">{{ t('connLogs.sub') }}</p>
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
          v-model="filters.keyword"
          class="filter-input"
          :placeholder="t('connLogs.searchPlaceholder')"
          clearable
          @enter="search"
          @clear="search"
        >
          <template #prefix-icon><t-icon name="search" /></template>
        </t-input>
        <t-date-range-picker v-model="filters.range" class="filter-range" clearable @change="search" />
        <t-button theme="primary" @click="search">{{ t('common.search') }}</t-button>
      </div>

      <t-table :data="rows" :columns="columns" row-key="id" :loading="loading" hover size="medium">
        <template #from_ip="{ row }">
          <span v-if="row.from_ip" class="mono text-secondary">{{ row.from_ip }}</span>
          <span v-else class="muted">-</span>
        </template>
        <template #flow="{ row }">
          <div class="flow-cell">
            <CopyableId :value="row.from_id" dim />
            <span class="flow-arrow"><t-icon name="arrow-right" size="13px" /></span>
            <CopyableId :value="row.rid" />
          </div>
        </template>
        <template #conn_start="{ row }">
          <span class="num text-secondary">{{ row.conn_start || '-' }}</span>
        </template>
        <template #conn_end="{ row }">
          <span v-if="row.conn_end" class="num text-secondary">{{ row.conn_end }}</span>
          <StatusDot v-else status="active" :label="t('common.inProgress')" />
        </template>
        <template #duration="{ row }">
          <span class="mono">{{ row.duration || '-' }}</span>
        </template>
        <template #note="{ row }">
          <span v-if="row.note">{{ row.note }}</span>
          <span v-else class="muted">-</span>
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
import StatusDot from '../components/StatusDot.vue'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const filters = reactive({ keyword: '', range: [] })
const page = reactive({ current: 1, pageSize: 20 })

const columns = computed(() => [
  { colKey: 'from_ip', title: t('connLogs.colSourceIp'), width: 136 },
  { colKey: 'flow', title: t('connLogs.colFlow'), minWidth: 276 },
  { colKey: 'conn_start', title: t('connLogs.colStart'), width: 186 },
  { colKey: 'conn_end', title: t('connLogs.colEndStatus'), width: 186 },
  { colKey: 'duration', title: t('connLogs.colDuration'), width: 96 },
  { colKey: 'note', title: t('common.note'), ellipsis: true },
])

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

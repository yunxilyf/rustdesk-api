<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ t('dashboard.title') }}</h2>
        <p class="page-sub">{{ t('dashboard.sub') }}</p>
      </div>
      <div class="page-head-actions">
        <t-button variant="outline" :loading="loading" @click="load">
          <template #icon><t-icon name="refresh" /></template>
          {{ t('common.refresh') }}
        </t-button>
      </div>
    </div>

    <div class="stat-grid">
      <div
        v-for="card in cards"
        :key="card.key"
        class="stat-card"
        role="button"
        tabindex="0"
        @click="$router.push(card.to)"
        @keydown.enter="$router.push(card.to)"
      >
        <div>
          <div class="stat-card-top">
            <span class="stat-label">{{ card.label }}</span>
            <span class="stat-icon" :class="`accent-${card.accent}`">
              <t-icon :name="card.icon" size="18px" />
            </span>
          </div>
          <div class="stat-value">{{ card.value }}</div>
        </div>

        <div v-if="card.ratio !== null" class="stat-progress">
          <div class="stat-progress-head">
            <span>{{ card.hint }}</span>
            <span class="num">{{ card.ratio }}%</span>
          </div>
          <div class="stat-bar">
            <div class="stat-bar-fill" :style="{ width: `${card.ratio}%` }" />
          </div>
        </div>
        <div v-else class="stat-foot">
          <span>{{ card.hint }}</span>
          <t-icon name="chevron-right" size="14px" />
        </div>
      </div>
    </div>

    <div class="dash-grid">
      <div class="panel">
        <div class="panel-head">
          <div>
            <h3 class="panel-title">{{ t('dashboard.recentConnTitle') }}</h3>
            <div class="panel-sub">{{ t('dashboard.recentConnSub') }}</div>
          </div>
          <t-link theme="primary" @click="$router.push('/conn-logs')">{{ t('common.viewAll') }}</t-link>
        </div>

        <t-table :data="recent" :columns="columns" row-key="id" :loading="loading" size="small" hover>
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
          <template #duration="{ row }">
            <span class="mono">{{ row.duration || '-' }}</span>
          </template>
          <template #status="{ row }">
            <StatusDot v-if="!row.conn_end" status="active" :label="t('common.inProgress')" />
            <StatusDot v-else status="neutral" :label="t('common.ended')" :pulse="false" />
          </template>
        </t-table>
      </div>

      <div class="dash-side">
        <div class="panel">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">{{ t('dashboard.onlineDevicesTitle') }}</h3>
              <div class="panel-sub">{{ t('dashboard.onlineDevicesSub') }}</div>
            </div>
            <t-link theme="primary" @click="$router.push('/devices')">{{ t('dashboard.allDevices') }}</t-link>
          </div>

          <div v-if="onlineDevices.length" class="online-list">
            <div v-for="dev in onlineDevices" :key="dev.rid" class="online-item">
              <div class="online-item-main">
                <div class="online-item-name">
                  <StatusDot status="online" />
                  <span class="online-item-host" :title="dev.hostname || dev.rid">{{ dev.hostname || dev.rid }}</span>
                </div>
                <div class="online-item-meta">
                  <CopyableId :value="dev.rid" dim />
                  <span v-if="dev.os" class="online-item-os" :title="dev.os">· {{ dev.os }}</span>
                </div>
              </div>
              <t-tag v-if="dev.owner" variant="light" size="small">{{ dev.owner }}</t-tag>
            </div>
          </div>
          <div v-else class="empty-state">
            <div class="empty-state-icon"><t-icon name="desktop" size="18px" /></div>
            <div>{{ loading ? t('dashboard.loadingOnline') : t('dashboard.noOnline') }}</div>
          </div>
        </div>

        <div class="panel">
          <div class="panel-head">
            <div>
              <h3 class="panel-title">{{ t('dashboard.quickActionsTitle') }}</h3>
              <div class="panel-sub">{{ t('dashboard.quickActionsSub') }}</div>
            </div>
          </div>
          <div class="quick-actions">
            <button type="button" class="quick-action-btn" @click="openWebClient">
              <t-icon name="internet" size="16px" />
              <span>{{ t('dashboard.quickWeb') }}</span>
            </button>
            <button type="button" class="quick-action-btn" @click="$router.push('/devices')">
              <t-icon name="desktop" size="16px" />
              <span>{{ t('dashboard.quickDevices') }}</span>
            </button>
            <button type="button" class="quick-action-btn" @click="$router.push('/addressbooks')">
              <t-icon name="book" size="16px" />
              <span>{{ t('dashboard.quickAb') }}</span>
            </button>
            <button
              type="button"
              class="quick-action-btn"
              @click="$router.push(isAdmin ? '/users' : '/settings')"
            >
              <t-icon :name="isAdmin ? 'usergroup' : 'setting'" size="16px" />
              <span>{{ isAdmin ? t('dashboard.quickUsers') : t('dashboard.quickSettings') }}</span>
            </button>
          </div>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import { store } from '../store'
import { t } from '../i18n'
import CopyableId from '../components/CopyableId.vue'
import StatusDot from '../components/StatusDot.vue'

const isAdmin = computed(() => !!store.user?.is_admin)
const loading = ref(false)
const stats = ref(null)
const recent = ref([])
const onlineDevices = ref([])

const columns = computed(() => [
  { colKey: 'flow', title: t('dashboard.colFlow'), minWidth: 270 },
  { colKey: 'conn_start', title: t('dashboard.colStart'), width: 168 },
  { colKey: 'duration', title: t('dashboard.colDuration'), width: 92 },
  { colKey: 'status', title: t('common.status'), width: 102 },
])

const cards = computed(() => {
  const s = stats.value || {}
  const devices = s.devices || {}
  const users = s.users || {}
  const abs = s.addressbooks || {}
  const logs = s.logs || {}
  const devTotal = Number(devices.total) || 0
  const devOnline = Number(devices.online) || 0
  const onlineRatio = devTotal > 0 ? Math.min(100, Math.round((devOnline / devTotal) * 100)) : 0

  return [
    {
      key: 'devices',
      label: t('dashboard.statDevices'),
      value: devices.total ?? '-',
      hint: t('dashboard.statDevicesHint', { count: devOnline }),
      ratio: devices.total !== undefined ? onlineRatio : null,
      icon: 'desktop',
      accent: 'blue',
      to: '/devices',
    },
    {
      key: 'users',
      label: t('dashboard.statUsers'),
      value: users.total ?? '-',
      hint: t('dashboard.statUsersHint', { count: users.active ?? 0 }),
      ratio: null,
      icon: 'usergroup',
      accent: 'indigo',
      to: isAdmin.value ? '/users' : '/settings',
    },
    {
      key: 'addressbooks',
      label: t('dashboard.statAddressbooks'),
      value: abs.total ?? '-',
      hint: t('dashboard.statAddressbooksHint', { count: abs.peers ?? 0 }),
      ratio: null,
      icon: 'book',
      accent: 'teal',
      to: '/addressbooks',
    },
    {
      key: 'conn',
      label: t('dashboard.statConnToday'),
      value: logs.conn_today ?? '-',
      hint: t('dashboard.statConnTodayHint'),
      ratio: null,
      icon: 'history',
      accent: 'amber',
      to: '/conn-logs',
    },
    {
      key: 'files',
      label: t('dashboard.statFileToday'),
      value: logs.file_today ?? '-',
      hint: t('dashboard.statFileTodayHint'),
      ratio: null,
      icon: 'file',
      accent: 'green',
      to: '/file-logs',
    },
  ]
})

function openWebClient() {
  window.open('/web/', '_blank', 'noopener')
}

async function load() {
  loading.value = true
  try {
    const [s, logs, devs] = await Promise.all([
      api.stats(),
      api.connLogs({ current: 1, pageSize: 8 }),
      api.devices({ current: 1, pageSize: 6, status: 'online' }),
    ])
    stats.value = s
    recent.value = logs.list || []
    onlineDevices.value = devs.list || []
  } catch (e) {
    MessagePlugin.error(e.message || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(load)
</script>

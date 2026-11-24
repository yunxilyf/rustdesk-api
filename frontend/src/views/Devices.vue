<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ t('devices.title') }}</h2>
        <p class="page-sub">{{ t('devices.sub') }}</p>
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
          :placeholder="t('devices.searchPlaceholder')"
          clearable
          @enter="search"
          @clear="search"
        >
          <template #prefix-icon><t-icon name="search" /></template>
        </t-input>
        <t-select v-model="filters.status" class="filter-select" :options="statusOptions" @change="search" />
        <t-button theme="primary" @click="search">{{ t('common.search') }}</t-button>
      </div>

      <t-table :data="rows" :columns="columns" row-key="rid" :loading="loading" hover size="medium">
        <template #online="{ row }">
          <StatusDot :status="row.online ? 'online' : 'offline'" :label="row.online ? t('common.online') : t('common.offline')" />
        </template>
        <template #rid="{ row }">
          <CopyableId :value="row.rid" />
        </template>
        <template #hostname="{ row }">
          <span v-if="row.hostname">{{ row.hostname }}</span>
          <span v-else class="muted">-</span>
        </template>
        <template #os="{ row }">
          <OsBadge :os="row.os" />
        </template>
        <template #version="{ row }">
          <t-tag v-if="row.version" variant="light" size="small" class="mono">{{ row.version }}</t-tag>
          <span v-else class="muted">-</span>
        </template>
        <template #owner="{ row }">
          <span v-if="row.owner">{{ row.owner }}</span>
          <span v-else class="muted">{{ t('devices.unassigned') }}</span>
        </template>
        <template #update_time="{ row }">
          <span class="num text-secondary">{{ row.update_time || '-' }}</span>
        </template>
        <template #op="{ row }">
          <t-link theme="primary" @click="openDetail(row)">{{ t('common.detail') }}</t-link>
          <t-link v-if="isAdmin" theme="primary" class="link-gap" @click="openOwner(row)">{{ t('devices.assignOwner') }}</t-link>
        </template>
      </t-table>

      <div class="card-footer">
        <t-pagination
          v-model="page.current"
          v-model:page-size="page.pageSize"
          :total="total"
          :page-size-options="[10, 20, 50]"
          @change="load"
        />
      </div>
    </div>

    <t-drawer v-model:visible="detailVisible" :header="detailHeader" size="460px" :footer="false">
      <template v-if="detailRow">
        <div class="drawer-section-title">{{ t('devices.sectionBasic') }}</div>
        <div class="detail-list">
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.fieldOnlineStatus') }}</span>
            <span class="detail-val">
              <StatusDot
                :status="detailRow.online ? 'online' : 'offline'"
                :label="detailRow.online ? t('common.online') : t('common.offline')"
              />
            </span>
          </div>
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.colRid') }}</span>
            <span class="detail-val"><CopyableId :value="detailRow.rid" /></span>
          </div>
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.colHostname') }}</span>
            <span class="detail-val">{{ detailRow.hostname || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.colSysUser') }}</span>
            <span class="detail-val">{{ detailRow.username || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.fieldOwnerAccount') }}</span>
            <span class="detail-val">{{ detailRow.owner || t('devices.unassigned') }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.colLastSeen') }}</span>
            <span class="detail-val num">{{ detailRow.update_time || '-' }}</span>
          </div>
        </div>

        <div class="drawer-section-title">{{ t('devices.sectionHardware') }}</div>
        <div class="detail-list">
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.colOs') }}</span>
            <span class="detail-val"><OsBadge :os="detailRow.os" /></span>
          </div>
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.fieldClientVersion') }}</span>
            <span class="detail-val mono">{{ detailRow.version || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.fieldCpu') }}</span>
            <span class="detail-val">{{ detailRow.cpu || '-' }}</span>
          </div>
          <div class="detail-row">
            <span class="detail-key">{{ t('devices.fieldMemory') }}</span>
            <span class="detail-val">{{ detailRow.memory || '-' }}</span>
          </div>
        </div>

        <div class="drawer-actions">
          <t-button v-if="isAdmin" theme="primary" @click="openOwnerFromDetail">{{ t('devices.setOwnerBtn') }}</t-button>
          <t-button variant="outline" @click="openWebClient">
            <template #icon><t-icon name="internet" /></template>
            {{ t('devices.openWebBtn') }}
          </t-button>
        </div>
      </template>
    </t-drawer>

    <t-dialog
      v-model:visible="ownerVisible"
      :header="t('devices.ownerDialogTitle')"
      :confirm-btn="{ content: t('common.save'), theme: 'primary' }"
      @confirm="saveOwner"
    >
      <t-form label-width="90px">
        <t-form-item :label="t('devices.colRid')"><span class="mono">{{ ownerRow?.rid }}</span></t-form-item>
        <t-form-item :label="t('devices.ownerField')">
          <t-select
            v-model="ownerUserId"
            :options="userOptions"
            :placeholder="t('devices.ownerPlaceholder')"
            clearable
            filterable
            class="full-width"
          />
        </t-form-item>
      </t-form>
    </t-dialog>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import { store } from '../store'
import { t } from '../i18n'
import CopyableId from '../components/CopyableId.vue'
import OsBadge from '../components/OsBadge.vue'
import StatusDot from '../components/StatusDot.vue'

const isAdmin = computed(() => !!store.user?.is_admin)
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const users = ref([])
const filters = reactive({ keyword: '', status: '' })
const page = reactive({ current: 1, pageSize: 20 })

const statusOptions = computed(() => [
  { label: t('devices.statusAll'), value: '' },
  { label: t('common.online'), value: 'online' },
  { label: t('common.offline'), value: 'offline' },
])

const columns = computed(() => [
  { colKey: 'online', title: t('common.status'), width: 92 },
  { colKey: 'rid', title: t('devices.colRid'), width: 142 },
  { colKey: 'hostname', title: t('devices.colHostname'), ellipsis: true, minWidth: 126 },
  { colKey: 'username', title: t('devices.colSysUser'), width: 88, ellipsis: true },
  { colKey: 'os', title: t('devices.colOs'), ellipsis: true, minWidth: 162 },
  { colKey: 'version', title: t('devices.colVersion'), width: 82 },
  { colKey: 'owner', title: t('devices.colOwner'), width: 112, ellipsis: true },
  { colKey: 'update_time', title: t('devices.colLastSeen'), width: 184 },
  { colKey: 'op', title: t('common.actions'), width: isAdmin.value ? 142 : 84 },
])

const userOptions = computed(() => users.value.map((u) => ({ label: u.display_name || u.username, value: u.id })))
const detailVisible = ref(false)
const detailRow = ref(null)
const detailHeader = computed(() =>
  detailRow.value
    ? t('devices.detailHeaderWithName', { name: detailRow.value.hostname || detailRow.value.rid })
    : t('devices.detailHeader'),
)

const ownerVisible = ref(false)
const ownerRow = ref(null)
const ownerUserId = ref(null)

async function load() {
  loading.value = true
  try {
    const data = await api.devices({
      current: page.current,
      pageSize: page.pageSize,
      keyword: filters.keyword,
      status: filters.status,
    })
    rows.value = data.list || []
    total.value = data.total || 0
    if (detailRow.value) {
      const updated = rows.value.find((r) => r.rid === detailRow.value.rid)
      if (updated) detailRow.value = updated
    }
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

async function loadUsers() {
  if (!isAdmin.value) return
  try {
    const data = await api.users({ current: 1, pageSize: 200 })
    users.value = data.list || []
  } catch (e) {
    /* ignore */
  }
}

function openDetail(row) {
  detailRow.value = row
  detailVisible.value = true
}

function openOwner(row) {
  ownerRow.value = row
  ownerUserId.value = row.owner_id || null
  ownerVisible.value = true
}

function openOwnerFromDetail() {
  if (detailRow.value) openOwner(detailRow.value)
}

function openWebClient() {
  window.open('/web/', '_blank', 'noopener')
}

async function saveOwner() {
  try {
    await api.setDeviceOwner(ownerRow.value.rid, ownerUserId.value)
    MessagePlugin.success(t('common.saved'))
    ownerVisible.value = false
    load()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
  }
}

onMounted(() => {
  load()
  loadUsers()
})
</script>

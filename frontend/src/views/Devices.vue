<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">设备</h2>
      </div>
      <t-button variant="outline" :loading="loading" @click="load">
        <template #icon><t-icon name="refresh" /></template>
        刷新
      </t-button>
    </div>

    <div class="toolbar">
      <t-input v-model="filters.keyword" placeholder="搜索 ID / 主机名 / 用户名" clearable style="width: 260px" @enter="search" />
      <t-select v-model="filters.status" :options="statusOptions" style="width: 140px" @change="search" />
      <t-button theme="primary" @click="search">查询</t-button>
      <div class="spacer" />
      <span class="muted">共 {{ total }} 台</span>
    </div>

    <t-table :data="rows" :columns="columns" row-key="rid" :loading="loading" hover size="medium">
      <template #online="{ row }">
        <t-tag :theme="row.online ? 'success' : 'default'" variant="light" size="small">
          {{ row.online ? '在线' : '离线' }}
        </t-tag>
      </template>
      <template #rid="{ row }"><span class="mono">{{ row.rid }}</span></template>
      <template #owner="{ row }">
        <span v-if="row.owner">{{ row.owner }}</span>
        <span v-else class="muted">未归属</span>
      </template>
      <template #op="{ row }">
        <t-link v-if="isAdmin" theme="primary" @click="openOwner(row)">归属</t-link>
        <span v-else class="muted">-</span>
      </template>
    </t-table>

    <div class="toolbar" style="justify-content: flex-end; margin-top: 16px">
      <t-pagination v-model="page.current" v-model:page-size="page.pageSize" :total="total" :page-size-options="[10, 20, 50]" @change="load" />
    </div>

    <t-dialog v-model:visible="ownerVisible" header="设置设备归属" :confirm-btn="{ content: '保存', theme: 'primary' }" @confirm="saveOwner">
      <t-form label-width="80px">
        <t-form-item label="设备 ID"><span class="mono">{{ ownerRow?.rid }}</span></t-form-item>
        <t-form-item label="归属用户">
          <t-select v-model="ownerUserId" :options="userOptions" placeholder="选择用户（留空=解除归属）" clearable filterable style="width: 100%" />
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

const isAdmin = computed(() => !!store.user?.is_admin)
const loading = ref(false)
const rows = ref([])
const total = ref(0)
const users = ref([])
const filters = reactive({ keyword: '', status: '' })
const page = reactive({ current: 1, pageSize: 20 })

const statusOptions = [
  { label: '全部状态', value: '' },
  { label: '在线', value: 'online' },
  { label: '离线', value: 'offline' },
]

const columns = computed(() => {
  const cols = [
    { colKey: 'online', title: '状态', width: 90 },
    { colKey: 'rid', title: '设备 ID', width: 180 },
    { colKey: 'hostname', title: '主机名', ellipsis: true },
    { colKey: 'username', title: '系统用户', width: 130, ellipsis: true },
    { colKey: 'os', title: '系统', ellipsis: true },
    { colKey: 'version', title: '版本', width: 100 },
    { colKey: 'owner', title: '归属', width: 130 },
    { colKey: 'update_time', title: '最后上报', width: 170 },
  ]
  if (isAdmin.value) cols.push({ colKey: 'op', title: '操作', width: 80 })
  return cols
})

const userOptions = computed(() => users.value.map((u) => ({ label: u.display_name || u.username, value: u.id })))
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

async function loadUsers() {
  if (!isAdmin.value) return
  try {
    const data = await api.users({ current: 1, pageSize: 200 })
    users.value = data.list || []
  } catch (e) {
    /* ignore */
  }
}

function openOwner(row) {
  ownerRow.value = row
  ownerUserId.value = row.owner_id || null
  ownerVisible.value = true
}

async function saveOwner() {
  try {
    await api.setDeviceOwner(ownerRow.value.rid, ownerUserId.value)
    MessagePlugin.success('已保存')
    ownerVisible.value = false
    load()
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  }
}

onMounted(() => {
  load()
  loadUsers()
})
</script>

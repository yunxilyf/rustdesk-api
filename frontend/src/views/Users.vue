<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ t('users.title') }}</h2>
        <p class="page-sub">{{ t('users.sub') }}</p>
      </div>
      <div class="page-head-actions">
        <t-button theme="primary" @click="openDialog()">
          <template #icon><t-icon name="add" /></template>
          {{ t('users.createBtn') }}
        </t-button>
      </div>
    </div>

    <div class="table-card">
      <div class="card-toolbar">
        <t-input
          v-model="keyword"
          class="filter-input"
          :placeholder="t('users.searchPlaceholder')"
          clearable
          @enter="search"
          @clear="search"
        >
          <template #prefix-icon><t-icon name="search" /></template>
        </t-input>
        <t-button theme="primary" @click="search">{{ t('common.search') }}</t-button>
      </div>

      <t-table :data="rows" :columns="columns" row-key="id" :loading="loading" hover>
        <template #username="{ row }">
          <div class="user-cell">
            <UserAvatar :name="row.display_name || row.username" :size="30" />
            <div class="user-cell-meta">
              <div class="user-cell-primary">{{ row.display_name || row.username }}</div>
              <div class="user-cell-sub mono">@{{ row.username }}</div>
            </div>
          </div>
        </template>
        <template #email="{ row }">
          <span v-if="row.email" class="text-secondary">{{ row.email }}</span>
          <span v-else class="muted">-</span>
        </template>
        <template #device_count="{ row }">
          <t-tag variant="light" size="small" class="num">{{ t('users.deviceUnit', { count: row.device_count ?? 0 }) }}</t-tag>
        </template>
        <template #is_admin="{ row }">
          <t-tag v-if="row.is_admin" theme="primary" variant="light" size="small">{{ t('common.admin') }}</t-tag>
          <t-tag v-else theme="default" variant="light" size="small">{{ t('common.user') }}</t-tag>
        </template>
        <template #is_active="{ row }">
          <StatusDot :status="statusKind(row)" :label="statusLabel(row)" :pulse="false" />
        </template>
        <template #op="{ row }">
          <t-link theme="primary" @click="openDialog(row)">{{ t('common.edit') }}</t-link>
          <t-popconfirm v-if="row.id !== store.user?.id" :content="t('users.deleteConfirm')" @confirm="remove(row)">
            <t-link theme="danger" class="link-gap">{{ t('common.delete') }}</t-link>
          </t-popconfirm>
        </template>
      </t-table>

      <div class="card-footer">
        <t-pagination v-model="page.current" v-model:page-size="page.pageSize" :total="total" @change="load" />
      </div>
    </div>

    <t-dialog
      v-model:visible="dialog"
      :header="form.id ? t('users.editTitle') : t('users.createTitle')"
      :confirm-btn="{ content: t('common.save'), theme: 'primary' }"
      @confirm="save"
    >
      <t-form label-width="106px">
        <t-form-item :label="t('users.fieldUsername')">
          <t-input v-model="form.username" :disabled="!!form.id" :placeholder="t('users.usernamePlaceholder')" />
        </t-form-item>
        <t-form-item :label="form.id ? t('users.fieldResetPassword') : t('users.fieldPassword')">
          <t-input
            v-model="form.password"
            type="password"
            :placeholder="form.id ? t('users.passwordKeepPlaceholder') : t('users.passwordMinPlaceholder')"
          />
        </t-form-item>
        <t-form-item :label="t('users.fieldDisplayName')"><t-input v-model="form.display_name" /></t-form-item>
        <t-form-item :label="t('users.fieldEmail')"><t-input v-model="form.email" :placeholder="t('users.emailPlaceholder')" /></t-form-item>
        <t-form-item :label="t('common.note')"><t-input v-model="form.note" /></t-form-item>
        <t-form-item :label="t('users.fieldAdmin')"><t-switch v-model="form.is_admin" /></t-form-item>
        <t-form-item :label="t('users.fieldActive')"><t-switch v-model="form.is_active" /></t-form-item>
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
import StatusDot from '../components/StatusDot.vue'
import UserAvatar from '../components/UserAvatar.vue'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')
const page = reactive({ current: 1, pageSize: 20 })

const columns = computed(() => [
  { colKey: 'username', title: t('users.colAccount'), minWidth: 220 },
  { colKey: 'email', title: t('users.colEmail'), ellipsis: true },
  { colKey: 'device_count', title: t('users.colDevices'), width: 110 },
  { colKey: 'is_admin', title: t('users.colRole'), width: 110 },
  { colKey: 'is_active', title: t('common.status'), width: 112 },
  { colKey: 'op', title: t('common.actions'), width: 132 },
])

function statusKind(row) {
  if (!row.is_active) return 'offline'
  const st = Number(row.status ?? 1)
  if (st === 0) return 'offline'
  if (st === -1) return 'warning'
  return 'online'
}

function statusLabel(row) {
  const kind = statusKind(row)
  if (kind === 'online') return t('users.statusActive')
  if (kind === 'warning') return t('users.statusUnverified')
  return t('users.statusDisabled')
}

async function load() {
  loading.value = true
  try {
    const data = await api.users({ current: page.current, pageSize: page.pageSize, keyword: keyword.value })
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

const dialog = ref(false)
const form = reactive({
  id: null,
  username: '',
  password: '',
  display_name: '',
  email: '',
  note: '',
  is_admin: false,
  is_active: true,
})

function openDialog(row) {
  form.id = row?.id || null
  form.username = row?.username || ''
  form.password = ''
  form.display_name = row?.display_name || ''
  form.email = row?.email || ''
  form.note = row?.note || ''
  form.is_admin = !!row?.is_admin
  form.is_active = row ? !!row.is_active : true
  dialog.value = true
}

async function save() {
  if (!form.username.trim()) {
    MessagePlugin.warning(t('users.warnUsername'))
    return
  }
  if (!form.id && form.password.length < 6) {
    MessagePlugin.warning(t('users.warnPasswordLen'))
    return
  }
  const body = {
    username: form.username.trim(),
    display_name: form.display_name,
    email: form.email,
    note: form.note,
    is_admin: form.is_admin,
    is_active: form.is_active,
  }
  if (form.password) body.password = form.password
  try {
    if (form.id) await api.updateUser(form.id, body)
    else await api.createUser(body)
    MessagePlugin.success(t('common.saved'))
    dialog.value = false
    load()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
  }
}

async function remove(row) {
  try {
    await api.deleteUser(row.id)
    MessagePlugin.success(t('common.deleted'))
    load()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.deleteFailed'))
  }
}

onMounted(load)
</script>

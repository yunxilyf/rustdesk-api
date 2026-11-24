<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ t('groups.title') }}</h2>
        <p class="page-sub">{{ t('groups.sub') }}</p>
      </div>
      <div class="page-head-actions">
        <t-button theme="primary" @click="openDialog()">
          <template #icon><t-icon name="add" /></template>
          {{ t('groups.createBtn') }}
        </t-button>
      </div>
    </div>

    <div class="table-card">
      <t-table :data="rows" :columns="columns" row-key="guid" :loading="loading" hover>
        <template #owner="{ row }">
          <span v-if="row.owner">{{ row.owner }}</span>
          <span v-else class="muted">{{ t('groups.publicOwner') }}</span>
        </template>
        <template #member_count="{ row }">
          <t-tag variant="light" size="small" class="num">{{ t('groups.countUnit', { count: row.member_count }) }}</t-tag>
        </template>
        <template #note="{ row }">
          <span v-if="row.note">{{ row.note }}</span>
          <span v-else class="muted">-</span>
        </template>
        <template #op="{ row }">
          <t-link theme="primary" @click="openMembers(row)">{{ t('groups.members') }}</t-link>
          <t-link theme="primary" class="link-gap" @click="openDialog(row)">{{ t('common.edit') }}</t-link>
          <t-popconfirm :content="t('groups.deleteConfirm')" @confirm="remove(row)">
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
      :header="form.guid ? t('groups.editTitle') : t('groups.createTitle')"
      :confirm-btn="{ content: t('common.save'), theme: 'primary' }"
      @confirm="save"
    >
      <t-form label-width="84px">
        <t-form-item :label="t('common.name')"><t-input v-model="form.name" :placeholder="t('groups.namePlaceholder')" /></t-form-item>
        <t-form-item :label="t('common.note')"><t-input v-model="form.note" :placeholder="t('common.optional')" /></t-form-item>
      </t-form>
    </t-dialog>

    <t-drawer v-model:visible="drawer" :header="t('groups.drawerTitle', { name: current?.name || '' })" size="500px" :footer="false">
      <div class="toolbar">
        <t-input v-model="newRid" :placeholder="t('groups.addRidPlaceholder')" clearable class="spacer" @enter="addMember" />
        <t-button theme="primary" @click="addMember">{{ t('common.add') }}</t-button>
      </div>
      <t-table v-if="loadingMembers || members.length" :data="members" :columns="memberColumns" row-key="rid" size="small" :loading="loadingMembers" hover>
        <template #rid="{ row }"><CopyableId :value="row.rid" /></template>
        <template #op="{ row }">
          <t-popconfirm :content="t('groups.removeMemberConfirm')" @confirm="removeMember(row)">
            <t-link theme="danger">{{ t('groups.removeMember') }}</t-link>
          </t-popconfirm>
        </template>
      </t-table>
      <div v-else class="empty-state">
        <div class="empty-state-icon"><t-icon name="folder" size="18px" /></div>
        <div>{{ t('groups.emptyMembers') }}</div>
      </div>
    </t-drawer>
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
const page = reactive({ current: 1, pageSize: 20 })

const columns = computed(() => [
  { colKey: 'name', title: t('groups.colName'), minWidth: 180 },
  { colKey: 'owner', title: t('groups.colOwner'), width: 140 },
  { colKey: 'member_count', title: t('groups.colCount'), width: 110 },
  { colKey: 'note', title: t('common.note'), ellipsis: true },
  { colKey: 'op', title: t('common.actions'), width: 210 },
])

async function load() {
  loading.value = true
  try {
    const data = await api.groups({ current: page.current, pageSize: page.pageSize })
    rows.value = data.list || []
    total.value = data.total || 0
  } catch (e) {
    MessagePlugin.error(e.message || t('common.loadFailed'))
  } finally {
    loading.value = false
  }
}

const dialog = ref(false)
const form = reactive({ guid: '', name: '', note: '' })
function openDialog(row) {
  form.guid = row?.guid || ''
  form.name = row?.name || ''
  form.note = row?.note || ''
  dialog.value = true
}
async function save() {
  if (!form.name.trim()) {
    MessagePlugin.warning(t('common.fillName'))
    return
  }
  try {
    if (form.guid) await api.updateGroup(form.guid, { name: form.name, note: form.note })
    else await api.createGroup({ name: form.name, note: form.note })
    MessagePlugin.success(t('common.saved'))
    dialog.value = false
    load()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
  }
}
async function remove(row) {
  try {
    await api.deleteGroup(row.guid)
    MessagePlugin.success(t('common.deleted'))
    load()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.deleteFailed'))
  }
}

const drawer = ref(false)
const current = ref(null)
const members = ref([])
const loadingMembers = ref(false)
const newRid = ref('')
const memberColumns = computed(() => [
  { colKey: 'rid', title: t('groups.colRid'), width: 170 },
  { colKey: 'alias', title: t('groups.colAlias'), ellipsis: true },
  { colKey: 'hostname', title: t('groups.colHostname'), ellipsis: true },
  { colKey: 'op', title: t('common.actions'), width: 84 },
])

async function openMembers(row) {
  current.value = row
  drawer.value = true
  await loadMembers()
}
async function loadMembers() {
  if (!current.value) return
  loadingMembers.value = true
  try {
    const data = await api.groupMembers(current.value.guid)
    members.value = data.list || []
  } catch (e) {
    MessagePlugin.error(e.message || t('groups.loadMembersFailed'))
  } finally {
    loadingMembers.value = false
  }
}
async function addMember() {
  if (!newRid.value.trim()) return
  try {
    await api.addGroupMembers(current.value.guid, [newRid.value.trim()])
    newRid.value = ''
    MessagePlugin.success(t('common.added'))
    await Promise.all([loadMembers(), load()])
  } catch (e) {
    MessagePlugin.error(e.message || t('common.addFailed'))
  }
}
async function removeMember(row) {
  try {
    await api.removeGroupMembers(current.value.guid, [row.rid])
    MessagePlugin.success(t('groups.removedMember'))
    await Promise.all([loadMembers(), load()])
  } catch (e) {
    MessagePlugin.error(e.message || t('groups.removeMemberFailed'))
  }
}

onMounted(load)
</script>

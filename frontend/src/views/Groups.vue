<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">设备分组</h2>
      </div>
      <t-button theme="primary" @click="openDialog()">
        <template #icon><t-icon name="add" /></template>
        新建分组
      </t-button>
    </div>

    <t-table :data="rows" :columns="columns" row-key="guid" :loading="loading" hover>
      <template #member_count="{ row }">{{ row.member_count }}</template>
      <template #op="{ row }">
        <t-link theme="primary" @click="openMembers(row)">成员</t-link>
        <t-link theme="primary" style="margin-left: 10px" @click="openDialog(row)">编辑</t-link>
        <t-popconfirm content="确认删除该分组？" @confirm="remove(row)">
          <t-link theme="danger" style="margin-left: 10px">删除</t-link>
        </t-popconfirm>
      </template>
    </t-table>

    <div class="toolbar" style="justify-content: flex-end; margin-top: 16px">
      <t-pagination v-model="page.current" v-model:page-size="page.pageSize" :total="total" @change="load" />
    </div>

    <t-dialog v-model:visible="dialog" :header="form.guid ? '编辑分组' : '新建分组'" :confirm-btn="{ content: '保存', theme: 'primary' }" @confirm="save">
      <t-form label-width="80px">
        <t-form-item label="名称"><t-input v-model="form.name" placeholder="例如：财务部" /></t-form-item>
        <t-form-item label="备注"><t-input v-model="form.note" /></t-form-item>
      </t-form>
    </t-dialog>

    <t-drawer v-model:visible="drawer" :header="`成员 · ${current?.name || ''}`" size="480px" :footer="false">
      <div class="toolbar">
        <t-input v-model="newRid" placeholder="输入设备 ID 后回车添加" clearable @enter="addMember" />
        <t-button theme="primary" @click="addMember">添加</t-button>
      </div>
      <t-table :data="members" :columns="memberColumns" row-key="rid" size="small" :loading="loadingMembers">
        <template #rid="{ row }"><span class="mono">{{ row.rid }}</span></template>
        <template #op="{ row }">
          <t-popconfirm content="确认移出该设备？" @confirm="removeMember(row)">
            <t-link theme="danger">移出</t-link>
          </t-popconfirm>
        </template>
      </t-table>
      <div v-if="!loadingMembers && !members.length" class="empty">暂无成员</div>
    </t-drawer>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const page = reactive({ current: 1, pageSize: 20 })

const columns = [
  { colKey: 'name', title: '名称' },
  { colKey: 'owner', title: '归属', width: 140 },
  { colKey: 'member_count', title: '成员数', width: 100 },
  { colKey: 'note', title: '备注', ellipsis: true },
  { colKey: 'op', title: '操作', width: 200 },
]

async function load() {
  loading.value = true
  try {
    const data = await api.groups({ current: page.current, pageSize: page.pageSize })
    rows.value = data.list || []
    total.value = data.total || 0
  } catch (e) {
    MessagePlugin.error(e.message || '加载失败')
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
    MessagePlugin.warning('请填写名称')
    return
  }
  try {
    if (form.guid) await api.updateGroup(form.guid, { name: form.name, note: form.note })
    else await api.createGroup({ name: form.name, note: form.note })
    MessagePlugin.success('已保存')
    dialog.value = false
    load()
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  }
}
async function remove(row) {
  try {
    await api.deleteGroup(row.guid)
    MessagePlugin.success('已删除')
    load()
  } catch (e) {
    MessagePlugin.error(e.message || '删除失败')
  }
}

const drawer = ref(false)
const current = ref(null)
const members = ref([])
const loadingMembers = ref(false)
const newRid = ref('')
const memberColumns = [
  { colKey: 'rid', title: '设备 ID' },
  { colKey: 'alias', title: '别名', ellipsis: true },
  { colKey: 'hostname', title: '主机名', ellipsis: true },
  { colKey: 'op', title: '操作', width: 80 },
]

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
    MessagePlugin.error(e.message || '加载成员失败')
  } finally {
    loadingMembers.value = false
  }
}
async function addMember() {
  if (!newRid.value.trim()) return
  try {
    await api.addGroupMembers(current.value.guid, [newRid.value.trim()])
    newRid.value = ''
    MessagePlugin.success('已添加')
    await Promise.all([loadMembers(), load()])
  } catch (e) {
    MessagePlugin.error(e.message || '添加失败')
  }
}
async function removeMember(row) {
  try {
    await api.removeGroupMembers(current.value.guid, [row.rid])
    MessagePlugin.success('已移出')
    await Promise.all([loadMembers(), load()])
  } catch (e) {
    MessagePlugin.error(e.message || '移出失败')
  }
}

onMounted(load)
</script>

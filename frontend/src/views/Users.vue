<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">用户</h2>
      </div>
      <t-button theme="primary" @click="openDialog()">
        <template #icon><t-icon name="add" /></template>
        新建用户
      </t-button>
    </div>

    <div class="toolbar">
      <t-input v-model="keyword" placeholder="搜索用户名 / 显示名" clearable style="width: 240px" @enter="search" />
      <t-button variant="outline" @click="search">查询</t-button>
      <div class="spacer" />
      <span class="muted">共 {{ total }} 个账号</span>
    </div>

    <t-table :data="rows" :columns="columns" row-key="id" :loading="loading" hover>
      <template #is_admin="{ row }">
        <t-tag v-if="row.is_admin" theme="primary" variant="light" size="small">管理员</t-tag>
        <span v-else class="muted">普通用户</span>
      </template>
      <template #is_active="{ row }">
        <t-tag :theme="statusTheme(row)" variant="light" size="small">{{ statusLabel(row) }}</t-tag>
      </template>
      <template #op="{ row }">
        <t-link theme="primary" @click="openDialog(row)">编辑</t-link>
        <t-popconfirm v-if="row.id !== store.user?.id" content="确认删除该账号？" @confirm="remove(row)">
          <t-link theme="danger" style="margin-left: 10px">删除</t-link>
        </t-popconfirm>
      </template>
    </t-table>

    <div class="toolbar" style="justify-content: flex-end; margin-top: 16px">
      <t-pagination v-model="page.current" v-model:page-size="page.pageSize" :total="total" @change="load" />
    </div>

    <t-dialog v-model:visible="dialog" :header="form.id ? '编辑用户' : '新建用户'" :confirm-btn="{ content: '保存', theme: 'primary' }" @confirm="save">
      <t-form label-width="90px">
        <t-form-item label="用户名"><t-input v-model="form.username" :disabled="!!form.id" placeholder="登录名" /></t-form-item>
        <t-form-item :label="form.id ? '重置密码' : '密码'">
          <t-input v-model="form.password" type="password" :placeholder="form.id ? '留空则不修改' : '至少 6 位'" />
        </t-form-item>
        <t-form-item label="显示名"><t-input v-model="form.display_name" /></t-form-item>
        <t-form-item label="邮箱"><t-input v-model="form.email" placeholder="选填，仅作备注" /></t-form-item>
        <t-form-item label="备注"><t-input v-model="form.note" /></t-form-item>
        <t-form-item label="管理员"><t-switch v-model="form.is_admin" /></t-form-item>
        <t-form-item label="启用"><t-switch v-model="form.is_active" /></t-form-item>
      </t-form>
    </t-dialog>
  </div>
</template>

<script setup>
import { onMounted, reactive, ref } from 'vue'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import { store } from '../store'

const rows = ref([])
const total = ref(0)
const loading = ref(false)
const keyword = ref('')
const page = reactive({ current: 1, pageSize: 20 })

const columns = [
  { colKey: 'username', title: '用户名', width: 160 },
  { colKey: 'display_name', title: '显示名', width: 160 },
  { colKey: 'email', title: '邮箱（备注）', ellipsis: true },
  { colKey: 'device_count', title: '设备数', width: 90 },
  { colKey: 'is_admin', title: '角色', width: 110 },
  { colKey: 'is_active', title: '状态', width: 90 },
  { colKey: 'op', title: '操作', width: 120 },
]

function statusLabel(row) {
  if (!row.is_active) return '已停用'
  const st = Number(row.status ?? 1)
  if (st === 0) return '已停用'
  if (st === -1) return '未验证'
  return '正常'
}
function statusTheme(row) {
  const label = statusLabel(row)
  if (label === '正常') return 'success'
  if (label === '未验证') return 'warning'
  return 'default'
}

async function load() {
  loading.value = true
  try {
    const data = await api.users({ current: page.current, pageSize: page.pageSize, keyword: keyword.value })
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
    MessagePlugin.warning('请填写用户名')
    return
  }
  if (!form.id && form.password.length < 6) {
    MessagePlugin.warning('密码至少 6 位')
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
    MessagePlugin.success('已保存')
    dialog.value = false
    load()
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  }
}

async function remove(row) {
  try {
    await api.deleteUser(row.id)
    MessagePlugin.success('已删除')
    load()
  } catch (e) {
    MessagePlugin.error(e.message || '删除失败')
  }
}

onMounted(load)
</script>

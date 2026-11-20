<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">地址簿</h2>
      </div>
      <t-button v-if="isAdmin" theme="primary" @click="openAbDialog()">
        <template #icon><t-icon name="add" /></template>
        新建地址簿
      </t-button>
    </div>

    <div class="ab-layout">
      <div class="ab-list">
        <div v-if="!books.length && !loading" class="empty">暂无地址簿</div>
        <div
          v-for="book in books"
          :key="book.guid"
          class="ab-item"
          :class="{ active: book.guid === currentGuid }"
          @click="selectBook(book)"
        >
          <div class="ab-item-name">
            {{ book.name || '未命名地址簿' }}
            <t-tag v-if="book.is_personal" size="small" variant="light" theme="primary" style="margin-left: 6px">个人</t-tag>
            <t-tag v-else size="small" variant="light" :theme="ruleTagTheme(book.rule)" style="margin-left: 6px">{{ ruleLabel(book.rule) }}</t-tag>
          </div>
          <div class="ab-item-meta">
            {{ book.owner || '无归属' }} · {{ book.peer_count }} 个联系人
          </div>
        </div>
      </div>

      <div class="panel">
        <template v-if="currentBook">
          <div class="page-head" style="margin-bottom: 12px">
            <div>
              <div style="font-size: 16px; font-weight: 600">
                {{ currentBook.name }}
                <t-tag v-if="currentBook.is_personal" size="small" variant="light" theme="primary" style="margin-left: 6px">个人</t-tag>
                <t-tag v-else size="small" variant="light" :theme="ruleTagTheme(currentBook.rule)" style="margin-left: 6px">{{ ruleLabel(currentBook.rule) }}</t-tag>
              </div>
              <div class="muted" style="font-size: 12px; margin-top: 2px">
                归属 {{ currentBook.owner || '无' }} · 更新于 {{ currentBook.updated_at || '-' }}
              </div>
            </div>
            <div v-if="canEditAb">
              <t-button variant="text" theme="primary" size="small" @click="openAbDialog(currentBook)">重命名</t-button>
              <t-popconfirm v-if="!currentBook.is_personal" content="确认删除该地址簿及其联系人？" @confirm="removeBook">
                <t-button variant="text" theme="danger" size="small">删除</t-button>
              </t-popconfirm>
            </div>
          </div>

          <t-tabs v-model="tab">
            <t-tab-panel value="peers" :label="`联系人 (${peers.length})`">
              <div class="toolbar" style="margin-top: 12px">
                <t-input v-model="peerKeyword" placeholder="搜索 ID / 别名 / 主机名" clearable style="width: 240px" @enter="loadPeers" />
                <t-button variant="outline" @click="loadPeers">查询</t-button>
                <div class="spacer" />
                <t-button theme="primary" @click="openPeerDialog()">
                  <template #icon><t-icon name="add" /></template>
                  添加联系人
                </t-button>
              </div>
              <t-table :data="peers" :columns="peerColumns" row-key="id" :loading="loadingPeers" size="small" hover>
                <template #id="{ row }"><span class="mono">{{ row.id }}</span></template>
                <template #tags="{ row }">
                  <span
                    v-for="tag in row.tags"
                    :key="tag"
                    class="tag-chip"
                    :style="{ backgroundColor: tagColor(tagColorOf(tag)), marginRight: '4px' }"
                  >{{ tag }}</span>
                  <span v-if="!row.tags?.length" class="muted">-</span>
                </template>
                <template #has_password="{ row }">
                  <span :class="{ muted: !row.has_password }">{{ row.has_password ? '已设置' : '-' }}</span>
                </template>
                <template #op="{ row }">
                  <t-link theme="primary" @click="openPeerDialog(row)">编辑</t-link>
                  <t-popconfirm content="确认移除该联系人？" @confirm="removePeer(row)">
                    <t-link theme="danger" style="margin-left: 10px">移除</t-link>
                  </t-popconfirm>
                </template>
              </t-table>
            </t-tab-panel>

            <t-tab-panel value="tags" :label="`标签 (${tags.length})`">
              <div class="toolbar" style="margin-top: 12px">
                <div class="spacer" />
                <t-button theme="primary" @click="openTagDialog()">
                  <template #icon><t-icon name="add" /></template>
                  新建标签
                </t-button>
              </div>
              <t-table :data="tags" :columns="tagColumns" row-key="name" size="small" hover>
                <template #color="{ row }">
                  <span class="tag-chip" :style="{ backgroundColor: tagColor(row.color) }">{{ row.name }}</span>
                </template>
                <template #op="{ row }">
                  <t-link theme="primary" @click="openTagDialog(row)">编辑</t-link>
                  <t-popconfirm content="确认删除该标签？" @confirm="removeTag(row)">
                    <t-link theme="danger" style="margin-left: 10px">删除</t-link>
                  </t-popconfirm>
                </template>
              </t-table>
            </t-tab-panel>
          </t-tabs>
        </template>
        <div v-else class="empty">请选择左侧地址簿</div>
      </div>
    </div>

    <t-dialog v-model:visible="abDialog" :header="abForm.guid ? '编辑地址簿' : '新建地址簿'" :confirm-btn="{ content: '保存', theme: 'primary' }" @confirm="saveBook">
      <t-form label-width="80px">
        <t-form-item label="名称">
          <t-input v-model="abForm.name" :disabled="abForm.personal" placeholder="例如：运维组" />
          <div v-if="abForm.personal" class="muted" style="font-size: 12px; margin-top: 4px">
            个人地址簿在客户端固定显示为「我的地址簿」，名称不可修改；如需自定义名称，请新建共享地址簿。
          </div>
        </t-form-item>
        <t-form-item label="备注"><t-input v-model="abForm.note" placeholder="可选" /></t-form-item>
        <t-form-item label="可见范围">
          <t-select v-model="abForm.rule" :options="RULE_OPTIONS" :disabled="abForm.personal" style="width: 100%" />
        </t-form-item>
      </t-form>
    </t-dialog>

    <t-dialog v-model:visible="peerDialog" :header="peerForm.editing ? '编辑联系人' : '添加联系人'" :confirm-btn="{ content: '保存', theme: 'primary' }" @confirm="savePeer">
      <t-form label-width="80px">
        <t-form-item label="设备 ID"><t-input v-model="peerForm.id" :disabled="peerForm.editing" placeholder="必填" /></t-form-item>
        <t-form-item label="别名"><t-input v-model="peerForm.alias" /></t-form-item>
        <t-form-item label="用户名"><t-input v-model="peerForm.username" /></t-form-item>
        <t-form-item label="主机名"><t-input v-model="peerForm.hostname" /></t-form-item>
        <t-form-item label="平台"><t-input v-model="peerForm.platform" placeholder="Windows / Linux / macOS" /></t-form-item>
        <t-form-item v-if="currentBook && !currentBook.is_personal" label="共享密码">
          <t-input v-model="peerForm.password" type="password" autocomplete="new-password"
                   :placeholder="peerForm.editing ? '留空保持不变' : '可选，组内连接该设备时自动使用'" />
          <t-checkbox v-if="peerForm.editing && peerForm.hasPassword" v-model="peerForm.clearPassword" style="margin-top: 6px">
            清除已保存的共享密码
          </t-checkbox>
        </t-form-item>
        <t-form-item label="标签">
          <t-select v-model="peerForm.tags" :options="tagOptions" multiple filterable clearable placeholder="选择标签" style="width: 100%" />
        </t-form-item>
        <t-form-item label="备注"><t-input v-model="peerForm.note" /></t-form-item>
      </t-form>
    </t-dialog>

    <t-dialog v-model:visible="tagDialog" width="560px" :header="tagForm.editing ? '编辑标签' : '新建标签'" :confirm-btn="{ content: '保存', theme: 'primary' }" @confirm="saveTag">
      <t-form label-width="80px">
        <t-form-item label="名称"><t-input v-model="tagForm.name" placeholder="例如：生产环境" /></t-form-item>
        <t-form-item label="颜色">
          <div class="tag-color-field">
          <div class="tag-colors">
            <button
              v-for="c in TAG_COLORS"
              :key="c.value"
              type="button"
              class="tag-color"
              :class="{ active: Number(tagForm.color) === c.value }"
              :style="{ backgroundColor: tagColor(c.value) }"
              :title="c.label"
              @click="tagForm.color = c.value"
            />
            <button
              v-if="customColor"
              type="button"
              class="tag-color active"
              :style="{ backgroundColor: tagColor(tagForm.color) }"
              :title="'客户端颜色 ' + colorHex(tagForm.color)"
            />
          </div>
          <div class="tag-color-tip">{{ colorLabel(tagForm.color) }}</div>
          </div>
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

// 与客户端 flutter/lib/common.dart str2color2 完全一致的 12 色调色板（ARGB）
const TAG_COLORS = [
  { label: '红', value: 0xFFF44336 },
  { label: '绿', value: 0xFF4CAF50 },
  { label: '蓝', value: 0xFF2196F3 },
  { label: '橙', value: 0xFFFF9800 },
  { label: '紫', value: 0xFF9C27B0 },
  { label: '灰', value: 0xFF9E9E9E },
  { label: '青', value: 0xFF00BCD4 },
  { label: '柠檬', value: 0xFFCDDC39 },
  { label: '蓝绿', value: 0xFF009688 },
  { label: '粉', value: 0xFFF48FB1 },
  { label: '靛蓝', value: 0xFF3F51B5 },
  { label: '棕', value: 0xFF795548 },
]
const DEFAULT_TAG_COLOR = TAG_COLORS[2].value
const isAdmin = computed(() => !!store.user?.is_admin)

const books = ref([])
const currentGuid = ref('')
const currentBook = computed(() => books.value.find((b) => b.guid === currentGuid.value) || null)
const canEditAb = computed(
  () => isAdmin.value || (currentBook.value && currentBook.value.owner_id === store.user?.id),
)

const loading = ref(false)
const peers = ref([])
const tags = ref([])
const loadingPeers = ref(false)
const peerKeyword = ref('')
const tab = ref('peers')

const peerColumns = [
  { colKey: 'id', title: '设备 ID', width: 170 },
  { colKey: 'alias', title: '别名', width: 140 },
  { colKey: 'hostname', title: '主机名', ellipsis: true },
  { colKey: 'platform', title: '平台', width: 100 },
  { colKey: 'has_password', title: '共享密码', width: 100 },
  { colKey: 'tags', title: '标签', ellipsis: true },
  { colKey: 'note', title: '备注', ellipsis: true },
  { colKey: 'op', title: '操作', width: 120 },
]

const tagColumns = [
  { colKey: 'color', title: '标签', width: 200 },
  { colKey: 'op', title: '操作', width: 120 },
]

const tagOptions = computed(() => tags.value.map((t) => ({ label: t.name, value: t.name })))
function tagColorOf(name) {
  const hit = tags.value.find((t) => t.name === name)
  return hit ? hit.color : 0
}

function tagColor(color) {
  const n = Number(color) >>> 0
  if (!n) return '#9E9E9E'
  const r = (n >> 16) & 255
  const g = (n >> 8) & 255
  const b = n & 255
  return `rgb(${r}, ${g}, ${b})`
}
function colorHex(color) {
  const n = Number(color) >>> 0
  return `#${n.toString(16).padStart(6, '0').slice(-6).toUpperCase()}`
}
const customColor = computed(() => {
  const v = Number(tagForm.color) || 0
  return v > 0 && !TAG_COLORS.some((c) => c.value === v)
})
function colorLabel(color) {
  const v = Number(color) || 0
  const hit = TAG_COLORS.find((c) => c.value === v)
  if (hit) return `已选：${hit.label}`
  return v ? `客户端颜色 ${colorHex(v)}` : '未选择'
}

async function loadBooks() {
  loading.value = true
  try {
    const data = await api.addressbooks()
    books.value = data.list || []
    if (!currentGuid.value && books.value.length) currentGuid.value = books.value[0].guid
  } catch (e) {
    MessagePlugin.error(e.message || '加载失败')
  } finally {
    loading.value = false
  }
}

async function selectBook(book) {
  currentGuid.value = book.guid
  tab.value = 'peers'
  await Promise.all([loadPeers(), loadTags()])
}

async function loadPeers() {
  if (!currentGuid.value) return
  loadingPeers.value = true
  try {
    const data = await api.abPeers(currentGuid.value, { keyword: peerKeyword.value })
    peers.value = data.list || []
  } catch (e) {
    MessagePlugin.error(e.message || '加载联系人失败')
  } finally {
    loadingPeers.value = false
  }
}

async function loadTags() {
  if (!currentGuid.value) return
  try {
    const data = await api.abTags(currentGuid.value)
    tags.value = data.list || []
  } catch (e) {
    MessagePlugin.error(e.message || '加载标签失败')
  }
}

const RULE_OPTIONS = [
  { label: '私有（仅自己可见）', value: 0 },
  { label: '共享只读（所有用户可见，不能修改）', value: 1 },
  { label: '共享读写（所有用户可见，可增删联系人）', value: 2 },
  { label: '完全控制（所有用户可见，可管理标签和联系人）', value: 3 },
]
function ruleLabel(rule) {
  const r = Number(rule) || 0
  if (r <= 0) return '私有'
  if (r === 1) return '只读'
  if (r === 2) return '读写'
  return '完全控制'
}
function ruleTagTheme(rule) {
  const r = Number(rule) || 0
  if (r <= 0) return 'default'
  if (r === 1) return 'success'
  if (r === 2) return 'warning'
  return 'danger'
}
const abDialog = ref(false)
const abForm = reactive({ guid: '', name: '', note: '', rule: 0, personal: false })
function openAbDialog(book) {
  abForm.guid = book?.guid || ''
  abForm.name = book?.name || ''
  abForm.note = book?.note || ''
  abForm.rule = book?.rule || 0
  abForm.personal = !!book?.is_personal
  abDialog.value = true
}
async function saveBook() {
  if (!abForm.name.trim()) {
    MessagePlugin.warning('请填写名称')
    return
  }
  try {
    if (abForm.guid) {
      await api.updateAddressbook(abForm.guid, { name: abForm.name, note: abForm.note, rule: abForm.rule })
    } else {
      await api.createAddressbook({ name: abForm.name, note: abForm.note, rule: abForm.rule })
    }
    MessagePlugin.success('已保存')
    abDialog.value = false
    await loadBooks()
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  }
}
async function removeBook() {
  try {
    await api.deleteAddressbook(currentGuid.value)
    MessagePlugin.success('已删除')
    currentGuid.value = ''
    peers.value = []
    tags.value = []
    await loadBooks()
  } catch (e) {
    MessagePlugin.error(e.message || '删除失败')
  }
}

const peerDialog = ref(false)
const peerForm = reactive({
  editing: false, id: '', alias: '', username: '', hostname: '', platform: '',
  tags: [], note: '', password: '', clearPassword: false, hasPassword: false,
})
function openPeerDialog(row) {
  peerForm.editing = !!row
  peerForm.id = row?.id || ''
  peerForm.alias = row?.alias || ''
  peerForm.username = row?.username || ''
  peerForm.hostname = row?.hostname || ''
  peerForm.platform = row?.platform || ''
  peerForm.tags = row?.tags ? [...row.tags] : []
  peerForm.note = row?.note || ''
  peerForm.password = ''
  peerForm.clearPassword = false
  peerForm.hasPassword = !!row?.has_password
  peerDialog.value = true
}
async function savePeer() {
  if (!peerForm.id.trim()) {
    MessagePlugin.warning('请填写设备 ID')
    return
  }
  const body = {
    alias: peerForm.alias,
    username: peerForm.username,
    hostname: peerForm.hostname,
    platform: peerForm.platform,
    tags: peerForm.tags,
    note: peerForm.note,
  }
  if (currentBook.value && !currentBook.value.is_personal) {
    if (peerForm.clearPassword) body.password = ''
    else if (peerForm.password) body.password = peerForm.password
  }
  try {
    if (peerForm.editing) await api.updateAbPeer(currentGuid.value, peerForm.id.trim(), body)
    else await api.addAbPeer(currentGuid.value, { id: peerForm.id.trim(), ...body })
    MessagePlugin.success('已保存')
    peerDialog.value = false
    await Promise.all([loadPeers(), loadBooks()])
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  }
}
async function removePeer(row) {
  try {
    await api.deleteAbPeers(currentGuid.value, [row.id])
    MessagePlugin.success('已移除')
    await Promise.all([loadPeers(), loadBooks()])
  } catch (e) {
    MessagePlugin.error(e.message || '移除失败')
  }
}

const tagDialog = ref(false)
const tagForm = reactive({ editing: false, name: '', color: DEFAULT_TAG_COLOR })
function openTagDialog(row) {
  tagForm.editing = !!row
  tagForm.name = row?.name || ''
  tagForm.color = row?.color ?? DEFAULT_TAG_COLOR
  tagDialog.value = true
}
async function saveTag() {
  if (!tagForm.name.trim()) {
    MessagePlugin.warning('请填写标签名')
    return
  }
  try {
    if (tagForm.editing) await api.updateAbTag(currentGuid.value, tagForm.name, { color: tagForm.color })
    else await api.addAbTag(currentGuid.value, { name: tagForm.name.trim(), color: tagForm.color })
    MessagePlugin.success('已保存')
    tagDialog.value = false
    await loadTags()
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  }
}
async function removeTag(row) {
  try {
    await api.deleteAbTags(currentGuid.value, [row.name])
    MessagePlugin.success('已删除')
    await loadTags()
  } catch (e) {
    MessagePlugin.error(e.message || '删除失败')
  }
}

onMounted(async () => {
  await loadBooks()
  if (currentGuid.value) await selectBook(currentBook.value)
})
</script>

<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ t('addressbooks.title') }}</h2>
        <p class="page-sub">{{ t('addressbooks.sub') }}</p>
      </div>
      <div class="page-head-actions">
        <t-button v-if="isAdmin" theme="primary" @click="openAbDialog()">
          <template #icon><t-icon name="add" /></template>
          {{ t('addressbooks.createBtn') }}
        </t-button>
      </div>
    </div>

    <div class="ab-layout">
      <div class="ab-list">
        <div class="ab-search">
          <t-input v-model="bookFilter" :placeholder="t('addressbooks.filterPlaceholder')" clearable size="small">
            <template #prefix-icon><t-icon name="search" /></template>
          </t-input>
        </div>

        <div v-if="!filteredBooks.length && !loading" class="empty-state">
          <div class="empty-state-icon"><t-icon name="book" size="18px" /></div>
          <div>{{ books.length ? t('addressbooks.noMatch') : t('addressbooks.emptyBooks') }}</div>
        </div>

        <template v-else>
          <template v-if="sharedBooks.length">
            <div v-if="personalBooks.length" class="ab-section-label">
              {{ t('addressbooks.sharedSection', { count: sharedBooks.length }) }}
            </div>
            <div
              v-for="book in sharedBooks"
              :key="book.guid"
              class="ab-item"
              :class="{ active: book.guid === currentGuid }"
              @click="selectBook(book)"
            >
              <div class="ab-item-name">
                <span class="ab-item-title">{{ book.name || t('addressbooks.unnamedBook') }}</span>
                <t-tag size="small" variant="light" :theme="ruleTagTheme(book.rule)">{{ ruleLabel(book.rule) }}</t-tag>
              </div>
              <div class="ab-item-meta num">
                {{ book.owner || t('addressbooks.noOwner') }} · {{ t('addressbooks.peerCount', { count: book.peer_count }) }}
              </div>
            </div>
          </template>

          <template v-if="personalBooks.length">
            <div v-if="sharedBooks.length" class="ab-section-label">
              {{ t('addressbooks.personalSection', { count: personalBooks.length }) }}
            </div>
            <div
              v-for="book in personalBooks"
              :key="book.guid"
              class="ab-item"
              :class="{ active: book.guid === currentGuid }"
              @click="selectBook(book)"
            >
              <div class="ab-item-name">
                <span class="ab-item-title">{{ book.name || t('addressbooks.unnamedBook') }}</span>
                <t-tag size="small" variant="light" theme="primary">{{ t('addressbooks.personalTag') }}</t-tag>
              </div>
              <div class="ab-item-meta num">
                {{ book.owner || t('addressbooks.noOwner') }} · {{ t('addressbooks.peerCount', { count: book.peer_count }) }}
              </div>
            </div>
          </template>
        </template>
      </div>

      <div class="panel">
        <template v-if="currentBook">
          <div class="panel-head">
            <div>
              <div class="ab-detail-title">
                <span>{{ currentBook.name }}</span>
                <t-tag v-if="currentBook.is_personal" size="small" variant="light" theme="primary">
                  {{ t('addressbooks.personalTag') }}
                </t-tag>
                <t-tag v-else size="small" variant="light" :theme="ruleTagTheme(currentBook.rule)">
                  {{ ruleLabel(currentBook.rule) }}
                </t-tag>
              </div>
              <div class="ab-detail-meta">
                {{ t('addressbooks.detailMeta', { owner: currentBook.owner || t('common.none'), time: currentBook.updated_at || '-' }) }}
              </div>
            </div>
            <div v-if="canEditAb">
              <t-button variant="text" theme="primary" size="small" @click="openAbDialog(currentBook)">
                {{ t('addressbooks.rename') }}
              </t-button>
              <t-popconfirm v-if="!currentBook.is_personal" :content="t('addressbooks.deleteBookConfirm')" @confirm="removeBook">
                <t-button variant="text" theme="danger" size="small">{{ t('common.delete') }}</t-button>
              </t-popconfirm>
            </div>
          </div>

          <t-tabs v-model="tab">
            <t-tab-panel value="peers" :label="t('addressbooks.tabPeers', { count: peers.length })">
              <div class="toolbar mt-md">
                <t-input
                  v-model="peerKeyword"
                  class="filter-input"
                  :placeholder="t('addressbooks.peerSearchPlaceholder')"
                  clearable
                  @enter="loadPeers"
                  @clear="loadPeers"
                >
                  <template #prefix-icon><t-icon name="search" /></template>
                </t-input>
                <t-button variant="outline" @click="loadPeers">{{ t('common.search') }}</t-button>
                <div class="spacer" />
                <t-button theme="primary" @click="openPeerDialog()">
                  <template #icon><t-icon name="add" /></template>
                  {{ t('addressbooks.addPeerBtn') }}
                </t-button>
              </div>
              <t-table :data="peers" :columns="peerColumns" row-key="id" :loading="loadingPeers" size="small" hover>
                <template #id="{ row }">
                  <CopyableId :value="row.id" />
                </template>
                <template #platform="{ row }">
                  <OsBadge :os="row.platform" />
                </template>
                <template #tags="{ row }">
                  <span
                    v-for="tag in row.tags"
                    :key="tag"
                    class="tag-chip"
                    :style="{ backgroundColor: tagColor(tagColorOf(tag)) }"
                  >{{ tag }}</span>
                  <span v-if="!row.tags?.length" class="muted">-</span>
                </template>
                <template #has_password="{ row }">
                  <span v-if="row.has_password" class="lock-badge">
                    <t-icon name="lock-on" size="13px" />
                    <span>{{ t('addressbooks.passwordSaved') }}</span>
                  </span>
                  <span v-else class="muted">-</span>
                </template>
                <template #op="{ row }">
                  <t-link theme="primary" @click="openPeerDialog(row)">{{ t('common.edit') }}</t-link>
                  <t-popconfirm :content="t('addressbooks.removePeerConfirm')" @confirm="removePeer(row)">
                    <t-link theme="danger" class="link-gap">{{ t('common.remove') }}</t-link>
                  </t-popconfirm>
                </template>
              </t-table>
            </t-tab-panel>

            <t-tab-panel value="tags" :label="t('addressbooks.tabTags', { count: tags.length })">
              <div class="toolbar mt-md">
                <div class="spacer" />
                <t-button theme="primary" @click="openTagDialog()">
                  <template #icon><t-icon name="add" /></template>
                  {{ t('addressbooks.addTagBtn') }}
                </t-button>
              </div>
              <t-table :data="tags" :columns="tagColumns" row-key="name" size="small" hover>
                <template #color="{ row }">
                  <span class="tag-chip" :style="{ backgroundColor: tagColor(row.color) }">{{ row.name }}</span>
                </template>
                <template #op="{ row }">
                  <t-link theme="primary" @click="openTagDialog(row)">{{ t('common.edit') }}</t-link>
                  <t-popconfirm :content="t('addressbooks.deleteTagConfirm')" @confirm="removeTag(row)">
                    <t-link theme="danger" class="link-gap">{{ t('common.delete') }}</t-link>
                  </t-popconfirm>
                </template>
              </t-table>
            </t-tab-panel>
          </t-tabs>
        </template>
        <div v-else class="empty-state">
          <div class="empty-state-icon"><t-icon name="book" size="18px" /></div>
          <div>{{ t('addressbooks.selectPrompt') }}</div>
        </div>
      </div>
    </div>

    <t-dialog
      v-model:visible="abDialog"
      :header="abForm.guid ? t('addressbooks.editAbTitle') : t('addressbooks.createAbTitle')"
      :confirm-btn="{ content: t('common.save'), theme: 'primary' }"
      @confirm="saveBook"
    >
      <t-form label-width="90px">
        <t-form-item :label="t('common.name')">
          <div class="full-width">
            <t-input v-model="abForm.name" :disabled="abForm.personal" :placeholder="t('addressbooks.abNamePlaceholder')" />
            <div v-if="abForm.personal" class="field-hint">
              {{ t('addressbooks.personalNameHint') }}
            </div>
          </div>
        </t-form-item>
        <t-form-item :label="t('common.note')"><t-input v-model="abForm.note" :placeholder="t('common.optional')" /></t-form-item>
        <t-form-item :label="t('addressbooks.visibilityField')">
          <t-select v-model="abForm.rule" :options="ruleOptions" :disabled="abForm.personal" class="full-width" />
        </t-form-item>
      </t-form>
    </t-dialog>

    <t-dialog
      v-model:visible="peerDialog"
      :header="peerForm.editing ? t('addressbooks.editPeerTitle') : t('addressbooks.addPeerTitle')"
      :confirm-btn="{ content: t('common.save'), theme: 'primary' }"
      @confirm="savePeer"
    >
      <t-form label-width="90px">
        <t-form-item :label="t('addressbooks.colId')">
          <t-input v-model="peerForm.id" :disabled="peerForm.editing" :placeholder="t('common.required')" />
        </t-form-item>
        <t-form-item :label="t('addressbooks.colAlias')"><t-input v-model="peerForm.alias" /></t-form-item>
        <t-form-item :label="t('addressbooks.usernameField')"><t-input v-model="peerForm.username" /></t-form-item>
        <t-form-item :label="t('addressbooks.colHostname')"><t-input v-model="peerForm.hostname" /></t-form-item>
        <t-form-item :label="t('addressbooks.colPlatform')">
          <t-input v-model="peerForm.platform" :placeholder="t('addressbooks.platformPlaceholder')" />
        </t-form-item>
        <t-form-item v-if="currentBook && !currentBook.is_personal" :label="t('addressbooks.colSharedPassword')">
          <div class="full-width">
            <t-input
              v-model="peerForm.password"
              type="password"
              autocomplete="new-password"
              :placeholder="peerForm.editing ? t('addressbooks.passwordEditPlaceholder') : t('addressbooks.passwordAddPlaceholder')"
            />
            <t-checkbox v-if="peerForm.editing && peerForm.hasPassword" v-model="peerForm.clearPassword" class="mt-sm">
              {{ t('addressbooks.clearPassword') }}
            </t-checkbox>
          </div>
        </t-form-item>
        <t-form-item :label="t('addressbooks.colTags')">
          <t-select
            v-model="peerForm.tags"
            :options="tagOptions"
            multiple
            filterable
            clearable
            :placeholder="t('addressbooks.tagsPlaceholder')"
            class="full-width"
          />
        </t-form-item>
        <t-form-item :label="t('common.note')"><t-input v-model="peerForm.note" /></t-form-item>
      </t-form>
    </t-dialog>

    <t-dialog
      v-model:visible="tagDialog"
      width="560px"
      :header="tagForm.editing ? t('addressbooks.editTagTitle') : t('addressbooks.createTagTitle')"
      :confirm-btn="{ content: t('common.save'), theme: 'primary' }"
      @confirm="saveTag"
    >
      <t-form label-width="84px">
        <t-form-item :label="t('common.name')">
          <t-input v-model="tagForm.name" :placeholder="t('addressbooks.tagNamePlaceholder')" />
        </t-form-item>
        <t-form-item :label="t('addressbooks.colorField')">
          <div class="tag-color-field">
            <div class="tag-colors">
              <button
                v-for="c in tagColors"
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
                :title="t('addressbooks.colorClient', { hex: colorHex(tagForm.color) })"
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
import { t } from '../i18n'
import CopyableId from '../components/CopyableId.vue'
import OsBadge from '../components/OsBadge.vue'

// 与客户端 flutter/lib/common.dart str2color2 完全一致的 12 色调色板（ARGB）
const TAG_COLOR_DEFS = [
  { key: 'red', value: 0xfff44336 },
  { key: 'green', value: 0xff4caf50 },
  { key: 'blue', value: 0xff2196f3 },
  { key: 'orange', value: 0xffff9800 },
  { key: 'purple', value: 0xff9c27b0 },
  { key: 'gray', value: 0xff9e9e9e },
  { key: 'cyan', value: 0xff00bcd4 },
  { key: 'lime', value: 0xffcddc39 },
  { key: 'teal', value: 0xff009688 },
  { key: 'pink', value: 0xfff48fb1 },
  { key: 'indigo', value: 0xff3f51b5 },
  { key: 'brown', value: 0xff795548 },
]
const tagColors = computed(() => TAG_COLOR_DEFS.map((c) => ({ ...c, label: t(`addressbooks.colors.${c.key}`) })))
const DEFAULT_TAG_COLOR = TAG_COLOR_DEFS[2].value
const isAdmin = computed(() => !!store.user?.is_admin)

const books = ref([])
const bookFilter = ref('')
const currentGuid = ref('')
const currentBook = computed(() => books.value.find((b) => b.guid === currentGuid.value) || null)
const canEditAb = computed(
  () => isAdmin.value || (currentBook.value && currentBook.value.owner_id === store.user?.id),
)

const filteredBooks = computed(() => {
  const kw = bookFilter.value.trim().toLowerCase()
  if (!kw) return books.value
  return books.value.filter(
    (b) =>
      String(b.name || '')
        .toLowerCase()
        .includes(kw) ||
      String(b.owner || '')
        .toLowerCase()
        .includes(kw),
  )
})

const sharedBooks = computed(() => filteredBooks.value.filter((b) => !b.is_personal))
const personalBooks = computed(() => filteredBooks.value.filter((b) => b.is_personal))

const loading = ref(false)
const peers = ref([])
const tags = ref([])
const loadingPeers = ref(false)
const peerKeyword = ref('')
const tab = ref('peers')

const peerColumns = computed(() => [
  { colKey: 'id', title: t('addressbooks.colId'), width: 132 },
  { colKey: 'alias', title: t('addressbooks.colAlias'), width: 96, ellipsis: true },
  { colKey: 'hostname', title: t('addressbooks.colHostname'), ellipsis: true },
  { colKey: 'platform', title: t('addressbooks.colPlatform'), width: 102 },
  { colKey: 'has_password', title: t('addressbooks.colSharedPassword'), width: 86 },
  { colKey: 'tags', title: t('addressbooks.colTags'), width: 98, ellipsis: true },
  { colKey: 'note', title: t('common.note'), ellipsis: true },
  { colKey: 'op', title: t('common.actions'), width: 120 },
])

const tagColumns = computed(() => [
  { colKey: 'color', title: t('addressbooks.colTag'), width: 200 },
  { colKey: 'op', title: t('common.actions'), width: 130 },
])

const tagOptions = computed(() => tags.value.map((tag) => ({ label: tag.name, value: tag.name })))
function tagColorOf(name) {
  const hit = tags.value.find((tag) => tag.name === name)
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
  return v > 0 && !TAG_COLOR_DEFS.some((c) => c.value === v)
})
function colorLabel(color) {
  const v = Number(color) || 0
  const hit = tagColors.value.find((c) => c.value === v)
  if (hit) return t('addressbooks.colorSelected', { label: hit.label })
  return v ? t('addressbooks.colorClient', { hex: colorHex(v) }) : t('addressbooks.colorUnselected')
}

async function loadBooks() {
  loading.value = true
  try {
    const data = await api.addressbooks()
    books.value = data.list || []
    if (!currentGuid.value && books.value.length) currentGuid.value = books.value[0].guid
  } catch (e) {
    MessagePlugin.error(e.message || t('common.loadFailed'))
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
    MessagePlugin.error(e.message || t('addressbooks.loadPeersFailed'))
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
    MessagePlugin.error(e.message || t('addressbooks.loadTagsFailed'))
  }
}

const ruleOptions = computed(() => [
  { label: t('addressbooks.rulePrivateOpt'), value: 0 },
  { label: t('addressbooks.ruleReadonlyOpt'), value: 1 },
  { label: t('addressbooks.ruleReadwriteOpt'), value: 2 },
  { label: t('addressbooks.ruleFullOpt'), value: 3 },
])

function ruleLabel(rule) {
  const r = Number(rule) || 0
  if (r <= 0) return t('addressbooks.rulePrivate')
  if (r === 1) return t('addressbooks.ruleReadonly')
  if (r === 2) return t('addressbooks.ruleReadwrite')
  return t('addressbooks.ruleFull')
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
    MessagePlugin.warning(t('common.fillName'))
    return
  }
  try {
    if (abForm.guid) {
      await api.updateAddressbook(abForm.guid, { name: abForm.name, note: abForm.note, rule: abForm.rule })
    } else {
      await api.createAddressbook({ name: abForm.name, note: abForm.note, rule: abForm.rule })
    }
    MessagePlugin.success(t('common.saved'))
    abDialog.value = false
    await loadBooks()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
  }
}
async function removeBook() {
  try {
    await api.deleteAddressbook(currentGuid.value)
    MessagePlugin.success(t('common.deleted'))
    currentGuid.value = ''
    peers.value = []
    tags.value = []
    await loadBooks()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.deleteFailed'))
  }
}

const peerDialog = ref(false)
const peerForm = reactive({
  editing: false,
  id: '',
  alias: '',
  username: '',
  hostname: '',
  platform: '',
  tags: [],
  note: '',
  password: '',
  clearPassword: false,
  hasPassword: false,
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
    MessagePlugin.warning(t('addressbooks.warnFillRid'))
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
    MessagePlugin.success(t('common.saved'))
    peerDialog.value = false
    await Promise.all([loadPeers(), loadBooks()])
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
  }
}
async function removePeer(row) {
  try {
    await api.deleteAbPeers(currentGuid.value, [row.id])
    MessagePlugin.success(t('common.removed'))
    await Promise.all([loadPeers(), loadBooks()])
  } catch (e) {
    MessagePlugin.error(e.message || t('common.removeFailed'))
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
    MessagePlugin.warning(t('addressbooks.warnFillTagName'))
    return
  }
  try {
    if (tagForm.editing) await api.updateAbTag(currentGuid.value, tagForm.name, { color: tagForm.color })
    else await api.addAbTag(currentGuid.value, { name: tagForm.name.trim(), color: tagForm.color })
    MessagePlugin.success(t('common.saved'))
    tagDialog.value = false
    await loadTags()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
  }
}
async function removeTag(row) {
  try {
    await api.deleteAbTags(currentGuid.value, [row.name])
    MessagePlugin.success(t('common.deleted'))
    await loadTags()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.deleteFailed'))
  }
}

onMounted(async () => {
  await loadBooks()
  if (currentGuid.value) await selectBook(currentBook.value)
})
</script>

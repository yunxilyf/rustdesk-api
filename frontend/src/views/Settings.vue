<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">个人设置</h2>
      </div>
    </div>

    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 16px; max-width: 980px">
      <div class="panel">
        <h3 style="margin: 0 0 16px; font-size: 16px">账号信息</h3>
        <t-form label-width="90px">
          <t-form-item label="用户名">{{ user?.username }}</t-form-item>
          <t-form-item label="显示名">
            <t-input v-model="profile.display_name" :maxlength="64" placeholder="留空则显示用户名" />
          </t-form-item>
          <t-form-item label="邮箱">
            <t-input v-model="profile.email" placeholder="选填，仅作备注，不参与登录" />
          </t-form-item>
          <t-form-item label="角色">
            <t-tag :theme="user?.is_admin ? 'primary' : 'default'" variant="light" size="small">
              {{ user?.is_admin ? '管理员' : '普通用户' }}
            </t-tag>
          </t-form-item>
          <t-form-item label="状态">
            <t-tag :theme="user?.is_active ? 'success' : 'default'" variant="light" size="small">
              {{ user?.is_active ? '启用' : '停用' }}
            </t-tag>
          </t-form-item>
          <t-form-item label=" ">
            <t-button theme="primary" :loading="savingProfile" @click="saveProfile">保存资料</t-button>
          </t-form-item>
        </t-form>
      </div>

      <div class="panel">
        <h3 style="margin: 0 0 16px; font-size: 16px">修改密码</h3>
        <t-form label-width="90px" :data="form" @submit="submit">
          <t-form-item label="当前密码">
            <t-input v-model="form.old" type="password" placeholder="请输入当前密码" />
          </t-form-item>
          <t-form-item label="新密码">
            <t-input v-model="form.password" type="password" placeholder="至少 8 位" />
          </t-form-item>
          <t-form-item label="确认密码">
            <t-input v-model="form.confirm" type="password" placeholder="再次输入新密码" />
          </t-form-item>
          <t-form-item label=" ">
            <t-button theme="primary" type="submit" :loading="saving">保存</t-button>
          </t-form-item>
        </t-form>
      </div>
    </div>


    <div class="panel" style="margin-top: 16px; max-width: 980px">
      <h3 style="margin: 0 0 6px; font-size: 16px">软件更新</h3>
      <div class="muted" style="margin-bottom: 16px">当前版本 {{ versionInfo.version || '-' }}</div>
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 24px">
        <div>
          <div v-if="versionInfo.update_available" style="font-weight: 500">
            发现新版本 {{ versionInfo.latest }}
            <a v-if="versionInfo.release_url" :href="versionInfo.release_url" target="_blank" rel="noopener">查看发布说明</a>
          </div>
          <div v-else-if="versionInfo.checked && !versionInfo.error" class="muted">已是最新版本</div>
          <div v-else-if="versionInfo.error" class="muted">检查失败：{{ versionInfo.error }}</div>
          <div v-else class="muted">点击右侧按钮检查 GitHub 上是否有新版本</div>
        </div>
        <t-button variant="outline" :loading="checking" @click="checkUpdate">检查更新</t-button>
      </div>
    </div>

    <div v-if="user?.is_admin" class="panel" style="margin-top: 16px; max-width: 980px">
      <h3 style="margin: 0 0 6px; font-size: 16px">第三方登录</h3>
      <div class="muted" style="margin-bottom: 16px">
        可配置多个登录方式，客户端登录页会并列显示按钮；回调地址需在身份提供方登记为
        <code>{{ oidc.redirect_uri || CALLBACK_PLACEHOLDER }}</code>
      </div>

      <t-collapse v-model="expandedProviders" style="margin-bottom: 12px">
        <t-collapse-panel v-for="(p, idx) in oidc.providers" :key="idx" :value="idx">
          <template #header>
            <div style="display: flex; align-items: center; justify-content: space-between; width: 100%">
              <span>
                <strong>{{ p.name || p.type || p.op || '未命名登录方式' }}</strong>
                <t-tag v-if="p.name && p.type" size="small" variant="light" style="margin-left: 8px">{{ p.type }}</t-tag>
                <t-tag v-if="p.saved" size="small" theme="success" variant="light" style="margin-left: 6px">已保存</t-tag>
              </span>
              <span style="display: flex; align-items: center" @click.stop>
                <t-switch v-model="p.enabled" size="small" />
                <span class="muted" style="margin: 0 12px 0 6px">启用</span>
                <t-button variant="text" theme="danger" size="small" @click.stop="removeProvider(idx)">删除</t-button>
              </span>
            </div>
          </template>
          <t-form label-width="110px">
                    <div style="display: grid; grid-template-columns: 1fr 1fr; gap: 0 16px">
                      <t-form-item label="类型">
                        <t-select v-model="p.type" :options="OAUTH_TYPES" style="width: 100%" @change="() => syncOpFromType(p)" />
                      </t-form-item>
                      <t-form-item label="标识 op">
                        <t-input
                          v-model="p.op"
                          :maxlength="32"
                          :disabled="p.saved"
                          :placeholder="p.saved ? '保存后不可修改' : '跟随类型自动填充'"
                          @change="() => (p.op_fixed = !!p.op)"
                        />
                        <div v-if="p.saved" class="muted" style="font-size: 12px">标识参与账号绑定，保存后不可修改</div>
                      </t-form-item>
                      <t-form-item label="按钮名称">
                        <t-input v-model="p.name" :maxlength="64" placeholder="留空则用标识" />
                      </t-form-item>
                      <t-form-item label="排序">
                        <t-input-number v-model="p.sort" theme="normal" style="width: 100%" />
                      </t-form-item>
                    </div>
                    <t-form-item v-if="p.type !== 'github'" label="Issuer">
                      <t-input v-model="p.issuer" placeholder="https://id.example.com/realms/main（Google 可留空）" />
                    </t-form-item>
                    <t-form-item label="Client ID">
                      <t-input v-model="p.client_id" placeholder="rustdesk-api" />
                    </t-form-item>
                    <t-form-item label="Client Secret">
                      <t-input
                        v-model="p.client_secret"
                        type="password"
                        :placeholder="p.has_secret && !p.clear_secret ? '已保存，留空则不修改' : '填写客户端密钥'"
                      />
                    </t-form-item>
                    <t-form-item label="Scopes">
                      <t-input v-model="p.scopes" placeholder="留空使用默认值" />
                    </t-form-item>
                    <t-form-item label=" ">
                      <t-checkbox v-model="p.auto_register">允许自动创建账号</t-checkbox>
                      <t-checkbox v-model="p.pkce_enable" style="margin-left: 16px">启用 PKCE</t-checkbox>
                      <t-button
                        v-if="p.has_secret && !p.clear_secret"
                        variant="text"
                        theme="danger"
                        style="margin-left: 8px"
                        @click="markClearSecret(p)"
                      >
                        清除密钥
                      </t-button>
                      <span v-if="p.clear_secret" class="muted" style="margin-left: 8px">保存后清除已存密钥</span>
                      <t-button v-if="p.clear_secret" variant="text" size="small" @click="undoClearSecret(p)">撤销</t-button>
                    </t-form-item>
                  </t-form>
        </t-collapse-panel>
      </t-collapse>

      <div v-if="oidcLoading" class="muted" style="margin-bottom: 12px">正在加载登录方式…</div>
      <div v-else-if="!oidc.providers.length" class="muted" style="margin-bottom: 12px">
        <template v-if="oidcLoaded">尚未配置任何登录方式，客户端登录页不会显示第三方登录按钮。</template>
        <template v-else>加载失败，请刷新页面后重试（当前不可保存，避免覆盖已有配置）。</template>
      </div>
      <t-button variant="outline" @click="addProvider">添加登录方式</t-button>
      <t-button theme="primary" :loading="savingOidc" :disabled="!oidcLoaded" style="margin-left: 8px" @click="saveOidc">
        保存全部
      </t-button>
      <div class="muted" style="margin-top: 12px">
        当前状态：<t-tag :theme="oidc.enabled ? 'success' : 'default'" variant="light" size="small">
          {{ oidc.enabled ? '已启用' : '未启用' }}
        </t-tag>
      </div>
    </div>

    <div v-if="user?.is_admin" class="panel" style="margin-top: 16px; max-width: 980px">
      <h3 style="margin: 0 0 6px; font-size: 16px">系统设置</h3>
      <div class="muted" style="margin-bottom: 16px">仅管理员可见，修改后立即生效</div>
      <div style="display: flex; align-items: center; justify-content: space-between; gap: 24px">
        <div>
          <div style="font-weight: 500">允许用户自助注册</div>
          <div class="muted" style="margin-top: 4px">
            开启后，登录页可自助注册普通账号；关闭后仅管理员能在「用户」页添加账号。
          </div>
        </div>
        <t-switch
          v-model="settings.allow_registration"
          :loading="savingSetting"
          @change="saveSetting"
        />
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { DialogPlugin, MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import { setUser, store } from '../store'

const user = computed(() => store.user)
const saving = ref(false)
const savingProfile = ref(false)
const profile = reactive({ display_name: '', email: '' })
const form = reactive({ old: '', password: '', confirm: '' })
const settings = reactive({ allow_registration: true })
const savingSetting = ref(false)
const savingOidc = ref(false)
const oidc = reactive({ enabled: false, redirect_uri: '', providers: [] })
const expandedProviders = ref([])
const oidcLoaded = ref(false)
const oidcLoading = ref(false)
const OAUTH_TYPES = [
  { value: 'oidc', label: '通用 OIDC' },
  { value: 'github', label: 'GitHub' },
  { value: 'google', label: 'Google' },
]
const CALLBACK_PLACEHOLDER = 'https://rustdesk.example.com/api/oidc/callback'
const checking = ref(false)
const versionInfo = reactive({ version: '', latest: '', update_available: false, release_url: '', error: '', checked: false })

async function checkUpdate() {
  checking.value = true
  try {
    const data = await api.getVersion()
    Object.assign(versionInfo, {
      version: data.version || '',
      latest: data.latest || '',
      update_available: !!data.update_available,
      release_url: data.release_url || '',
      error: data.error || '',
      checked: true,
    })
  } catch (e) {
    versionInfo.error = e.message || '检查失败'
    versionInfo.checked = true
  } finally {
    checking.value = false
  }
}

function newProvider(sort) {
  return {
    op: '',
    op_fixed: false,
    saved: false,
    name: '',
    type: 'oidc',
    issuer: '',
    client_id: '',
    client_secret: '',
    has_secret: false,
    clear_secret: false,
    scopes: '',
    auto_register: true,
    pkce_enable: true,
    enabled: true,
    sort,
  }
}

function normalizeProvider(row, sort) {
  return {
    ...newProvider(sort),
    // 已保存的记录保留原 op，不被类型改名覆盖；op 也不允许再编辑（会丢绑定）。
    op_fixed: true,
    saved: true,
    op: row.op || '',
    name: row.name || '',
    type: row.type || 'oidc',
    issuer: row.issuer || '',
    client_id: row.client_id || '',
    scopes: row.scopes || '',
    auto_register: row.auto_register !== false,
    pkce_enable: row.pkce_enable !== false,
    enabled: row.enabled !== false,
    sort: Number.isFinite(Number(row.sort)) ? Number(row.sort) : sort,
    has_secret: !!row.has_secret,
  }
}

async function loadSettings() {
  if (!user.value?.is_admin) return
  oidcLoading.value = true
  try {
    const data = await api.getSettings()
    settings.allow_registration = !!data.allow_registration
    if (data.oidc) {
      oidc.enabled = !!data.oidc.enabled
      oidc.redirect_uri = data.oidc.redirect_uri || ''
      oidc.providers = (data.oidc.providers || []).map((row, idx) => normalizeProvider(row, idx))
      // 只有真正读到配置才允许保存：否则一次请求失败就会把服务器上的配置删空。
      oidcLoaded.value = true
    }
  } catch (e) {
    oidcLoaded.value = false
  } finally {
    oidcLoading.value = false
  }
}

// 标识 op 默认跟随类型；用户手改过（op_fixed）就不再自动覆盖
function syncOpFromType(provider) {
  if (provider.type === 'github') provider.issuer = ''
  if (provider.op_fixed) return
  provider.op = uniqueOp(provider, provider.type)
}

function uniqueOp(provider, base) {
  const taken = new Set(oidc.providers.filter((item) => item !== provider && item.op).map((item) => item.op))
  if (!taken.has(base)) return base
  let index = 2
  while (taken.has(`${base}${index}`)) index += 1
  return `${base}${index}`
}

function addProvider() {
  const provider = newProvider(oidc.providers.length)
  provider.op = uniqueOp(provider, provider.type)
  oidc.providers.push(provider)
  expandedProviders.value = [...expandedProviders.value, oidc.providers.length - 1]
}

function removeProvider(index) {
  const provider = oidc.providers[index]
  if (!provider) return
  if (!provider.saved) {
    oidc.providers.splice(index, 1)
    return
  }
  DialogPlugin.confirm({
    header: '删除登录方式',
    body: `删除「${provider.name || provider.op}」后，已绑定的用户将无法再用它登录，确定继续？`,
    theme: 'warning',
    onConfirm: () => {
      oidc.providers.splice(index, 1)
      expandedProviders.value = []
    },
  })
}

function markClearSecret(provider) {
  provider.client_secret = ''
  provider.has_secret = false
  provider.clear_secret = true
}

function undoClearSecret(provider) {
  provider.clear_secret = false
  provider.has_secret = true
}

async function saveSetting(value) {
  savingSetting.value = true
  try {
    await api.updateSettings({ allow_registration: !!value })
    MessagePlugin.success(value ? '已开启用户注册' : '已关闭用户注册')
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
    await loadSettings()
  } finally {
    savingSetting.value = false
  }
}

async function saveOidc() {
  if (!oidcLoaded.value) {
    MessagePlugin.warning('登录方式配置尚未加载成功，请刷新页面后重试')
    return
  }
  const seen = new Set()
  const items = []
  for (const [idx, p] of oidc.providers.entries()) {
    const op = (p.op || p.type || '').trim()
    if (!op) {
      MessagePlugin.warning(`第 ${idx + 1} 个登录方式缺少标识 op`)
      return
    }
    if (seen.has(op)) {
      MessagePlugin.warning(`标识 op 重复：${op}`)
      return
    }
    seen.add(op)
    const clientId = (p.client_id || '').trim()
    if (!clientId) {
      MessagePlugin.warning(`${op} 缺少 Client ID`)
      return
    }
    const issuer = (p.issuer || '').trim()
    if (p.type !== 'github' && !issuer) {
      MessagePlugin.warning(`${op} 缺少 Issuer`)
      return
    }
    if (issuer && !/^https?:\/\//i.test(issuer)) {
      MessagePlugin.warning(`${op} 的 Issuer 必须是 http(s) 地址`)
      return
    }
    if (!p.has_secret && !p.client_secret && !p.clear_secret) {
      MessagePlugin.warning(`${op} 缺少 Client Secret`)
      return
    }
    const item = {
      op,
      name: (p.name || '').trim(),
      type: p.type,
      issuer,
      client_id: clientId,
      scopes: (p.scopes || '').trim(),
      auto_register: !!p.auto_register,
      pkce_enable: !!p.pkce_enable,
      enabled: !!p.enabled,
      sort: Number(p.sort) || 0,
    }
    if (p.client_secret) item.client_secret = p.client_secret
    if (p.clear_secret) item.clear_secret = true
    items.push(item)
  }
  if (!items.length) {
    const confirmed = await new Promise((resolve) => {
      DialogPlugin.confirm({
        header: '清空第三方登录',
        body: '当前没有保留任何登录方式，保存后会删除服务器上的全部配置，客户端与控制台将不再显示第三方登录按钮。确定继续？',
        theme: 'warning',
        onConfirm: () => resolve(true),
        onCancel: () => resolve(false),
        onClose: () => resolve(false),
      })
    })
    if (!confirmed) return
  }
  savingOidc.value = true
  try {
    await api.updateSettings({ oidc: { providers: items } })
    MessagePlugin.success('第三方登录配置已保存')
    await loadSettings()
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  } finally {
    savingOidc.value = false
  }
}

function syncProfile() {
  profile.display_name = user.value?.display_name || ''
  profile.email = user.value?.email || ''
}

async function saveProfile() {
  const email = (profile.email || '').trim()
  if (email && !/^[^@\s]+@[^@\s]+\.[^@\s]+$/.test(email)) {
    MessagePlugin.warning('邮箱格式不正确')
    return
  }
  savingProfile.value = true
  try {
    const data = await api.updateProfile({
      display_name: (profile.display_name || '').trim(),
      email,
    })
    if (data?.user) setUser(data.user)
    MessagePlugin.success('资料已保存')
  } catch (e) {
    MessagePlugin.error(e.message || '保存失败')
  } finally {
    savingProfile.value = false
  }
}

onMounted(() => {
  syncProfile()
  loadSettings()
  checkUpdate()
})

async function submit() {
  if (!form.old || !form.password) {
    MessagePlugin.warning('请填写完整')
    return
  }
  if (form.password.length < 8) {
    MessagePlugin.warning('新密码至少 8 位')
    return
  }
  if (form.password !== form.confirm) {
    MessagePlugin.warning('两次输入的密码不一致')
    return
  }
  saving.value = true
  try {
    await api.changePassword(form.old, form.password)
    MessagePlugin.success('密码已修改')
    form.old = ''
    form.password = ''
    form.confirm = ''
  } catch (e) {
    MessagePlugin.error(e.message || '修改失败')
  } finally {
    saving.value = false
  }
}
</script>

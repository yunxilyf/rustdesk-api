<template>
  <div class="page">
    <div class="page-head">
      <div>
        <h2 class="page-title">{{ t('settings.title') }}</h2>
        <p class="page-sub">{{ t('settings.sub') }}</p>
      </div>
    </div>

    <div class="settings-wrap">
      <div class="settings-tabs-panel">
        <t-tabs v-model="activeTab">
          <t-tab-panel value="account" :label="t('settings.tabAccount')">
            <div class="settings-tab-body settings-stack">
              <div class="settings-grid">
                <div class="settings-section">
                  <h3 class="settings-section-title">{{ t('settings.profileTitle') }}</h3>
                  <p class="settings-section-sub">{{ t('settings.profileSub') }}</p>
                  <t-form label-width="102px">
                    <t-form-item :label="t('settings.fieldUsername')">
                      <span class="mono">{{ user?.username }}</span>
                    </t-form-item>
                    <t-form-item :label="t('settings.fieldDisplayName')">
                      <t-input v-model="profile.display_name" :maxlength="64" :placeholder="t('settings.displayNamePlaceholder')" />
                    </t-form-item>
                    <t-form-item :label="t('settings.fieldEmail')">
                      <t-input v-model="profile.email" :placeholder="t('settings.emailPlaceholder')" />
                    </t-form-item>
                    <t-form-item :label="t('settings.fieldRole')">
                      <t-tag :theme="user?.is_admin ? 'primary' : 'default'" variant="light" size="small">
                        {{ user?.is_admin ? t('common.admin') : t('common.user') }}
                      </t-tag>
                    </t-form-item>
                    <t-form-item :label="t('common.status')">
                      <StatusDot
                        :status="user?.is_active ? 'online' : 'offline'"
                        :label="user?.is_active ? t('common.enabled') : t('common.disabled')"
                        :pulse="false"
                      />
                    </t-form-item>
                    <t-form-item label=" ">
                      <t-button theme="primary" :loading="savingProfile" @click="saveProfile">
                        {{ t('settings.saveProfileBtn') }}
                      </t-button>
                    </t-form-item>
                  </t-form>
                </div>

                <div class="settings-section">
                  <h3 class="settings-section-title">{{ t('settings.passwordTitle') }}</h3>
                  <p class="settings-section-sub">{{ t('settings.passwordSub') }}</p>
                  <t-form label-width="96px" :data="form" @submit="submit">
                    <t-form-item :label="t('settings.fieldOldPassword')">
                      <t-input v-model="form.old" type="password" :placeholder="t('settings.oldPasswordPlaceholder')" />
                    </t-form-item>
                    <t-form-item :label="t('settings.fieldNewPassword')">
                      <t-input v-model="form.password" type="password" :placeholder="t('settings.newPasswordPlaceholder')" />
                    </t-form-item>
                    <t-form-item :label="t('settings.fieldConfirmPassword')">
                      <t-input v-model="form.confirm" type="password" :placeholder="t('settings.confirmPasswordPlaceholder')" />
                    </t-form-item>
                    <t-form-item label=" ">
                      <t-button theme="primary" type="submit" :loading="saving">{{ t('common.save') }}</t-button>
                    </t-form-item>
                  </t-form>
                </div>
              </div>

              <div class="settings-section">
                <div class="setting-row">
                  <div>
                    <div class="setting-row-title">{{ t('settings.appearanceTitle') }}</div>
                    <div class="setting-row-desc">{{ t('settings.appearanceDesc') }}</div>
                  </div>
                  <t-radio-group :value="themeState.mode" variant="default-filled" @change="setThemeMode">
                    <t-radio-button value="light">{{ t('theme.light') }}</t-radio-button>
                    <t-radio-button value="dark">{{ t('theme.dark') }}</t-radio-button>
                    <t-radio-button value="system">{{ t('theme.system') }}</t-radio-button>
                  </t-radio-group>
                </div>

                <div class="setting-row setting-row-divider">
                  <div>
                    <div class="setting-row-title">{{ t('lang.label') }}</div>
                    <div class="setting-row-desc">{{ t('lang.desc') }}</div>
                  </div>
                  <t-radio-group :value="i18nState.locale" variant="default-filled" @change="setLocale">
                    <t-radio-button v-for="loc in LOCALES" :key="loc.value" :value="loc.value">
                      {{ loc.label }}
                    </t-radio-button>
                  </t-radio-group>
                </div>
              </div>
            </div>
          </t-tab-panel>

          <t-tab-panel v-if="user?.is_admin" value="oidc" :label="t('settings.tabOidc')">
            <div class="settings-tab-body">
              <div class="settings-section">
                <h3 class="settings-section-title">{{ t('settings.oidcTitle') }}</h3>
                <p class="settings-section-sub">
                  {{ t('settings.oidcSub') }}
                  <code>{{ oidc.redirect_uri || CALLBACK_PLACEHOLDER }}</code>
                </p>

                <t-collapse v-if="oidc.providers.length" v-model="expandedProviders" class="oidc-collapse">
                  <t-collapse-panel v-for="(p, idx) in oidc.providers" :key="idx" :value="idx">
                    <template #header>
                      <div class="oidc-header">
                        <span class="oidc-header-left">
                          <strong>{{ p.name || p.type || p.op || t('settings.unnamedProvider') }}</strong>
                          <t-tag v-if="p.name && p.type" size="small" variant="light">{{ p.type }}</t-tag>
                          <t-tag v-if="p.saved" size="small" theme="success" variant="light">{{ t('settings.savedTag') }}</t-tag>
                        </span>
                        <span class="oidc-header-right" @click.stop>
                          <t-switch v-model="p.enabled" size="small" />
                          <span class="muted">{{ t('common.enabled') }}</span>
                          <t-button variant="text" theme="danger" size="small" @click.stop="removeProvider(idx)">
                            {{ t('common.delete') }}
                          </t-button>
                        </span>
                      </div>
                    </template>

                    <t-form label-width="116px">
                      <div class="oidc-grid">
                        <t-form-item :label="t('settings.fieldType')">
                          <t-select v-model="p.type" :options="oauthTypes" class="full-width" @change="() => syncOpFromType(p)" />
                        </t-form-item>
                        <t-form-item :label="t('settings.fieldOp')">
                          <div class="full-width">
                            <t-input
                              v-model="p.op"
                              :maxlength="32"
                              :disabled="p.saved"
                              :placeholder="p.saved ? t('settings.opSavedPlaceholder') : t('settings.opAutoPlaceholder')"
                              @change="() => (p.op_fixed = !!p.op)"
                            />
                            <div v-if="p.saved" class="field-hint">{{ t('settings.opSavedHint') }}</div>
                          </div>
                        </t-form-item>
                        <t-form-item :label="t('settings.fieldBtnName')">
                          <t-input v-model="p.name" :maxlength="64" :placeholder="t('settings.btnNamePlaceholder')" />
                        </t-form-item>
                        <t-form-item :label="t('settings.fieldSort')">
                          <t-input-number v-model="p.sort" theme="normal" class="full-width" />
                        </t-form-item>
                      </div>
                      <t-form-item v-if="p.type !== 'github'" label="Issuer">
                        <t-input v-model="p.issuer" :placeholder="t('settings.issuerPlaceholder')" />
                      </t-form-item>
                      <t-form-item label="Client ID">
                        <t-input v-model="p.client_id" placeholder="rustdesk-api" />
                      </t-form-item>
                      <t-form-item label="Client Secret">
                        <t-input
                          v-model="p.client_secret"
                          type="password"
                          :placeholder="p.has_secret && !p.clear_secret ? t('settings.secretSavedPlaceholder') : t('settings.secretFillPlaceholder')"
                        />
                      </t-form-item>
                      <t-form-item label="Scopes">
                        <t-input v-model="p.scopes" :placeholder="t('settings.scopesPlaceholder')" />
                      </t-form-item>
                      <t-form-item label=" ">
                        <div class="oidc-checkbox-row">
                          <t-checkbox v-model="p.auto_register">{{ t('settings.autoRegister') }}</t-checkbox>
                          <t-checkbox v-model="p.pkce_enable">{{ t('settings.enablePkce') }}</t-checkbox>
                          <t-button
                            v-if="p.has_secret && !p.clear_secret"
                            variant="text"
                            theme="danger"
                            @click="markClearSecret(p)"
                          >
                            {{ t('settings.clearSecret') }}
                          </t-button>
                          <span v-if="p.clear_secret" class="muted">{{ t('settings.clearSecretHint') }}</span>
                          <t-button v-if="p.clear_secret" variant="text" size="small" @click="undoClearSecret(p)">
                            {{ t('settings.undo') }}
                          </t-button>
                        </div>
                      </t-form-item>
                    </t-form>
                  </t-collapse-panel>
                </t-collapse>

                <div v-if="oidcLoading" class="muted mb-md">{{ t('settings.oidcLoading') }}</div>
                <div v-else-if="!oidc.providers.length" class="muted mb-md">
                  <template v-if="oidcLoaded">{{ t('settings.oidcEmpty') }}</template>
                  <template v-else>{{ t('settings.oidcLoadFailed') }}</template>
                </div>

                <div class="oidc-actions">
                  <t-button variant="outline" @click="addProvider">
                    <template #icon><t-icon name="add" /></template>
                    {{ t('settings.addProvider') }}
                  </t-button>
                  <t-button theme="primary" :loading="savingOidc" :disabled="!oidcLoaded" @click="saveOidc">
                    {{ t('settings.saveAll') }}
                  </t-button>
                </div>

                <div class="oidc-status">
                  <span>{{ t('settings.currentStatus') }}</span>
                  <StatusDot
                    :status="oidc.enabled ? 'online' : 'offline'"
                    :label="oidc.enabled ? t('settings.oidcEnabled') : t('settings.oidcDisabled')"
                    :pulse="false"
                  />
                </div>
              </div>
            </div>
          </t-tab-panel>

          <t-tab-panel value="system" :label="t('settings.tabSystem')">
            <div class="settings-tab-body settings-stack">
              <div v-if="user?.is_admin" class="settings-section">
                <h3 class="settings-section-title">{{ t('settings.regPolicyTitle') }}</h3>
                <p class="settings-section-sub">{{ t('settings.regPolicySub') }}</p>
                <div class="setting-row">
                  <div>
                    <div class="setting-row-title">{{ t('settings.allowRegTitle') }}</div>
                    <div class="setting-row-desc">{{ t('settings.allowRegDesc') }}</div>
                  </div>
                  <t-switch v-model="settings.allow_registration" :loading="savingSetting" @change="saveSetting" />
                </div>
              </div>

              <div class="settings-section">
                <h3 class="settings-section-title">{{ t('settings.updateTitle') }}</h3>
                <p class="settings-section-sub">
                  {{ t('settings.currentVersion') }} <span class="mono">{{ versionInfo.version || '-' }}</span>
                </p>
                <div class="setting-row">
                  <div>
                    <div v-if="versionInfo.update_available" class="setting-row-title">
                      {{ t('settings.newVersionFound') }} <span class="mono">{{ versionInfo.latest }}</span>
                      <t-link
                        v-if="versionInfo.release_url"
                        theme="primary"
                        class="link-gap"
                        :href="versionInfo.release_url"
                        target="_blank"
                      >
                        {{ t('settings.viewReleaseNotes') }}
                      </t-link>
                    </div>
                    <div v-else-if="versionInfo.checked && !versionInfo.error" class="setting-row-desc">
                      {{ t('settings.upToDate') }}
                    </div>
                    <div v-else-if="versionInfo.error" class="setting-row-desc">
                      {{ t('settings.checkFailed', { error: versionInfo.error }) }}
                    </div>
                    <div v-else class="setting-row-desc">{{ t('settings.checkHint') }}</div>
                  </div>
                  <t-button variant="outline" :loading="checking" @click="checkUpdate">
                    <template #icon><t-icon name="refresh" /></template>
                    {{ t('settings.checkUpdateBtn') }}
                  </t-button>
                </div>
              </div>
            </div>
          </t-tab-panel>
        </t-tabs>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { DialogPlugin, MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import { setUser, store } from '../store'
import { setThemeMode, themeState } from '../theme'
import { LOCALES, i18nState, setLocale, t } from '../i18n'
import StatusDot from '../components/StatusDot.vue'

const user = computed(() => store.user)
const activeTab = ref('account')
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
const oauthTypes = computed(() => [
  { value: 'oidc', label: t('settings.typeOidc') },
  { value: 'github', label: 'GitHub' },
  { value: 'google', label: 'Google' },
])
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
    versionInfo.error = e.message || t('common.loadFailed')
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
    header: t('settings.deleteProviderHeader'),
    body: t('settings.deleteProviderBody', { name: provider.name || provider.op }),
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
    MessagePlugin.success(value ? t('settings.regEnabledToast') : t('settings.regDisabledToast'))
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
    await loadSettings()
  } finally {
    savingSetting.value = false
  }
}

async function saveOidc() {
  if (!oidcLoaded.value) {
    MessagePlugin.warning(t('settings.warnOidcNotLoaded'))
    return
  }
  const seen = new Set()
  const items = []
  for (const [idx, p] of oidc.providers.entries()) {
    const op = (p.op || p.type || '').trim()
    if (!op) {
      MessagePlugin.warning(t('settings.warnMissingOp', { index: idx + 1 }))
      return
    }
    if (seen.has(op)) {
      MessagePlugin.warning(t('settings.warnDuplicateOp', { op }))
      return
    }
    seen.add(op)
    const clientId = (p.client_id || '').trim()
    if (!clientId) {
      MessagePlugin.warning(t('settings.warnMissingClientId', { op }))
      return
    }
    const issuer = (p.issuer || '').trim()
    if (p.type !== 'github' && !issuer) {
      MessagePlugin.warning(t('settings.warnMissingIssuer', { op }))
      return
    }
    if (issuer && !/^https?:\/\//i.test(issuer)) {
      MessagePlugin.warning(t('settings.warnInvalidIssuer', { op }))
      return
    }
    if (!p.has_secret && !p.client_secret && !p.clear_secret) {
      MessagePlugin.warning(t('settings.warnMissingSecret', { op }))
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
        header: t('settings.clearOidcHeader'),
        body: t('settings.clearOidcBody'),
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
    MessagePlugin.success(t('settings.oidcSaved'))
    await loadSettings()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
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
    MessagePlugin.warning(t('settings.warnInvalidEmail'))
    return
  }
  savingProfile.value = true
  try {
    const data = await api.updateProfile({
      display_name: (profile.display_name || '').trim(),
      email,
    })
    if (data?.user) setUser(data.user)
    MessagePlugin.success(t('settings.profileSaved'))
  } catch (e) {
    MessagePlugin.error(e.message || t('common.saveFailed'))
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
    MessagePlugin.warning(t('settings.warnFillComplete'))
    return
  }
  if (form.password.length < 8) {
    MessagePlugin.warning(t('settings.warnNewPasswordLen'))
    return
  }
  if (form.password !== form.confirm) {
    MessagePlugin.warning(t('settings.warnPasswordMismatch'))
    return
  }
  saving.value = true
  try {
    await api.changePassword(form.old, form.password)
    MessagePlugin.success(t('settings.passwordChanged'))
    form.old = ''
    form.password = ''
    form.confirm = ''
  } catch (e) {
    MessagePlugin.error(e.message || t('settings.passwordChangeFailed'))
  } finally {
    saving.value = false
  }
}
</script>

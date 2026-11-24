<template>
  <div class="login-wrap">
    <div class="login-theme-float">
      <t-dropdown :options="langOptions" trigger="click" @click="onLangAction">
        <t-button
          variant="outline"
          shape="circle"
          aria-label="Language"
          :title="t('lang.switchTooltip', { label: currentLangLabel })"
        >
          <template #icon><t-icon name="translate" /></template>
        </t-button>
      </t-dropdown>
      <t-tooltip
        :content="themeState.resolved === 'dark' ? t('theme.switchToLight') : t('theme.switchToDark')"
        placement="bottom"
      >
        <t-button variant="outline" shape="circle" :aria-label="t('theme.appearance')" @click="toggleQuickTheme">
          <template #icon>
            <t-icon :name="themeState.resolved === 'dark' ? 'mode-light' : 'mode-dark'" />
          </template>
        </t-button>
      </t-tooltip>
    </div>

    <div class="login-shell">
      <div class="login-brand-panel" aria-hidden="true">
        <div class="login-brand-top">
          <div class="login-brand-badge">
            <t-icon name="desktop" size="14px" />
            <span>{{ t('login.badge') }}</span>
          </div>
          <h2 class="login-brand-heading">
            {{ t('login.brandHeadingLine1') }}<br />{{ t('login.brandHeadingLine2') }}
          </h2>
          <p class="login-brand-desc">{{ t('login.brandDesc') }}</p>
        </div>

        <ul class="login-brand-features">
          <li>
            <span class="login-feature-dot"><t-icon name="server" size="13px" /></span>
            <span>{{ t('login.feature1') }}</span>
          </li>
          <li>
            <span class="login-feature-dot"><t-icon name="book" size="13px" /></span>
            <span>{{ t('login.feature2') }}</span>
          </li>
          <li>
            <span class="login-feature-dot"><t-icon name="internet" size="13px" /></span>
            <span>{{ t('login.feature3') }}</span>
          </li>
        </ul>

        <div class="login-brand-foot">{{ t('login.brandFoot') }}</div>
      </div>

      <div class="login-card">
        <img class="login-logo" :src="logo" alt="RustDesk" />
        <h1 class="login-title">{{ title }}</h1>
        <p class="login-sub">{{ subtitle }}</p>
        <t-alert
          v-if="fromWebClient && !setupMode && !setupPending"
          theme="info"
          class="login-web-tip"
          :message="t('login.webTip')"
        />
        <t-form v-if="!setupPending" :data="form" label-width="0" :show-error-message="false" @submit="submit">
          <t-form-item name="username">
            <t-input v-model="form.username" size="large" :placeholder="t('login.usernamePlaceholder')" clearable autofocus>
              <template #prefix-icon><t-icon name="user" /></template>
            </t-input>
          </t-form-item>
          <t-form-item name="password">
            <t-input
              v-model="form.password"
              type="password"
              size="large"
              :placeholder="t('login.passwordPlaceholder')"
              @enter="submit"
            >
              <template #prefix-icon><t-icon name="lock-on" /></template>
            </t-input>
          </t-form-item>
          <t-form-item v-if="setupMode || registerMode" name="confirm">
            <t-input
              v-model="form.confirm"
              type="password"
              size="large"
              :placeholder="t('login.confirmPlaceholder')"
              @enter="submit"
            >
              <template #prefix-icon><t-icon name="lock-on" /></template>
            </t-input>
          </t-form-item>
          <t-form-item v-if="setupMode" name="setupToken">
            <t-input v-model="form.setupToken" type="password" size="large" :placeholder="t('login.setupTokenPlaceholder')">
              <template #prefix-icon><t-icon name="key" /></template>
            </t-input>
          </t-form-item>
          <t-button theme="primary" type="submit" size="large" block :loading="loading">
            {{ submitText }}
          </t-button>
        </t-form>
        <div v-if="!setupMode && !setupPending && !registerMode && providers.length" class="login-oauth">
          <div class="login-or"><span>{{ t('login.orOauth') }}</span></div>
          <a
            v-for="p in providers"
            :key="p.op"
            class="login-oauth-btn"
            :class="`oauth-${p.type || 'oidc'}`"
            :href="oauthHref(p)"
          >
            <span class="login-oauth-icon" aria-hidden="true" v-html="oauthIcon(p.type)"></span>
            <span class="login-oauth-text" :title="t('login.oauthBtn', { name: oauthName(p) })">
              {{ t('login.oauthBtn', { name: oauthName(p) }) }}
            </span>
          </a>
        </div>
        <div v-if="!setupMode" class="login-switch">
          <a v-if="!registerMode && allowRegistration" class="login-link" @click="switchMode(true)">{{ t('login.goRegister') }}</a>
          <a v-else-if="registerMode" class="login-link" @click="switchMode(false)">{{ t('login.goLogin') }}</a>
          <span v-if="fromWebClient && !registerMode && allowRegistration" class="login-switch-sep">·</span>
          <a v-if="fromWebClient && !registerMode" class="login-link" @click="goConsoleLogin">{{ t('login.onlyConsole') }}</a>
        </div>
      </div>
    </div>
  </div>
</template>

<script setup>
import { computed, onMounted, reactive, ref } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { MessagePlugin } from 'tdesign-vue-next'
import { api } from '../api'
import logo from '../assets/logo-128.png'
import { setUser } from '../store'
import { setThemeMode, themeState } from '../theme'
import { LOCALES, i18nState, setLocale, t } from '../i18n'
import { updatePageTitle } from '../router'

const router = useRouter()
const route = useRoute()
const form = reactive({ username: '', password: '', confirm: '', setupToken: '' })
const loading = ref(false)
const setupMode = ref(false)
const setupPending = ref(false)
const registerMode = ref(false)
const allowRegistration = ref(false)
const providers = ref([])
const fromWebClient = ref(new URLSearchParams(window.location.search).get('next') === '/web/')

const currentLangLabel = computed(() => LOCALES.find((item) => item.value === i18nState.locale)?.label || '简体中文')
const langOptions = computed(() =>
  LOCALES.map((item) => ({
    content: item.label,
    value: item.value,
    active: i18nState.locale === item.value,
  })),
)

function onLangAction({ value }) {
  setLocale(value)
}

function toggleQuickTheme() {
  setThemeMode(themeState.resolved === 'dark' ? 'light' : 'dark')
}

const PROVIDER_ICONS = {
  // 官方品牌图标：GitHub 用单色 octocat，Google 用四色 G。
  github:
    '<svg viewBox="0 0 16 16" width="18" height="18" fill="currentColor"><path d="M8 0C3.58 0 0 3.58 0 8c0 3.54 2.29 6.53 5.47 7.59.4.07.55-.17.55-.38 0-.19-.01-.82-.01-1.49-2.01.37-2.53-.49-2.69-.94-.09-.23-.48-.94-.82-1.13-.28-.15-.68-.52-.01-.53.63-.01 1.08.58 1.23.82.72 1.21 1.87.87 2.33.66.07-.52.28-.87.51-1.07-1.78-.2-3.64-.89-3.64-3.95 0-.87.31-1.59.82-2.15-.08-.2-.36-1.02.08-2.12 0 0 .67-.21 2.2.82a7.4 7.4 0 0 1 2-.27c.68 0 1.36.09 2 .27 1.53-1.04 2.2-.82 2.2-.82.44 1.1.16 1.92.08 2.12.51.56.82 1.27.82 2.15 0 3.07-1.87 3.75-3.65 3.95.29.25.54.73.54 1.48 0 1.07-.01 1.93-.01 2.2 0 .21.15.46.55.38A8.01 8.01 0 0 0 16 8c0-4.42-3.58-8-8-8Z"/></svg>',
  google:
    '<svg viewBox="0 0 18 18" width="18" height="18"><path fill="#4285F4" d="M17.64 9.2c0-.64-.06-1.25-.16-1.84H9v3.48h4.84a4.14 4.14 0 0 1-1.8 2.72v2.26h2.91c1.7-1.57 2.69-3.88 2.69-6.62Z"/><path fill="#34A853" d="M9 18c2.43 0 4.47-.8 5.96-2.18l-2.91-2.26c-.81.54-1.84.86-3.05.86-2.34 0-4.32-1.58-5.03-3.7H.96v2.33A9 9 0 0 0 9 18Z"/><path fill="#FBBC05" d="M3.97 10.72a5.4 5.4 0 0 1 0-3.44V4.95H.96a9 9 0 0 0 0 8.1l3.01-2.33Z"/><path fill="#EA4335" d="M9 3.58c1.32 0 2.5.45 3.44 1.35l2.58-2.58C13.46.89 11.42 0 9 0A9 9 0 0 0 .96 4.95l3.01 2.33C4.68 5.16 6.66 3.58 9 3.58Z"/></svg>',
  // 通用 OIDC 用钥匙图标，配色取控制台主色。
  oidc:
    '<svg viewBox="0 0 24 24" width="18" height="18" fill="none" stroke="currentColor" stroke-width="1.8" stroke-linecap="round"><circle cx="8" cy="12" r="4"/><path d="M12 12h9"/><path d="M17.5 12v2.5"/><path d="M20.5 12v1.8"/></svg>',
}

function oauthIcon(type) {
  return PROVIDER_ICONS[type] || PROVIDER_ICONS.oidc
}

function oauthName(provider) {
  // 管理员在控制台填的按钮名称优先，留空才用品牌默认名。
  if (provider.name) return provider.name
  if (provider.type === 'github') return 'GitHub'
  if (provider.type === 'google') return 'Google'
  return provider.op
}

function oauthHref(provider) {
  const next = fromWebClient.value ? '&next=%2Fweb%2F' : ''
  return `/api/oidc/console/auth?op=${encodeURIComponent(provider.op)}${next}`
}

const title = computed(() => {
  if (setupMode.value) return t('login.setupTitle')
  if (registerMode.value) return t('login.registerTitle')
  if (fromWebClient.value) return t('login.webTitle')
  return t('login.consoleTitle')
})
const subtitle = computed(() => {
  if (setupMode.value) return t('login.setupSub')
  if (setupPending.value) return t('login.setupPendingSub')
  if (registerMode.value) return t('login.registerSub')
  if (fromWebClient.value) return t('login.webSub')
  return t('login.consoleSub')
})
const submitText = computed(() => {
  if (setupMode.value) return t('login.submitSetup')
  if (registerMode.value) return t('login.submitRegister')
  if (fromWebClient.value) return t('login.submitWeb')
  return t('login.submitLogin')
})

function switchMode(toRegister) {
  registerMode.value = toRegister
  form.password = ''
  form.confirm = ''
}

function goConsoleLogin() {
  fromWebClient.value = false
  window.history.replaceState(null, '', '/console/#/login')
  updatePageTitle(route)
}

function goNext() {
  if (fromWebClient.value) {
    window.location.replace('/web/')
    return
  }
  const redirect = route.query.redirect
  router.replace(
    typeof redirect === 'string' && redirect.startsWith('/') && !redirect.startsWith('//')
      ? redirect
      : '/dashboard',
  )
}

async function submit() {
  if (!form.username || !form.password) {
    MessagePlugin.warning(t('login.warnEmpty'))
    return
  }
  loading.value = true
  try {
    if (setupMode.value) {
      if (form.password.length < 8) {
        MessagePlugin.warning(t('login.warnPasswordLen'))
        return
      }
      if (form.password !== form.confirm) {
        MessagePlugin.warning(t('login.warnPasswordMismatch'))
        return
      }
      const data = await api.setup({
        username: form.username.trim(),
        password: form.password,
        setup_token: form.setupToken,
      })
      setUser(data.user)
      MessagePlugin.success(t('login.adminCreated'))
      goNext()
      return
    }
    if (registerMode.value) {
      if (form.password.length < 8) {
        MessagePlugin.warning(t('login.warnPasswordLen'))
        return
      }
      if (form.password !== form.confirm) {
        MessagePlugin.warning(t('login.warnPasswordMismatch'))
        return
      }
      await api.register({ username: form.username.trim(), password: form.password })
      MessagePlugin.success(t('login.registerSuccess'))
      switchMode(false)
      return
    }
    const data = await api.login(form.username.trim(), form.password)
    setUser(data.user)
    MessagePlugin.success(t('login.loginSuccess'))
    goNext()
  } catch (e) {
    MessagePlugin.error(e.message || t('common.operationFailed'))
  } finally {
    loading.value = false
  }
}

onMounted(async () => {
  try {
    const data = await api.setupStatus()
    setupMode.value = !!data.web_setup_enabled
    setupPending.value = !!data.needs_setup && !setupMode.value
    allowRegistration.value = !data.needs_setup && !!data.allow_registration
  } catch (e) {
    /* 忽略：按登录处理 */
  }
  try {
    const data = await api.loginOptions()
    providers.value = data.providers || []
  } catch (e) {
    /* 忽略：未配置第三方登录时不出按钮 */
    providers.value = []
  }
})
</script>

<style scoped>
.login-card :deep(.t-form__item) {
  display: block;
  margin-bottom: 16px !important;
}

.login-card :deep(.t-form__label) {
  display: none;
}

.login-card :deep(.t-form__controls) {
  flex: 1;
  margin-left: 0 !important;
}

.login-card :deep(.t-form__controls-content) {
  width: 100%;
}

.login-card :deep(.t-input__wrap) {
  width: 100%;
}
</style>

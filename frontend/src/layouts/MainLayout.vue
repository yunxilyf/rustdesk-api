<template>
  <t-layout class="app-layout">
    <t-aside class="app-aside" :width="collapsed ? '68px' : '236px'">
      <div class="brand" :class="{ 'is-collapsed': collapsed }" @click="router.push('/dashboard')">
        <img class="brand-mark" :src="logo" alt="RustDesk" />
        <div v-if="!collapsed" class="brand-text">
          <div class="brand-name">RustDesk</div>
          <div class="brand-sub">{{ t('app.brandSub') }}</div>
        </div>
      </div>

      <t-menu
        v-model="active"
        :theme="themeState.resolved"
        :collapsed="collapsed"
        :width="['236px', '68px']"
        class="app-menu"
        @change="onMenuChange"
      >
        <t-menu-group v-for="group in menuGroups" :key="group.key" :title="group.name">
          <t-menu-item v-for="item in group.items" :key="item.path" :value="item.path">
            <template #icon><t-icon :name="item.icon" /></template>
            {{ item.title }}
          </t-menu-item>
        </t-menu-group>

        <t-menu-group :title="t('nav.sections.tools')">
          <t-menu-item value="/web/" class="menu-item-web">
            <template #icon><t-icon name="internet" /></template>
            <span class="menu-web-label">
              <span>{{ t('nav.webClient') }}</span>
              <t-icon v-if="!collapsed" name="jump" size="13px" class="menu-web-jump" />
            </span>
          </t-menu-item>
        </t-menu-group>
      </t-menu>

      <div class="aside-footer" :class="{ 'is-collapsed': collapsed }">
        <span v-if="!collapsed" class="aside-version muted">
          <span class="aside-ver-dot" />
          {{ appVersion ? `v${appVersion}` : 'RustDesk API' }}
        </span>
        <t-tooltip :content="collapsed ? t('nav.expandSidebar') : t('nav.collapseSidebar')" placement="right">
          <t-button variant="text" shape="square" size="small" @click="toggleCollapsed">
            <template #icon><t-icon :name="collapsed ? 'menu-unfold' : 'menu-fold'" /></template>
          </t-button>
        </t-tooltip>
      </div>
    </t-aside>

    <t-layout class="app-main">
      <t-header class="app-header">
        <div class="header-left">
          <t-button class="mobile-menu-btn" variant="text" shape="square" @click="mobileNavOpen = true">
            <template #icon><t-icon name="menu" /></template>
          </t-button>
          <div class="crumb">
            <span v-if="currentGroup" class="crumb-group">{{ currentGroup }}</span>
            <t-icon v-if="currentGroup" name="chevron-right" size="14px" class="crumb-sep" />
            <span class="crumb-current">{{ currentTitle }}</span>
          </div>
        </div>

        <div class="header-right">
          <t-dropdown :options="langOptions" trigger="click" @click="onLangAction">
            <t-button
              variant="text"
              shape="square"
              class="header-icon-btn"
              aria-label="Language"
              :title="t('lang.switchTooltip', { label: currentLangLabel })"
            >
              <template #icon><t-icon name="translate" /></template>
            </t-button>
          </t-dropdown>

          <t-dropdown :options="themeOptions" trigger="click" @click="onThemeAction">
            <t-button
              variant="text"
              shape="square"
              class="header-icon-btn"
              :aria-label="t('theme.appearance')"
              :title="t('theme.switchTooltip', { label: themeLabel })"
            >
              <template #icon>
                <t-icon :name="themeState.resolved === 'dark' ? 'mode-dark' : 'mode-light'" />
              </template>
            </t-button>
          </t-dropdown>

          <t-tag v-if="user?.is_admin" theme="primary" variant="light" size="small" class="role-tag">{{ t('common.admin') }}</t-tag>
          <t-tag v-else theme="default" variant="light" size="small" class="role-tag">{{ t('common.user') }}</t-tag>

          <t-dropdown :options="userOptions" trigger="click" @click="onUserAction">
            <span class="user-chip">
              <UserAvatar :name="displayName" :size="26" />
              <span class="user-name">{{ displayName }}</span>
              <t-icon name="chevron-down" size="15px" class="muted" />
            </span>
          </t-dropdown>
        </div>
      </t-header>

      <t-content class="app-content">
        <router-view v-slot="{ Component }">
          <transition name="fade-slide" mode="out-in">
            <component :is="Component" />
          </transition>
        </router-view>
      </t-content>
    </t-layout>

    <t-drawer v-model:visible="mobileNavOpen" placement="left" size="256px" :header="false" :footer="false">
      <div class="mobile-drawer-body">
        <div class="brand" @click="onMobileNav('/dashboard')">
          <img class="brand-mark" :src="logo" alt="RustDesk" />
          <div class="brand-text">
            <div class="brand-name">RustDesk</div>
            <div class="brand-sub">{{ t('app.brandSub') }}</div>
          </div>
        </div>
        <t-menu
          v-if="mobileNavOpen"
          :value="active"
          :theme="themeState.resolved"
          width="100%"
          class="mobile-menu"
          @change="onMobileNav"
        >
          <t-menu-group v-for="group in menuGroups" :key="group.key" :title="group.name">
            <t-menu-item v-for="item in group.items" :key="item.path" :value="item.path">
              <template #icon><t-icon :name="item.icon" /></template>
              {{ item.title }}
            </t-menu-item>
          </t-menu-group>
          <t-menu-group :title="t('nav.sections.tools')">
            <t-menu-item value="/web/" class="menu-item-web">
              <template #icon><t-icon name="internet" /></template>
              <span class="menu-web-label">
                <span>{{ t('nav.webClient') }}</span>
                <t-icon name="jump" size="13px" class="menu-web-jump" />
              </span>
            </t-menu-item>
          </t-menu-group>
        </t-menu>
      </div>
    </t-drawer>
  </t-layout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { clearUser, store } from '../store'
import { setThemeMode, themeState } from '../theme'
import { LOCALES, i18nState, setLocale, t } from '../i18n'
import UserAvatar from '../components/UserAvatar.vue'
import logo from '../assets/logo-128.png'

const AUTH_CHANNEL_NAME = 'rustdesk-auth'
const AUTH_LOGOUT_STORAGE_KEY = 'rd:auth_logout'
const SIDEBAR_COLLAPSED_KEY = 'rd:sidebar_collapsed'
const GROUP_ORDER = ['workspace', 'assets', 'audit', 'system']

const route = useRoute()
const router = useRouter()
const user = computed(() => store.user)
const mobileNavOpen = ref(false)
const collapsed = ref(false)

try {
  collapsed.value = window.localStorage.getItem(SIDEBAR_COLLAPSED_KEY) === '1'
} catch (e) {
  collapsed.value = false
}

function toggleCollapsed() {
  collapsed.value = !collapsed.value
  try {
    window.localStorage.setItem(SIDEBAR_COLLAPSED_KEY, collapsed.value ? '1' : '0')
  } catch (e) {
    /* ignore */
  }
}

const menuGroups = computed(() => {
  // 显式读取 i18nState.locale 以响应语言切换
  void i18nState.locale
  const root = router.options.routes.find((r) => r.path === '/')
  const items = (root?.children || [])
    .filter((child) => child.meta?.titleKey)
    .filter((child) => !child.meta.admin || user.value?.is_admin)
    .map((child) => ({
      path: '/' + child.path,
      title: t(child.meta.titleKey),
      icon: child.meta.icon,
      groupKey: child.meta.groupKey || 'workspace',
    }))

  const map = new Map()
  for (const key of GROUP_ORDER) map.set(key, [])
  for (const item of items) {
    if (!map.has(item.groupKey)) map.set(item.groupKey, [])
    map.get(item.groupKey).push(item)
  }
  return Array.from(map.entries())
    .filter(([, list]) => list.length > 0)
    .map(([key, list]) => ({ key, name: t(`nav.sections.${key}`), items: list }))
})

const active = ref(route.path)
watch(
  () => route.path,
  (path) => {
    active.value = path
    mobileNavOpen.value = false
  },
)

const appVersion = ref('')
let authChannel = null

function handleRemoteLogout() {
  clearUser()
  if (route.name !== 'login') {
    router.replace({ name: 'login' })
  }
}

function onStorageSync(ev) {
  if (ev.key === AUTH_LOGOUT_STORAGE_KEY && ev.newValue) {
    handleRemoteLogout()
  }
}

onMounted(async () => {
  window.addEventListener('storage', onStorageSync)
  if (typeof window.BroadcastChannel === 'function') {
    try {
      authChannel = new window.BroadcastChannel(AUTH_CHANNEL_NAME)
      authChannel.onmessage = (ev) => {
        if (ev?.data?.type === 'logout') handleRemoteLogout()
      }
    } catch (e) {
      authChannel = null
    }
  }
  try {
    const data = await api.getVersion()
    appVersion.value = String(data.version || '').replace(/^v/, '')
  } catch (e) {
    /* 版本号获取失败不影响使用 */
  }
})

onBeforeUnmount(() => {
  window.removeEventListener('storage', onStorageSync)
  if (authChannel) {
    try {
      authChannel.close()
    } catch (e) {
      /* ignore */
    }
    authChannel = null
  }
})

const currentTitle = computed(() => (route.meta?.titleKey ? t(route.meta.titleKey) : ''))
const currentGroup = computed(() => (route.meta?.groupKey ? t(`nav.sections.${route.meta.groupKey}`) : ''))
const displayName = computed(() => user.value?.display_name || user.value?.name || user.value?.username || t('common.notLoggedIn'))

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

const themeLabel = computed(() => {
  void i18nState.locale
  if (themeState.mode === 'light') return t('theme.light')
  if (themeState.mode === 'dark') return t('theme.dark')
  return t('theme.system')
})

const themeOptions = computed(() => {
  void i18nState.locale
  return [
    { content: t('theme.lightMode'), value: 'light', active: themeState.mode === 'light' },
    { content: t('theme.darkMode'), value: 'dark', active: themeState.mode === 'dark' },
    { content: t('theme.system'), value: 'system', active: themeState.mode === 'system' },
  ]
})

function onThemeAction({ value }) {
  setThemeMode(value)
}

function clearWebClientSession() {
  try {
    const raw = window.localStorage.getItem('rd:local')
    if (!raw) return
    const data = JSON.parse(raw)
    if (!data || typeof data !== 'object') return
    delete data.access_token
    delete data.user_info
    delete data.verifier
    window.localStorage.setItem('rd:local', JSON.stringify(data))
  } catch (e) {
    /* 忽略 localStorage 不可用或格式异常 */
  }
}

function broadcastAuthLogout() {
  const ts = Date.now()
  try {
    window.localStorage.setItem(AUTH_LOGOUT_STORAGE_KEY, String(ts))
  } catch (e) {
    /* ignore */
  }
  if (typeof window.BroadcastChannel === 'function') {
    try {
      const ch = new window.BroadcastChannel(AUTH_CHANNEL_NAME)
      ch.postMessage({ type: 'logout', ts })
      ch.close()
    } catch (e) {
      /* ignore */
    }
  }
}

function onMenuChange(value) {
  if (value === '/web/') {
    window.open('/web/', '_blank', 'noopener')
    active.value = route.path
    return
  }
  if (value !== route.path) router.push(value)
}

function onMobileNav(value) {
  mobileNavOpen.value = false
  onMenuChange(value)
}

const userOptions = computed(() => {
  void i18nState.locale
  return [
    { content: t('nav.settings'), value: 'settings' },
    { content: t('nav.logout'), value: 'logout', theme: 'error' },
  ]
})

async function onUserAction({ value }) {
  if (value === 'settings') {
    router.push('/settings')
  } else if (value === 'logout') {
    try {
      await api.logout()
    } catch (e) {
      /* ignore */
    }
    clearWebClientSession()
    broadcastAuthLogout()
    clearUser()
    router.replace({ name: 'login' })
  }
}
</script>

<style scoped>
.app-layout {
  height: 100%;
  background: var(--app-bg);
}

.app-aside {
  background: var(--app-surface);
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
  transition: width 0.2s cubic-bezier(0.38, 0, 0.24, 1);
  overflow: hidden;
  flex: none;
}

.brand {
  display: flex;
  align-items: center;
  gap: 11px;
  padding: 16px 18px 14px;
  cursor: pointer;
  user-select: none;
  border-bottom: 1px solid var(--app-border);
  height: 58px;
}

.brand.is-collapsed {
  justify-content: center;
  padding: 16px 0;
}

.brand-mark {
  width: 32px;
  height: 32px;
  border-radius: 9px;
  object-fit: cover;
  flex: none;
  box-shadow: 0 4px 12px rgba(24, 104, 242, 0.24);
}

.brand-text {
  min-width: 0;
  overflow: hidden;
}

.brand-name {
  font-size: 15px;
  font-weight: 700;
  line-height: 18px;
  letter-spacing: -0.01em;
  color: var(--app-text);
}

.brand-sub {
  font-size: 11.5px;
  color: var(--app-muted);
  margin-top: 1px;
}

.app-menu {
  flex: 1;
  overflow-y: auto;
  overflow-x: hidden;
  background: transparent;
}

.app-menu :deep(.t-menu) {
  padding: 8px 10px 12px;
  background: transparent;
}

.app-menu.t-is-collapsed :deep(.t-menu) {
  padding: 8px 6px;
}

.app-menu :deep(.t-menu-group) {
  margin-bottom: 6px;
}

.app-menu :deep(.t-menu-group__title) {
  font-size: 11px;
  font-weight: 600;
  letter-spacing: 0.04em;
  color: var(--app-muted);
  padding: 10px 12px 4px;
  height: auto;
  line-height: 16px;
}

.app-menu.t-is-collapsed :deep(.t-menu-group__title) {
  display: none;
}

.app-menu :deep(.t-menu__item) {
  border-radius: 8px;
  margin-bottom: 2px;
  height: 38px;
  line-height: 38px;
  font-size: 13.5px;
  font-weight: 500;
}

.app-menu.t-menu--dark :deep(.t-menu__item.t-is-active) {
  background: var(--app-active-item-bg);
  color: var(--td-brand-color-8);
}

.app-menu.t-menu--dark :deep(.t-menu__item.t-is-active .t-icon) {
  color: var(--td-brand-color-8);
}

.app-menu :deep(.menu-item-web) {
  background: var(--app-web-cta-bg);
  border: 1px solid var(--app-web-cta-border);
  color: var(--td-brand-color);
  margin-top: 4px;
}

.app-menu :deep(.menu-item-web:hover) {
  background: var(--app-web-cta-hover);
  color: var(--td-brand-color);
}

.app-menu :deep(.menu-item-web .t-icon) {
  color: var(--td-brand-color);
}

.menu-web-label {
  display: inline-flex;
  align-items: center;
  justify-content: space-between;
  width: 100%;
  gap: 8px;
}

.menu-web-jump {
  opacity: 0.72;
  flex: none;
}

.aside-footer {
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 10px 14px;
  border-top: 1px solid var(--app-border);
  min-height: 46px;
}

.aside-footer.is-collapsed {
  justify-content: center;
  padding: 10px 6px;
}

.aside-version {
  font-size: 12px;
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-variant-numeric: tabular-nums;
}

.aside-ver-dot {
  width: 6px;
  height: 6px;
  border-radius: 50%;
  background: var(--app-status-online);
}

.app-main {
  min-width: 0;
  background: var(--app-bg);
}

.app-header {
  height: 58px;
  background: var(--app-header-bg);
  backdrop-filter: blur(10px);
  border-bottom: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
  position: sticky;
  top: 0;
  z-index: 20;
}

.header-left {
  display: flex;
  align-items: center;
  gap: 10px;
  min-width: 0;
}

.mobile-menu-btn {
  display: none;
}

.crumb {
  display: inline-flex;
  align-items: center;
  gap: 6px;
  font-size: 13.5px;
  min-width: 0;
}

.crumb-group {
  color: var(--app-muted);
}

.crumb-sep {
  color: var(--app-muted);
  opacity: 0.65;
}

.crumb-current {
  color: var(--app-text);
  font-weight: 500;
}

.header-right {
  display: flex;
  align-items: center;
  gap: 8px;
}

.header-icon-btn {
  color: var(--app-text-secondary);
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 10px 4px 4px;
  border-radius: 999px;
  border: 1px solid transparent;
  transition: background-color 0.14s ease, border-color 0.14s ease;
}

.user-chip:hover {
  background: var(--app-surface-hover);
  border-color: var(--app-border);
}

.user-name {
  font-size: 13.5px;
  font-weight: 500;
  color: var(--app-text);
  max-width: 140px;
  overflow: hidden;
  text-overflow: ellipsis;
  white-space: nowrap;
}

.app-content {
  background: var(--app-bg);
  overflow: auto;
}

.mobile-drawer-body {
  display: flex;
  flex-direction: column;
  height: 100%;
  margin: -24px;
}

.mobile-menu :deep(.t-menu) {
  padding: 8px 10px;
  background: transparent;
}

.mobile-menu :deep(.t-menu-group__title) {
  font-size: 11px;
  font-weight: 600;
  color: var(--app-muted);
  padding: 10px 12px 4px;
}

.mobile-menu :deep(.t-menu__item) {
  border-radius: 8px;
  margin-bottom: 2px;
  height: 38px;
  line-height: 38px;
}

.mobile-menu :deep(.menu-item-web) {
  background: var(--app-web-cta-bg);
  border: 1px solid var(--app-web-cta-border);
  color: var(--td-brand-color);
  margin-top: 4px;
}

.mobile-menu.t-menu--dark :deep(.t-menu__item.t-is-active) {
  background: var(--app-active-item-bg);
  color: var(--td-brand-color-8);
}

.mobile-menu.t-menu--dark :deep(.t-menu__item.t-is-active .t-icon) {
  color: var(--td-brand-color-8);
}

@media (max-width: 900px) {
  .app-aside {
    display: none;
  }

  .mobile-menu-btn {
    display: inline-flex;
  }

  .app-header {
    padding: 0 14px;
  }

  .role-tag,
  .crumb-group,
  .crumb-sep {
    display: none;
  }
}
</style>

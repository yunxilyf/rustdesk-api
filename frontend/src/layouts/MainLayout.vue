<template>
  <t-layout class="app-layout">
    <t-aside class="app-aside" width="224px">
      <div class="brand">
        <img class="brand-mark" :src="logo" alt="RustDesk" />
        <div>
          <div class="brand-name">RustDesk</div>
          <div class="brand-sub">管理控制台</div>
        </div>
      </div>
      <t-menu v-model="active" theme="light" class="app-menu" @change="onMenuChange">
        <t-menu-item v-for="item in menus" :key="item.path" :value="item.path">
          <template #icon><t-icon :name="item.icon" /></template>
          {{ item.title }}
        </t-menu-item>
        <t-menu-item value="/web/">
          <template #icon><t-icon name="internet" /></template>
          网页远控
        </t-menu-item>
      </t-menu>
      <div class="aside-version muted">v{{ appVersion }}</div>
    </t-aside>

    <t-layout>
      <t-header class="app-header">
        <div class="crumb">{{ currentTitle }}</div>
        <div class="header-right">
          <t-tag v-if="user?.is_admin" theme="primary" variant="light" size="small">管理员</t-tag>
          <t-tag v-else theme="default" variant="light" size="small">普通用户</t-tag>
          <t-dropdown :options="userOptions" trigger="click" @click="onUserAction">
            <span class="user-chip">
              <span class="user-name">{{ displayName }}</span>
              <t-icon name="chevron-down" size="16px" />
            </span>
          </t-dropdown>
        </div>
      </t-header>
      <t-content class="app-content">
        <router-view v-slot="{ Component }">
          <component :is="Component" />
        </router-view>
      </t-content>
    </t-layout>
  </t-layout>
</template>

<script setup>
import { computed, onBeforeUnmount, onMounted, ref, watch } from 'vue'
import { useRoute, useRouter } from 'vue-router'
import { api } from '../api'
import { clearUser, store } from '../store'
import logo from '../assets/logo-128.png'

const AUTH_CHANNEL_NAME = 'rustdesk-auth'
const AUTH_LOGOUT_STORAGE_KEY = 'rd:auth_logout'

const route = useRoute()
const router = useRouter()
const user = computed(() => store.user)

const menus = computed(() => {
  const root = router.options.routes.find((r) => r.path === '/')
  return (root?.children || [])
    .filter((child) => child.meta?.title)
    .filter((child) => !child.meta.admin || user.value?.is_admin)
    .map((child) => ({ path: '/' + child.path, title: child.meta.title, icon: child.meta.icon }))
})

const active = ref(route.path)
watch(
  () => route.path,
  (path) => {
    active.value = path
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

const currentTitle = computed(() => route.meta?.title || '')
const displayName = computed(() => user.value?.display_name || user.value?.name || user.value?.username || '未登录')

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

const userOptions = computed(() => [
  { content: '个人设置', value: 'settings' },
  { content: '退出登录', value: 'logout', theme: 'error' },
])

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
}

.aside-version {
  padding: 10px 20px 14px;
  font-size: 12px;
}

.app-aside {
  background: #fff;
  border-right: 1px solid var(--app-border);
  display: flex;
  flex-direction: column;
}

.brand {
  display: flex;
  align-items: center;
  gap: 10px;
  padding: 18px 20px 14px;
}

.brand-mark {
  width: 34px;
  height: 34px;
  border-radius: 9px;
  background: linear-gradient(135deg, #0052d9, #3f8cff);
  color: #fff;
  font-weight: 700;
  font-size: 14px;
  display: flex;
  align-items: center;
  justify-content: center;
  letter-spacing: 0.5px;
  object-fit: cover;
  flex: none;
  box-shadow: 0 4px 10px rgba(0, 82, 217, 0.22);
}

.brand-name {
  font-size: 15px;
  font-weight: 600;
  line-height: 18px;
}

.brand-sub {
  font-size: 12px;
  color: var(--app-muted);
}

.app-menu {
  flex: 1;
  overflow: auto;
  padding: 6px 8px;
}

.app-header {
  height: 56px;
  background: #fff;
  border-bottom: 1px solid var(--app-border);
  display: flex;
  align-items: center;
  justify-content: space-between;
  padding: 0 24px;
}

.crumb {
  font-size: 14px;
  color: var(--app-muted);
}

.header-right {
  display: flex;
  align-items: center;
  gap: 12px;
}

.user-chip {
  display: inline-flex;
  align-items: center;
  gap: 8px;
  cursor: pointer;
  padding: 4px 8px;
  border-radius: 8px;
}

.user-chip:hover {
  background: #f3f5f9;
}

.user-name {
  font-size: 14px;
}

.app-content {
  background: var(--app-bg);
  overflow: auto;
}
</style>

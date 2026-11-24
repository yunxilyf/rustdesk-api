import { createRouter, createWebHashHistory } from 'vue-router'
import { loadUser, store } from './store'
import { t } from './i18n'
import Login from './views/Login.vue'
import MainLayout from './layouts/MainLayout.vue'
import Dashboard from './views/Dashboard.vue'
import Devices from './views/Devices.vue'
import AddressBooks from './views/AddressBooks.vue'
import Groups from './views/Groups.vue'
import Users from './views/Users.vue'
import ConnLogs from './views/ConnLogs.vue'
import FileLogs from './views/FileLogs.vue'
import Settings from './views/Settings.vue'

const routes = [
  { path: '/login', name: 'login', component: Login, meta: { public: true, titleKey: 'nav.login' } },
  {
    path: '/',
    component: MainLayout,
    children: [
      { path: '', redirect: '/dashboard' },
      {
        path: 'dashboard',
        name: 'dashboard',
        component: Dashboard,
        meta: { titleKey: 'nav.dashboard', groupKey: 'workspace', icon: 'dashboard' },
      },
      {
        path: 'devices',
        name: 'devices',
        component: Devices,
        meta: { titleKey: 'nav.devices', groupKey: 'assets', icon: 'desktop' },
      },
      {
        path: 'addressbooks',
        name: 'addressbooks',
        component: AddressBooks,
        meta: { titleKey: 'nav.addressbooks', groupKey: 'assets', icon: 'book' },
      },
      {
        path: 'groups',
        name: 'groups',
        component: Groups,
        meta: { titleKey: 'nav.groups', groupKey: 'assets', icon: 'folder' },
      },
      {
        path: 'conn-logs',
        name: 'conn-logs',
        component: ConnLogs,
        meta: { titleKey: 'nav.connLogs', groupKey: 'audit', icon: 'history' },
      },
      {
        path: 'file-logs',
        name: 'file-logs',
        component: FileLogs,
        meta: { titleKey: 'nav.fileLogs', groupKey: 'audit', icon: 'file' },
      },
      {
        path: 'users',
        name: 'users',
        component: Users,
        meta: { titleKey: 'nav.users', groupKey: 'system', icon: 'usergroup', admin: true },
      },
      {
        path: 'settings',
        name: 'settings',
        component: Settings,
        meta: { titleKey: 'nav.settings', groupKey: 'system', icon: 'setting' },
      },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

export function updatePageTitle(to) {
  const nextIsWeb = new URLSearchParams(window.location.search).get('next') === '/web/'
  if (to?.name === 'login' && nextIsWeb) {
    document.title = t('app.webLoginTitle')
    return
  }
  const titleKey = to?.meta?.titleKey
  document.title = titleKey ? `${t(titleKey)} · ${t('app.title')}` : t('app.title')
}

router.beforeEach(async (to) => {
  const nextIsWeb = new URLSearchParams(window.location.search).get('next') === '/web/'
  updatePageTitle(to)
  if (to.meta.public) {
    if (to.name === 'login' && nextIsWeb) {
      const user = await loadUser()
      if (user) {
        window.location.replace('/web/')
        return false
      }
    }
    return true
  }
  const user = await loadUser()
  if (!user) return { name: 'login', query: { redirect: to.fullPath } }
  if (nextIsWeb) {
    window.location.replace('/web/')
    return false
  }
  if (to.meta.admin && !store.user?.is_admin) return { name: 'dashboard' }
  return true
})

export default router

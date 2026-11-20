import { createRouter, createWebHashHistory } from 'vue-router'
import { loadUser, store } from './store'
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
  { path: '/login', name: 'login', component: Login, meta: { public: true, title: '登录' } },
  {
    path: '/',
    component: MainLayout,
    children: [
      { path: '', redirect: '/dashboard' },
      { path: 'dashboard', name: 'dashboard', component: Dashboard, meta: { title: '概览', icon: 'dashboard' } },
      { path: 'devices', name: 'devices', component: Devices, meta: { title: '设备', icon: 'desktop' } },
      { path: 'addressbooks', name: 'addressbooks', component: AddressBooks, meta: { title: '地址簿', icon: 'book' } },
      { path: 'groups', name: 'groups', component: Groups, meta: { title: '设备分组', icon: 'folder' } },
      { path: 'users', name: 'users', component: Users, meta: { title: '用户', icon: 'usergroup', admin: true } },
      { path: 'conn-logs', name: 'conn-logs', component: ConnLogs, meta: { title: '连接日志', icon: 'history' } },
      { path: 'file-logs', name: 'file-logs', component: FileLogs, meta: { title: '文件日志', icon: 'file' } },
      { path: 'settings', name: 'settings', component: Settings, meta: { title: '个人设置', icon: 'setting' } },
    ],
  },
  { path: '/:pathMatch(.*)*', redirect: '/dashboard' },
]

const router = createRouter({
  history: createWebHashHistory(),
  routes,
})

router.beforeEach(async (to) => {
  document.title = to.meta.title ? `${to.meta.title} · RustDesk 控制台` : 'RustDesk 控制台'
  if (to.meta.public) return true
  const user = await loadUser()
  if (!user) return { name: 'login', query: { redirect: to.fullPath } }
  if (to.meta.admin && !store.user?.is_admin) return { name: 'dashboard' }
  return true
})

export default router

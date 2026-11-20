import { reactive } from 'vue'
import { api } from './api'

export const store = reactive({
  user: null,
  loaded: false,
})

export async function loadUser(force = false) {
  if (store.loaded && !force) return store.user
  try {
    const data = await api.me()
    store.user = data.user
  } catch (e) {
    store.user = null
  } finally {
    store.loaded = true
  }
  return store.user
}

export function setUser(user) {
  store.user = user
  store.loaded = true
}

export function clearUser() {
  store.user = null
  store.loaded = true
}

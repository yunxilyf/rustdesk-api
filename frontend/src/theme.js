import { reactive } from 'vue'

const THEME_STORAGE_KEY = 'rd:console_theme'
const VALID_MODES = ['system', 'light', 'dark']

export const themeState = reactive({
  mode: 'system',
  resolved: 'light',
})

let mediaQuery = null
let initialized = false

function readStoredMode() {
  try {
    const raw = window.localStorage.getItem(THEME_STORAGE_KEY)
    return VALID_MODES.includes(raw) ? raw : 'system'
  } catch (e) {
    return 'system'
  }
}

function resolveMode(mode) {
  if (mode === 'dark' || mode === 'light') return mode
  if (typeof window !== 'undefined' && window.matchMedia) {
    return window.matchMedia('(prefers-color-scheme: dark)').matches ? 'dark' : 'light'
  }
  return 'light'
}

function applyTheme() {
  const resolved = resolveMode(themeState.mode)
  themeState.resolved = resolved
  if (typeof document !== 'undefined') {
    document.documentElement.setAttribute('theme-mode', resolved)
    document.documentElement.style.colorScheme = resolved
  }
}

export function setThemeMode(mode) {
  if (!VALID_MODES.includes(mode)) return
  themeState.mode = mode
  try {
    window.localStorage.setItem(THEME_STORAGE_KEY, mode)
  } catch (e) {
    /* ignore storage errors */
  }
  applyTheme()
}

export function initTheme() {
  if (initialized) {
    applyTheme()
    return
  }
  initialized = true
  themeState.mode = readStoredMode()
  applyTheme()
  if (typeof window !== 'undefined' && window.matchMedia) {
    mediaQuery = window.matchMedia('(prefers-color-scheme: dark)')
    const onChange = () => {
      if (themeState.mode === 'system') applyTheme()
    }
    if (typeof mediaQuery.addEventListener === 'function') {
      mediaQuery.addEventListener('change', onChange)
    } else if (typeof mediaQuery.addListener === 'function') {
      mediaQuery.addListener(onChange)
    }
  }
}

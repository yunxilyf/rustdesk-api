import { computed, reactive } from 'vue'
import zhCNConfig from 'tdesign-vue-next/es/locale/zh_CN'
import enUSConfig from 'tdesign-vue-next/es/locale/en_US'
import zhCN from './locales/zh-CN'
import enUS from './locales/en-US'

const LOCALE_STORAGE_KEY = 'rd:console_lang'

export const LOCALES = [
  { value: 'zh-CN', label: '简体中文', short: '中' },
  { value: 'en-US', label: 'English', short: 'EN' },
]

const VALID_LOCALES = LOCALES.map((item) => item.value)
const MESSAGES = {
  'zh-CN': zhCN,
  'en-US': enUS,
}
const TD_CONFIGS = {
  'zh-CN': zhCNConfig,
  'en-US': enUSConfig,
}

export const i18nState = reactive({
  locale: 'zh-CN',
})

function readStoredLocale() {
  try {
    const raw = window.localStorage.getItem(LOCALE_STORAGE_KEY)
    return VALID_LOCALES.includes(raw) ? raw : 'zh-CN'
  } catch (e) {
    return 'zh-CN'
  }
}

function applyLocale() {
  if (typeof document !== 'undefined') {
    document.documentElement.lang = i18nState.locale
  }
}

export function initI18n() {
  i18nState.locale = readStoredLocale()
  applyLocale()
}

export function setLocale(locale) {
  if (!VALID_LOCALES.includes(locale)) return
  i18nState.locale = locale
  try {
    window.localStorage.setItem(LOCALE_STORAGE_KEY, locale)
  } catch (e) {
    /* ignore storage errors */
  }
  applyLocale()
}

function lookup(dict, key) {
  const parts = String(key || '').split('.')
  let cur = dict
  for (const part of parts) {
    if (cur && typeof cur === 'object' && part in cur) {
      cur = cur[part]
    } else {
      return undefined
    }
  }
  return typeof cur === 'string' ? cur : undefined
}

export function t(key, params) {
  let text = lookup(MESSAGES[i18nState.locale], key)
  if (text === undefined) text = lookup(MESSAGES['zh-CN'], key)
  if (text === undefined) return key
  if (!params) return text
  return text.replace(/\{(\w+)\}/g, (_, k) => (params[k] !== undefined && params[k] !== null ? String(params[k]) : ''))
}

export const tdLocale = computed(() => TD_CONFIGS[i18nState.locale] || zhCNConfig)

export function useI18n() {
  const locale = computed(() => i18nState.locale)
  return {
    t,
    locale,
    locales: LOCALES,
    setLocale,
    tdLocale,
  }
}

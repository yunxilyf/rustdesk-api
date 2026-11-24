import { t } from './i18n'

const BASE = '/api/console'

export class ApiError extends Error {
  constructor(message, status) {
    super(message)
    this.status = status
  }
}

function cleanQuery(query) {
  const out = {}
  Object.keys(query || {}).forEach((k) => {
    const v = query[k]
    if (v !== '' && v !== null && v !== undefined && !(Array.isArray(v) && !v.length)) {
      out[k] = v
    }
  })
  return out
}

function csrfToken() {
  const match = document.cookie.match(/(?:^|;\s*)csrftoken=([^;]+)/)
  return match ? decodeURIComponent(match[1]) : ''
}

async function request(method, path, { query, body, silent401 } = {}) {
  const params = new URLSearchParams(cleanQuery(query)).toString()
  const url = BASE + path + (params ? `?${params}` : '')
  const init = { method, credentials: 'include', headers: {} }
  if (!['GET', 'HEAD', 'OPTIONS'].includes(method)) {
    const token = csrfToken()
    if (token) init.headers['X-CSRFToken'] = token
  }
  if (body !== undefined) {
    init.headers['Content-Type'] = 'application/json'
    init.body = JSON.stringify(body)
  }
  let res
  try {
    res = await fetch(url, init)
  } catch (e) {
    throw new ApiError(t('api.networkError'), 0)
  }
  if (res.status === 401) {
    if (!silent401) window.dispatchEvent(new CustomEvent('console:unauthorized'))
    throw new ApiError(t('api.unauthorized'), 401)
  }
  let data = {}
  try {
    data = await res.json()
  } catch (e) {
    data = {}
  }
  if (res.status === 403) {
    throw new ApiError(data.msg || t('api.forbidden'), 403)
  }
  if (!res.ok || data.ok === false) {
    throw new ApiError(data.msg || t('api.requestFailed', { status: res.status }), res.status)
  }
  return data
}

export const api = {
  get: (path, query) => request('GET', path, { query }),
  post: (path, body) => request('POST', path, { body }),
  put: (path, body) => request('PUT', path, { body }),
  del: (path, body) => request('DELETE', path, { body }),

  // auth
  setupStatus: () => request('GET', '/setup'),
  setup: (body) => request('POST', '/setup', { body }),
  register: (body) => request('POST', '/register', { body }),
  login: (username, password) => request('POST', '/login', { body: { username, password } }),
  loginOptions: () => request('GET', '/login-options'),
  logout: () => request('POST', '/logout'),
  me: () => request('GET', '/me', { silent401: true }),
  changePassword: (old, password) => request('PUT', '/me/password', { body: { old, password } }),
  updateProfile: (body) => request('PATCH', '/me', { body }),

  // stats
  stats: () => request('GET', '/stats'),

  // users
  users: (query) => request('GET', '/users', { query }),
  createUser: (body) => request('POST', '/users', { body }),
  updateUser: (id, body) => request('PUT', `/users/${id}`, { body }),
  deleteUser: (id) => request('DELETE', `/users/${id}`),

  // devices
  devices: (query) => request('GET', '/devices', { query }),
  setDeviceOwner: (rid, userId) =>
    userId
      ? request('PUT', `/devices/${encodeURIComponent(rid)}/owner`, { body: { user_id: userId } })
      : request('DELETE', `/devices/${encodeURIComponent(rid)}/owner`),

  // address books
  addressbooks: (query) => request('GET', '/addressbooks', { query }),
  createAddressbook: (body) => request('POST', '/addressbooks', { body }),
  updateAddressbook: (guid, body) => request('PUT', `/addressbooks/${guid}`, { body }),
  deleteAddressbook: (guid) => request('DELETE', `/addressbooks/${guid}`),
  abPeers: (guid, query) => request('GET', `/addressbooks/${guid}/peers`, { query }),
  addAbPeer: (guid, body) => request('POST', `/addressbooks/${guid}/peers`, { body }),
  updateAbPeer: (guid, rid, body) => request('PUT', `/addressbooks/${guid}/peers/${encodeURIComponent(rid)}`, { body }),
  deleteAbPeers: (guid, ids) => request('DELETE', `/addressbooks/${guid}/peers`, { body: { ids } }),
  abTags: (guid) => request('GET', `/addressbooks/${guid}/tags`),
  addAbTag: (guid, body) => request('POST', `/addressbooks/${guid}/tags`, { body }),
  updateAbTag: (guid, name, body) => request('PUT', `/addressbooks/${guid}/tags/${encodeURIComponent(name)}`, { body }),
  deleteAbTags: (guid, names) => request('DELETE', `/addressbooks/${guid}/tags`, { body: { names } }),

  // groups
  groups: (query) => request('GET', '/groups', { query }),
  createGroup: (body) => request('POST', '/groups', { body }),
  updateGroup: (guid, body) => request('PUT', `/groups/${guid}`, { body }),
  deleteGroup: (guid) => request('DELETE', `/groups/${guid}`),
  groupMembers: (guid) => request('GET', `/groups/${guid}/members`),
  addGroupMembers: (guid, rids) => request('POST', `/groups/${guid}/members`, { body: { rids } }),
  removeGroupMembers: (guid, rids) => request('DELETE', `/groups/${guid}/members`, { body: { rids } }),

  // logs
  connLogs: (query) => request('GET', '/logs/conn', { query }),
  fileLogs: (query) => request('GET', '/logs/file', { query }),

  // settings
  getVersion: () => request('GET', '/version'),
  getSettings: () => request('GET', '/settings'),
  updateSettings: (body) => request('PUT', '/settings', { body }),
}

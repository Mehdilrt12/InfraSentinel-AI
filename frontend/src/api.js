import axios from 'axios'

// Same-origin is the safe release default. Local development may still override
// it explicitly through frontend/.env without baking a loopback URL into a build.
export const resolveApiUrl = (configuredUrl) => (configuredUrl || '/api').replace(/\/$/, '')
export const API_URL = resolveApiUrl(import.meta.env.VITE_API_URL)

let accessToken = null
let csrfToken = null
let refreshPromise = null

export const api = axios.create({
  baseURL: API_URL,
  timeout: 15000,
  withCredentials: true,
  headers: { Accept: 'application/json' },
})

const browserAuth = axios.create({
  baseURL: API_URL,
  timeout: 15000,
  withCredentials: true,
  headers: { Accept: 'application/json' },
})

export function setAccessToken(token) { accessToken = token || null }
export function hasAccessToken() { return Boolean(accessToken) }

export async function ensureCsrfToken() {
  if (csrfToken) return csrfToken
  const { data } = await browserAuth.get('/auth/browser/csrf/')
  csrfToken = data.csrf_token
  return csrfToken
}

function csrfHeaders(token) { return { 'X-CSRFToken': token } }

export async function loginBrowser(email, password) {
  const csrf = await ensureCsrfToken()
  const { data } = await browserAuth.post(
    '/auth/browser/login/',
    { email, password },
    { headers: csrfHeaders(csrf) },
  )
  setAccessToken(data.access)
  return data
}

export async function refreshBrowserSession() {
  refreshPromise ||= ensureCsrfToken()
    .then((csrf) => browserAuth.post('/auth/browser/refresh/', {}, { headers: csrfHeaders(csrf) }))
    .then(({ data }) => { setAccessToken(data.access); return data.access })
    .catch((error) => { setAccessToken(null); throw error })
    .finally(() => { refreshPromise = null })
  return refreshPromise
}

export async function logoutBrowser() {
  try {
    const csrf = await ensureCsrfToken()
    await browserAuth.post('/auth/browser/logout/', {}, { headers: csrfHeaders(csrf) })
  } finally {
    setAccessToken(null)
  }
}

api.interceptors.request.use((config) => {
  if (accessToken) config.headers.Authorization = `Bearer ${accessToken}`
  return config
})

api.interceptors.response.use((response) => response, async (error) => {
  const original = error.config
  if (error.response?.status !== 401 || original?._retried) return Promise.reject(error)
  original._retried = true
  const token = await refreshBrowserSession()
  original.headers.Authorization = `Bearer ${token}`
  return api(original)
})

export const listData = (data) => Array.isArray(data) ? data : (data?.results || [])

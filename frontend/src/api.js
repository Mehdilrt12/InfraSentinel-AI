import axios from 'axios'

export const API_URL = (import.meta.env.VITE_API_URL || 'http://127.0.0.1:8000/api').replace(/\/$/, '')
export const api = axios.create({ baseURL: API_URL, timeout: 15000, headers: { Accept: 'application/json' } })

api.interceptors.request.use((config) => {
  const token = localStorage.getItem('access_token')
  if (token) config.headers.Authorization = `Bearer ${token}`
  return config
})

let refreshPromise
api.interceptors.response.use((response) => response, async (error) => {
  const original = error.config
  if (error.response?.status !== 401 || original?._retried || !localStorage.getItem('refresh_token')) return Promise.reject(error)
  original._retried = true
  refreshPromise ||= axios.post(`${API_URL}/auth/refresh/`, { refresh: localStorage.getItem('refresh_token') })
    .then(({ data }) => { localStorage.setItem('access_token', data.access); if (data.refresh) localStorage.setItem('refresh_token', data.refresh); return data.access })
    .finally(() => { refreshPromise = null })
  const token = await refreshPromise
  original.headers.Authorization = `Bearer ${token}`
  return api(original)
})

export const listData = (data) => Array.isArray(data) ? data : (data?.results || [])


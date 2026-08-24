import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(Boolean(localStorage.getItem('access_token')))
  useEffect(() => {
    if (!localStorage.getItem('access_token')) return setLoading(false)
    api.get('/auth/me/').then(({ data }) => setUser(data)).catch(() => { localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token') }).finally(() => setLoading(false))
  }, [])
  const value = useMemo(() => ({ user, loading, async login(email, password) { const { data } = await api.post('/auth/token/', { email, password }); localStorage.setItem('access_token', data.access); localStorage.setItem('refresh_token', data.refresh); const me = await api.get('/auth/me/'); setUser(me.data) }, async logout() { const refresh = localStorage.getItem('refresh_token'); try { if (refresh) await api.post('/auth/logout/', { refresh }) } finally { localStorage.removeItem('access_token'); localStorage.removeItem('refresh_token'); setUser(null) } } }), [user, loading])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() { return useContext(AuthContext) }

export function Protected({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="center-state"><span className="spinner" />Chargement de la session…</div>
  return user ? children : <Navigate to="/login" replace state={{ from: location }} />
}

import { createContext, useContext, useEffect, useMemo, useState } from 'react'
import { Navigate, useLocation } from 'react-router-dom'
import { api, loginBrowser, logoutBrowser, refreshBrowserSession, setAccessToken } from './api'

const AuthContext = createContext(null)

export function AuthProvider({ children }) {
  const [user, setUser] = useState(null)
  const [loading, setLoading] = useState(true)
  useEffect(() => {
    refreshBrowserSession()
      .then(() => api.get('/auth/me/'))
      .then(({ data }) => setUser(data))
      .catch(() => { setAccessToken(null); setUser(null) })
      .finally(() => setLoading(false))
  }, [])
  const value = useMemo(() => ({
    user,
    loading,
    async login(email, password) {
      await loginBrowser(email, password)
      const me = await api.get('/auth/me/')
      setUser(me.data)
    },
    async logout() {
      try { await logoutBrowser() } finally { setUser(null) }
    },
  }), [user, loading])
  return <AuthContext.Provider value={value}>{children}</AuthContext.Provider>
}

export function useAuth() { return useContext(AuthContext) }

export const isManager = (user) => Boolean(user?.is_superuser || ['ADMIN', 'SUPERVISOR'].includes(user?.role))
export const isAdministrator = (user) => Boolean(user?.is_superuser || user?.role === 'ADMIN')

export function Protected({ children }) {
  const { user, loading } = useAuth()
  const location = useLocation()
  if (loading) return <div className="center-state"><span className="spinner" />Chargement de la session…</div>
  return user ? children : <Navigate to="/login" replace state={{ from: location }} />
}

export function RoleProtected({ children, administrator = false }) {
  const { user, loading } = useAuth()
  if (loading) return <div className="center-state"><span className="spinner" />Chargement des autorisations…</div>
  const allowed = administrator ? isAdministrator(user) : isManager(user)
  return allowed ? children : <Navigate to="/dashboard" replace />
}

import { Activity, ArrowRight, Eye, EyeOff, LockKeyhole, Mail, ShieldCheck } from 'lucide-react'
import { useState } from 'react'
import { Link, Navigate, useNavigate } from 'react-router-dom'
import { api } from '../api'
import { useAuth } from '../auth'
import { apiErrorMessage } from '../hooks'

const publicRegistrationEnabled = import.meta.env.VITE_PUBLIC_REGISTRATION_ENABLED === 'true'

export function Login() {
  const { user, login } = useAuth()
  const [form, setForm] = useState({ email: '', password: '' })
  const [visible, setVisible] = useState(false)
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  if (user) return <Navigate to="/dashboard" replace />
  async function submit(event) {
    event.preventDefault(); setLoading(true); setError('')
    try {
      await login(form.email, form.password)
    } catch (reason) {
      const status = reason.response?.status
      if (status === 401) setError('Email ou mot de passe incorrect.')
      else if (status === 403) setError('Ce compte ne dispose pas de l’autorisation nécessaire.')
      else if (status === 429) setError('Trop de tentatives. Patientez avant de réessayer.')
      else setError(apiErrorMessage(reason, 'Connexion impossible.'))
    } finally { setLoading(false) }
  }
  return <AuthShell><form className="auth-form" onSubmit={submit} aria-busy={loading}><p className="eyebrow">ACCÈS SÉCURISÉ</p><h1>Connexion</h1><p>Accédez au centre de supervision unifié.</p>{error && <div className="auth-error" role="alert"><ShieldCheck /><span><strong>Connexion refusée</strong>{error}</span></div>}<label>Email<div className="input"><Mail /><input type="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} autoComplete="email" /></div></label><label>Mot de passe<div className="input"><LockKeyhole /><input type={visible ? 'text' : 'password'} required value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} autoComplete="current-password" /><button type="button" aria-label={visible ? 'Masquer le mot de passe' : 'Afficher le mot de passe'} onClick={() => setVisible(!visible)}>{visible ? <EyeOff /> : <Eye />}</button></div></label><button className="primary" disabled={loading}>{loading ? 'Connexion…' : <>Se connecter<ArrowRight /></>}</button><span className="sr-only" aria-live="polite">{loading ? 'Connexion en cours' : ''}</span>{publicRegistrationEnabled && <p className="auth-link">Pas encore de compte ? <Link to="/register">Créer un espace client</Link></p>}</form></AuthShell>
}

export function Register() {
  const navigate = useNavigate()
  const [form, setForm] = useState({ organization: '', email: '', password: '' })
  const [error, setError] = useState('')
  const [loading, setLoading] = useState(false)
  if (!publicRegistrationEnabled) return <Navigate to="/login" replace />
  async function submit(event) {
    event.preventDefault(); setError(''); setLoading(true)
    try { await api.post('/auth/register/', form); navigate('/login') }
    catch (reason) { setError(apiErrorMessage(reason, 'Inscription impossible.')) }
    finally { setLoading(false) }
  }
  return <AuthShell><form className="auth-form" onSubmit={submit} aria-busy={loading}><p className="eyebrow">NOUVEL ESPACE</p><h1>Créer un compte</h1><p>Initialisez un tenant isolé pour votre infrastructure.</p>{error && <div className="auth-error" role="alert">{error}</div>}<label>Organisation<div className="input"><Activity /><input required value={form.organization} onChange={(event) => setForm({ ...form, organization: event.target.value })} autoComplete="organization" /></div></label><label>Email<div className="input"><Mail /><input type="email" required value={form.email} onChange={(event) => setForm({ ...form, email: event.target.value })} autoComplete="email" /></div></label><label>Mot de passe (10 caractères minimum)<div className="input"><LockKeyhole /><input type="password" required minLength="10" value={form.password} onChange={(event) => setForm({ ...form, password: event.target.value })} autoComplete="new-password" /></div></label><button className="primary" disabled={loading}>{loading ? 'Création…' : <>Créer l’espace<ArrowRight /></>}</button><p className="auth-link"><Link to="/login">Retour à la connexion</Link></p></form></AuthShell>
}

function AuthShell({ children }) { return <main className="auth-page"><section className="auth-visual"><div className="visual-grid" /><div className="visual-copy"><span className="hero-icon"><Activity /></span><p className="eyebrow">PLATEFORME IA / ML</p><h2>InfraSentinel AI</h2><p>Windows, VMware et Hyper-V réunis dans un même centre opérationnel.</p><div className="visual-points"><span>Détection proactive</span><span>Temps réel</span><span>Multi-tenant</span></div></div></section><section className="auth-panel">{children}</section></main> }

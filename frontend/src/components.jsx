import {
  Activity,
  AlertTriangle,
  Bell,
  Bot,
  Boxes,
  BrainCircuit,
  Cable,
  ChevronRight,
  CircleGauge,
  CloudCog,
  LogOut,
  Menu,
  Monitor,
  RefreshCw,
  Server,
  Settings,
  ShieldCheck,
  Users,
  X,
} from 'lucide-react'
import { useEffect, useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { isAdministrator, isManager, useAuth } from './auth'
import {
  formatMetricReading,
  formatRawValue,
  formatReadableNumber,
  formatRelativeTime,
  formatTimestamp,
  roleLabel,
  severityLabel,
  statusLabel,
} from './metricFormatting'
import { useRealtime } from './realtime'

const navigation = [
  ['/dashboard', CircleGauge, 'Vue globale'],
  ['/machines', Monitor, 'Machines'],
  ['/agents', Bot, 'Agents'],
  ['/alerts', Bell, 'Alertes'],
  ['/anomalies', Activity, 'Anomalies'],
  ['/vmware', CloudCog, 'VMware'],
  ['/hyperv', Boxes, 'Hyper-V'],
  ['/ml', BrainCircuit, 'Machine Learning'],
  ['/users', Users, 'Utilisateurs'],
  ['/settings', Settings, 'Configuration'],
  ['/audit', ShieldCheck, 'Audit'],
]

const realtimeLabels = {
  live: 'Temps réel actif',
  polling: 'Polling de secours',
  connecting: 'Reconnexion…',
  offline: 'Temps réel indisponible',
}

export function Layout() {
  const [open, setOpen] = useState(false)
  const { user, logout } = useAuth()
  const realtime = useRealtime()
  const visibleNavigation = navigation.filter(([path]) => {
    if (path === '/users') return isAdministrator(user)
    if (path === '/settings' || path === '/audit') return isManager(user)
    return true
  })

  useEffect(() => {
    if (!open) return undefined
    const closeOnEscape = (event) => { if (event.key === 'Escape') setOpen(false) }
    document.addEventListener('keydown', closeOnEscape)
    document.body.classList.add('navigation-open')
    return () => {
      document.removeEventListener('keydown', closeOnEscape)
      document.body.classList.remove('navigation-open')
    }
  }, [open])

  return <div className="shell">
    {open && <button className="sidebar-backdrop" aria-label="Fermer le menu" onClick={() => setOpen(false)} />}
    <aside className={`sidebar ${open ? 'open' : ''}`} aria-label="Navigation principale">
      <div className="brand">
        <span className="brand-mark"><Activity aria-hidden="true" /></span>
        <span>InfraSentinel <small>AI</small></span>
        <button className="mobile-close" aria-label="Fermer le menu" onClick={() => setOpen(false)}><X /></button>
      </div>
      <nav>{visibleNavigation.map(([path, Icon, label]) => <NavLink key={path} to={path} onClick={() => setOpen(false)} className={({ isActive }) => isActive ? 'active' : ''}>
        <Icon aria-hidden="true" />
        <span>{label}</span>
        <ChevronRight className="chevron" aria-hidden="true" />
      </NavLink>)}</nav>
      <div className="sidebar-foot">
        <div className="avatar" aria-hidden="true">{user?.email?.[0]?.toUpperCase()}</div>
        <div><strong>{user?.first_name || user?.username}</strong><small>{roleLabel(user?.role)}</small></div>
        <button aria-label="Se déconnecter" title="Se déconnecter" onClick={logout}><LogOut /></button>
      </div>
    </aside>
    <main className="main">
      <header className="topbar">
        <button className="menu" aria-label="Ouvrir le menu" aria-expanded={open} onClick={() => setOpen(true)}><Menu /></button>
        <div className={`live ${realtime.status}`} role="status" aria-live="polite"><span aria-hidden="true" />{realtimeLabels[realtime.status] || realtimeLabels.offline}</div>
        <div className="tenant"><Server aria-hidden="true" />{user?.customer ? 'Espace client' : 'Administration globale'}</div>
      </header>
      <Outlet />
    </main>
  </div>
}

export function Page({ title, description, actions, children }) {
  return <section className="page">
    <div className="page-head">
      <div><p className="eyebrow">INFRASTRUCTURE INTELLIGENCE</p><h1>{title}</h1><p>{description}</p></div>
      {actions && <div className="actions">{actions}</div>}
    </div>
    {children}
  </section>
}

export function LoadingState({ label = 'Chargement des données…', rows = 3 }) {
  return <div className="state-card loading-state" role="status" aria-live="polite">
    <span className="spinner" aria-hidden="true" />
    <span>{label}</span>
    <div className="skeleton-stack" aria-hidden="true">{Array.from({ length: rows }, (_, index) => <i key={index} />)}</div>
  </div>
}

export function EmptyState({ title = 'Aucune donnée', message = 'Aucune donnée disponible.', icon: Icon = Cable, action }) {
  return <div className="state-card empty">
    <Icon aria-hidden="true" />
    <div><strong>{title}</strong><p>{message}</p>{action && <div className="state-action">{action}</div>}</div>
  </div>
}

export function ErrorState({ message, retry }) {
  return <div className="state-card error" role="alert">
    <AlertTriangle aria-hidden="true" />
    <div><strong>Données indisponibles</strong><p>{message}</p>{retry && <button onClick={retry}><RefreshCw />Réessayer</button>}</div>
  </div>
}

export function DataState({ state, children, empty = 'Aucune donnée disponible.', emptyTitle = 'Aucune donnée', retry }) {
  if (state.loading && (state.data == null || (Array.isArray(state.data) && !state.data.length))) return <LoadingState />
  if (state.error && (state.data == null || (Array.isArray(state.data) && !state.data.length))) return <ErrorState message={state.error} retry={retry || state.refresh} />
  const emptyData = Array.isArray(state.data) && !state.data.length
  if (emptyData) return <EmptyState title={emptyTitle} message={empty} />
  return <>
    {state.error && <div className="partial"><AlertTriangle aria-hidden="true" />Les données affichées peuvent être anciennes. {state.error}{(retry || state.refresh) && <button onClick={retry || state.refresh}>Réessayer</button>}</div>}
    {state.partial && <div className="partial"><AlertTriangle aria-hidden="true" />Certaines sources ont fourni des données partielles.</div>}
    {children}
  </>
}

function classKey(value, fallback) {
  return String(value || fallback).toLowerCase().replace(/[\s_]/g, '')
}

export function Severity({ value }) {
  const raw = String(value || 'INFO').toUpperCase()
  return <span className={`badge ${classKey(raw, 'info')}`}><span className="badge-symbol" aria-hidden="true" />{severityLabel(raw)}</span>
}

export function Status({ value, label }) {
  const raw = String(value || 'UNKNOWN')
  return <span className={`status ${classKey(raw, 'unknown')}`}><i aria-hidden="true" />{label || statusLabel(raw)}</span>
}

export function Timestamp({ value, relative = true, compact = false }) {
  if (!value) return <span className="timestamp muted">Jamais</span>
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return <span className="timestamp muted">Date invalide</span>
  const exact = formatTimestamp(value)
  return <time className="timestamp" dateTime={date.toISOString()} title={relative ? exact : undefined}>{relative ? formatRelativeTime(value) : exact}{!compact && relative && <span className="sr-only"> ({exact})</span>}</time>
}

export function MetricValue({ metric, value, unit, label, detail, className = '' }) {
  const reading = metric ? formatMetricReading(metric) : { label, ...formatRawValue(value, unit), detail }
  return <div className={`metric-value ${className}`.trim()}>
    {reading.label && <span>{reading.label}</span>}
    <strong>{reading.text}</strong>
    {(reading.detail || detail) && <small>{reading.detail || detail}</small>}
  </div>
}

export function MetricCard({ metric, icon: Icon, tone = 'cyan' }) {
  const reading = formatMetricReading(metric)
  return <article className={`metric-card ${tone}`}>
    {Icon && <span className="metric-card-icon"><Icon aria-hidden="true" /></span>}
    <div><span>{reading.label}</span><strong>{reading.text}</strong>{reading.detail && <small>{reading.detail}</small>}</div>
    {metric?.timestamp && <Timestamp value={metric.timestamp} compact />}
  </article>
}

export function ActionFeedback({ feedback, onDismiss }) {
  if (!feedback?.message) return null
  return <div className={`action-feedback ${feedback.type || 'info'}`} role={feedback.type === 'error' ? 'alert' : 'status'} aria-live="polite">
    <span>{feedback.message}</span>
    {onDismiss && <button aria-label="Fermer le message" onClick={onDismiss}><X /></button>}
  </div>
}

export function Table({ columns, rows = [], rowKey = 'id', onRow, label = 'Données' }) {
  return <div className="table-wrap" role="region" aria-label={label} tabIndex="0">
    <table>
      <thead><tr>{columns.map((column) => <th scope="col" key={column.key}>{column.label}</th>)}</tr></thead>
      <tbody>{rows.map((row, rowIndex) => {
        const key = row[rowKey] ?? rowIndex
        const activate = () => onRow?.(row)
        return <tr
          key={key}
          onClick={onRow ? activate : undefined}
          onKeyDown={onRow ? (event) => { if (event.key === 'Enter' || event.key === ' ') { event.preventDefault(); activate() } } : undefined}
          className={onRow ? 'clickable' : ''}
          tabIndex={onRow ? 0 : undefined}
          aria-label={onRow ? `Ouvrir ${row.hostname || row.name || key}` : undefined}
        >{columns.map((column) => <td data-label={column.label} key={column.key}>{column.render ? column.render(row[column.key], row) : String(row[column.key] ?? '—')}</td>)}</tr>
      })}</tbody>
    </table>
  </div>
}

export const formatNumber = (value, digits = 0) => formatReadableNumber(value, digits)

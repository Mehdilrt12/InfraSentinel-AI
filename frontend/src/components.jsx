import { Activity, AlertTriangle, Bell, Bot, Boxes, BrainCircuit, Cable, ChevronRight, CircleGauge, CloudCog, Cpu, LogOut, Menu, Monitor, Server, Settings, ShieldCheck, Users, X } from 'lucide-react'
import { useState } from 'react'
import { NavLink, Outlet } from 'react-router-dom'
import { useAuth } from './auth'
import { useRealtime } from './realtime'

const navigation = [
  ['/dashboard', CircleGauge, 'Vue globale'], ['/machines', Monitor, 'Machines'], ['/agents', Bot, 'Agents'],
  ['/alerts', Bell, 'Alertes'], ['/anomalies', Activity, 'Anomalies'], ['/vmware', CloudCog, 'VMware'],
  ['/hyperv', Boxes, 'Hyper-V'], ['/ml', BrainCircuit, 'Machine Learning'], ['/users', Users, 'Utilisateurs'],
  ['/settings', Settings, 'Configuration'], ['/audit', ShieldCheck, 'Audit'],
]

export function Layout() {
  const [open, setOpen] = useState(false)
  const { user, logout } = useAuth()
  const realtime = useRealtime()
  return <div className="shell">
    <aside className={`sidebar ${open ? 'open' : ''}`}>
      <div className="brand"><span className="brand-mark"><Activity /></span><span>InfraSentinel <small>AI</small></span><button className="mobile-close" onClick={() => setOpen(false)}><X /></button></div>
      <nav>{navigation.map(([path, Icon, label]) => <NavLink key={path} to={path} onClick={() => setOpen(false)} className={({ isActive }) => isActive ? 'active' : ''}><Icon />{label}<ChevronRight className="chevron" /></NavLink>)}</nav>
      <div className="sidebar-foot"><div className="avatar">{user?.email?.[0]?.toUpperCase()}</div><div><strong>{user?.first_name || user?.username}</strong><small>{user?.role}</small></div><button title="Se déconnecter" onClick={logout}><LogOut /></button></div>
    </aside>
    <main className="main"><header className="topbar"><button className="menu" onClick={() => setOpen(true)}><Menu /></button><div className={`live ${realtime.status}`}><span />{realtime.status === 'live' ? 'Temps réel' : realtime.status === 'polling' ? 'Polling de secours' : realtime.status === 'connecting' ? 'Connexion…' : 'Hors ligne'}</div><div className="tenant"><Server />{user?.customer ? 'Espace client' : 'Administration globale'}</div></header><Outlet /></main>
  </div>
}

export function Page({ title, description, actions, children }) { return <section className="page"><div className="page-head"><div><p className="eyebrow">INFRASTRUCTURE INTELLIGENCE</p><h1>{title}</h1><p>{description}</p></div>{actions && <div className="actions">{actions}</div>}</div>{children}</section> }

export function DataState({ state, children, empty = 'Aucune donnée disponible.' }) {
  if (state.loading) return <div className="state-card"><span className="spinner" />Chargement des données…</div>
  if (state.error) return <div className="state-card error"><AlertTriangle /><div><strong>Données indisponibles</strong><p>{state.error}</p></div></div>
  const emptyData = Array.isArray(state.data) && !state.data.length
  if (emptyData) return <div className="state-card empty"><Cable /><div><strong>Aucune donnée</strong><p>{empty}</p></div></div>
  return <>{state.partial && <div className="partial"><AlertTriangle />Certaines sources ont fourni des données partielles.</div>}{children}</>
}

export function Severity({ value }) { return <span className={`badge ${String(value || 'info').toLowerCase()}`}>{value || 'INFO'}</span> }
export function Status({ value }) { return <span className={`status ${String(value || 'unknown').toLowerCase()}`}><i />{value || 'UNKNOWN'}</span> }

export function Table({ columns, rows, rowKey = 'id', onRow }) {
  return <div className="table-wrap"><table><thead><tr>{columns.map((column) => <th key={column.key}>{column.label}</th>)}</tr></thead><tbody>{rows.map((row) => <tr key={row[rowKey]} onClick={() => onRow?.(row)} className={onRow ? 'clickable' : ''}>{columns.map((column) => <td key={column.key}>{column.render ? column.render(row[column.key], row) : String(row[column.key] ?? '—')}</td>)}</tr>)}</tbody></table></div>
}

export const formatNumber = (value, digits = 0) => value == null ? '—' : new Intl.NumberFormat('fr-FR', { maximumFractionDigits: digits }).format(value)


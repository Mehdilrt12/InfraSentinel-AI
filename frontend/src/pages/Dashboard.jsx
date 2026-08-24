import { Activity, AlertOctagon, BellRing, Boxes, CloudCog, MonitorCheck, MonitorX, Server } from 'lucide-react'
import { Area, AreaChart, CartesianGrid, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { DataState, formatNumber, Page } from '../components'
import { useApi } from '../hooks'

const cards = [
  ['total_assets', 'Assets supervisés', Server, 'cyan'], ['online', 'En ligne', MonitorCheck, 'green'], ['offline', 'Hors ligne', MonitorX, 'red'],
  ['critical', 'Critiques', AlertOctagon, 'red'], ['warning', 'Warnings', BellRing, 'amber'], ['anomalies', 'Anomalies', Activity, 'violet'],
  ['vmware_hosts', 'Hôtes VMware', CloudCog, 'blue'], ['hyperv_hosts', 'Hôtes Hyper-V', Boxes, 'cyan'],
]

export default function Dashboard() {
  const stats = useApi('/dashboard/')
  const metrics = useApi('/metrics/?page_size=100', { list: true })
  const chart = (metrics.data || []).slice(0, 40).reverse().map((item) => ({ time: new Date(item.timestamp).toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit' }), value: item.metric_value, metric: item.metric_name }))
  return <Page title="Vue globale" description="État consolidé de toutes les sources supervisées."><DataState state={stats}>{stats.data && <><div className="stat-grid">{cards.map(([key, label, Icon, tone]) => <article className={`stat-card ${tone}`} key={key}><span><Icon /></span><div><strong>{formatNumber(stats.data[key])}</strong><p>{label}</p></div></article>)}</div><div className="dashboard-grid"><article className="panel wide"><div className="panel-head"><div><h2>Activité récente</h2><p>Dernières mesures normalisées reçues</p></div><span className="badge info">LIVE</span></div><div className="chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={chart}><defs><linearGradient id="metricFill" x1="0" y1="0" x2="0" y2="1"><stop offset="0%" stopColor="#24dbc1" stopOpacity={0.45}/><stop offset="100%" stopColor="#24dbc1" stopOpacity={0}/></linearGradient></defs><CartesianGrid strokeDasharray="3 3" stroke="#183238"/><XAxis dataKey="time" stroke="#77959b"/><YAxis stroke="#77959b"/><Tooltip contentStyle={{ background: '#0c1d22', border: '1px solid #214149' }}/><Area type="monotone" dataKey="value" stroke="#24dbc1" fill="url(#metricFill)" /></AreaChart></ResponsiveContainer></div></article><article className="panel"><div className="panel-head"><div><h2>Priorité opérationnelle</h2><p>Alertes actives</p></div></div><div className="priority"><strong>{stats.data.active_alerts}</strong><span>alertes à traiter</span><div className="risk-bar"><i style={{ width: `${Math.min(100, stats.data.active_alerts * 8)}%` }} /></div><p>{stats.data.critical ? `${stats.data.critical} critique(s) nécessitent une action.` : 'Aucune alerte critique active.'}</p></div></article></div></>}</DataState></Page>
}


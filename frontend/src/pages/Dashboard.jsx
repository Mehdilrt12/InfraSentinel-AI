import { Activity, AlertOctagon, BellRing, Boxes, CloudCog, MonitorCheck, MonitorX, Server } from 'lucide-react'
import { DataState, Page, Timestamp } from '../components'
import { useApi } from '../hooks'
import { formatCount, formatMetricReading, sourceLabel } from '../metricFormatting'
import { useRealtime } from '../realtime'

const cards = [
  ['total_assets', 'Assets supervisés', Server, 'cyan'],
  ['online', 'En ligne', MonitorCheck, 'green'],
  ['offline', 'Hors ligne', MonitorX, 'red'],
  ['critical', 'Alertes critiques', AlertOctagon, 'red'],
  ['warning', 'Avertissements', BellRing, 'amber'],
  ['anomalies', 'Anomalies', Activity, 'violet'],
  ['vmware_hosts', 'Hôtes VMware', CloudCog, 'blue'],
  ['hyperv_hosts', 'Hôtes Hyper-V', Boxes, 'cyan'],
]

const realtimeLabels = {
  live: ['LIVE', 'normal'],
  connecting: ['RECONNEXION', 'warning'],
  polling: ['POLLING', 'warning'],
  offline: ['INDISPONIBLE', 'critical'],
}

export default function Dashboard() {
  const stats = useApi('/dashboard/')
  const metrics = useApi('/metrics/', { list: true })
  const realtime = useRealtime()
  const recentMetrics = (metrics.data || []).slice(0, 12)
  const [realtimeText, realtimeTone] = realtimeLabels[realtime.status] || realtimeLabels.offline

  return <Page title="Vue globale" description="État consolidé de toutes les sources supervisées.">
    <DataState state={stats} retry={stats.refresh}>{stats.data && <>
      <div className="stat-grid">{cards.map(([key, label, Icon, tone]) => <article className={`stat-card ${tone}`} key={key}>
        <span><Icon aria-hidden="true" /></span>
        <div><strong>{formatCount(stats.data[key])}</strong><p>{label}</p></div>
      </article>)}</div>
      <div className="dashboard-grid">
        <article className="panel wide">
          <div className="panel-head"><div><h2>Activité récente</h2><p>Dernières mesures normalisées reçues, sans mélanger des unités incompatibles.</p></div><span className={`badge ${realtimeTone}`}>{realtimeText}</span></div>
          <DataState state={metrics} retry={metrics.refresh} empty="Aucune mesure n’a encore été reçue.">
            <div className="activity-list">{recentMetrics.map((metric) => {
              const reading = formatMetricReading(metric)
              return <article className="activity-row" key={metric.id || `${metric.timestamp}-${metric.metric_name}`}>
                <span className="activity-dot" aria-hidden="true" />
                <div><strong>{reading.label}</strong><small>{sourceLabel(metric.source_type)}</small></div>
                <b>{reading.text}</b>
                <Timestamp value={metric.timestamp} compact />
              </article>
            })}</div>
          </DataState>
        </article>
        <article className="panel">
          <div className="panel-head"><div><h2>Priorité opérationnelle</h2><p>Alertes actives nécessitant un suivi.</p></div></div>
          <div className="priority">
            <strong>{formatCount(stats.data.active_alerts)}</strong>
            <span>alertes à traiter</span>
            <div className="risk-bar" role="progressbar" aria-label="Charge des alertes actives" aria-valuemin="0" aria-valuemax="100" aria-valuenow={Math.min(100, stats.data.active_alerts * 8)}><i style={{ width: `${Math.min(100, stats.data.active_alerts * 8)}%` }} /></div>
            <p>{stats.data.critical ? `${formatCount(stats.data.critical)} alerte(s) critique(s) nécessitent une action.` : 'Aucune alerte critique active.'}</p>
          </div>
        </article>
      </div>
    </>}</DataState>
  </Page>
}

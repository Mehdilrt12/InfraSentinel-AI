import {
  Activity,
  Bell,
  Bot,
  Boxes,
  BrainCircuit,
  Check,
  CloudCog,
  Copy,
  Cpu,
  Database,
  Download,
  Gauge,
  HardDrive,
  MemoryStick,
  Network,
  Plus,
  Power,
  RefreshCw,
  Save,
  Search,
  Server,
  ShieldAlert,
  Timer,
} from 'lucide-react'
import { useMemo, useState } from 'react'
import { useNavigate, useParams } from 'react-router-dom'
import { Area, AreaChart, CartesianGrid, Legend, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { api } from '../api'
import { isManager, useAuth } from '../auth'
import {
  ActionFeedback,
  DataState,
  EmptyState,
  MetricCard,
  Page,
  Severity,
  Status,
  Table,
  Timestamp,
} from '../components'
import { useActionFeedback, useApi } from '../hooks'
import {
  findModelByTechnicalVersion,
  getAlgorithmDisplayName,
  getModelDisplayName,
  orderModelHistory,
} from '../mlModelPresentation'
import {
  METRIC_LABELS,
  buildMetricChartGroups,
  formatAnomalySignal,
  formatBytes,
  formatCount,
  formatDuration,
  formatMetricChangePerHour,
  formatMetricReading,
  formatPercent,
  formatRawValue,
  formatReadableNumber,
  formatRiskLevel,
  formatTimestamp,
  formatTrend,
  latestMetrics,
  metricDefaultUnit,
  metricLabel,
  roleLabel,
  sourceLabel,
  statusLabel,
} from '../metricFormatting'

const METRIC_COLORS = ['#24dbc1', '#77db64', '#54a9ff', '#ffb84d', '#ab7cff', '#ff627d', '#36d7e8', '#f18fcd']

function osLabel(info = {}) {
  if (typeof info === 'string') return info || 'Non renseigné'
  return info.pretty_name || info.caption || info.name || info.system || [info.platform, info.release].filter(Boolean).join(' ') || 'Non renseigné'
}

function kindLabel(value) {
  return { HOST: 'Hôte', VM: 'Machine virtuelle', DATASTORE: 'Datastore' }[value] || value || '—'
}

function metricIcon(name) {
  if (name?.includes('cpu')) return Cpu
  if (name?.includes('memory')) return MemoryStick
  if (name?.includes('disk')) return HardDrive
  if (name?.includes('network')) return Network
  if (name?.includes('uptime')) return Timer
  return Gauge
}

function badge(label, tone = 'info') {
  return <span className={`badge ${tone}`}>{label}</span>
}

export function Machines() {
  const state = useApi('/machines/', { list: true })
  const navigate = useNavigate()
  const [query, setQuery] = useState('')
  const normalizedQuery = query.trim().toLowerCase()
  const rows = useMemo(() => (state.data || []).filter((machine) => {
    if (!normalizedQuery) return true
    return [machine.hostname, machine.ip_address, machine.source_type, osLabel(machine.os_information)]
      .some((value) => String(value || '').toLowerCase().includes(normalizedQuery))
  }), [normalizedQuery, state.data])
  const actions = <label className="search-control"><Search aria-hidden="true" /><span className="sr-only">Rechercher une machine</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Rechercher une machine…" /></label>
  const columns = [
    { key: 'hostname', label: 'Machine', render: (value, row) => <div className="primary-cell"><strong>{value}</strong><small>{osLabel(row.os_information)}</small></div> },
    { key: 'source_type', label: 'Source', render: (value) => <span className="chip">{sourceLabel(value)}</span> },
    { key: 'ip_address', label: 'Adresse IP' },
    { key: 'status', label: 'État', render: (value) => <Status value={value} /> },
    { key: 'agent_version', label: 'Agent', render: (value) => value || 'Non applicable' },
    { key: 'last_seen', label: 'Dernier contact', render: (value) => <Timestamp value={value} compact /> },
  ]
  return <Page title="Machines" description="Inventaire centralisé Windows, VMware et Hyper-V." actions={actions}>
    <DataState state={state} retry={state.refresh} emptyTitle="Aucune machine" empty="Aucune machine n’est encore enrôlée.">
      {rows.length ? <Table label="Inventaire des machines" columns={columns} rows={rows} onRow={(row) => navigate(`/machines/${row.id}`)} /> : <EmptyState title="Aucun résultat" message="Aucune machine ne correspond à votre recherche." />}
    </DataState>
  </Page>
}

function MetricHistoryChart({ group }) {
  const tickFormatter = group.key === 'state' ? (value) => value >= 0.5 ? 'Actif' : 'Arrêté' : formatReadableNumber
  return <article className="metric-chart-card" role="img" aria-label={`${group.title}, unité ${group.unit || 'sans unité'}`}>
    <div className="metric-chart-head"><h3>{group.title}</h3><span>{group.unit || (group.key === 'state' ? 'État' : 'Valeur')}</span></div>
    <div className="chart metric-chart"><ResponsiveContainer width="100%" height="100%"><AreaChart data={group.data} margin={{ top: 8, right: 16, left: 4, bottom: 4 }}>
      <CartesianGrid strokeDasharray="3 3" stroke="#183238" />
      <XAxis dataKey="time" stroke="#77959b" minTickGap={28} />
      <YAxis stroke="#77959b" width={64} tickFormatter={tickFormatter} domain={group.key === 'percent' ? [0, 100] : undefined} allowDecimals={group.key !== 'state'} />
      <Tooltip content={<MetricTooltip rawUnit={group.rawUnit} />} />
      <Legend />
      {group.series.map((series, index) => <Area key={series.dataKey} type="monotone" dataKey={series.dataKey} name={series.label} stroke={METRIC_COLORS[index % METRIC_COLORS.length]} fill="none" strokeWidth={2} dot={group.data.length < 3} connectNulls />)}
    </AreaChart></ResponsiveContainer></div>
  </article>
}

function MetricTooltip({ active, label, payload, rawUnit }) {
  if (!active || !payload?.length) return null
  return <div className="metric-tooltip"><strong>{label}</strong>{payload.filter((item) => item.value != null).map((item) => {
    const metric = item.payload?.[`${item.dataKey}_metric`]
    const reading = metric ? formatMetricReading(metric) : formatRawValue(item.payload?.[`${item.dataKey}_raw`], rawUnit)
    return <div key={item.dataKey}><i style={{ backgroundColor: item.color }} /><span>{item.name}</span><b>{reading.text}</b></div>
  })}</div>
}

function featuredMetrics(metrics) {
  const order = [
    'system.cpu.utilization',
    'system.memory.utilization',
    'system.disk.utilization',
    'system.disk.free',
    'system.network.in',
    'system.network.out',
    'system.network.latency',
    'system.uptime',
  ]
  const available = latestMetrics(metrics)
  const featured = available.filter((metric) => order.includes(metric.metric_name)).sort((left, right) => order.indexOf(left.metric_name) - order.indexOf(right.metric_name))
  return (featured.length ? featured : available).slice(0, 8)
}

function AlertMeasure({ alert }) {
  const context = alert.context || {}
  const unit = context.unit || metricDefaultUnit(context.metric_name)
  const current = formatRawValue(context.current_value, unit).text
  const threshold = formatRawValue(context.threshold, unit).text
  if (current === '—' && threshold === '—') return <span className="muted">Mesure non fournie</span>
  return <span className="alert-measure">Mesure {current}{threshold !== '—' ? ` · seuil ${threshold}` : ''}</span>
}

export function MachineDetail() {
  const { id } = useParams()
  const machine = useApi(`/machines/${id}/`)
  const metrics = useApi(`/metrics/?machine=${id}`, { list: true })
  const alerts = useApi(`/alerts/?machine=${id}`, { list: true })
  const anomalies = useApi(`/anomalies/?machine=${id}`, { list: true })
  const models = useApi('/ml/models/', { list: true })
  const trends = useApi(`/machines/${id}/trends/?hours=24`, { list: true })
  const chartGroups = useMemo(() => buildMetricChartGroups(metrics.data || []), [metrics.data])
  const currentMetrics = useMemo(() => featuredMetrics(metrics.data || []), [metrics.data])
  return <Page title={machine.data?.hostname || 'Détail machine'} description="Métriques, historique, risque et recommandations contextualisées.">
    <DataState state={machine} retry={machine.refresh}>{machine.data && <>
      <div className="detail-strip">
        <div><Status value={machine.data.status} /><small>État</small></div>
        <div><strong>{sourceLabel(machine.data.source_type)}</strong><small>Source</small></div>
        <div><strong>{machine.data.ip_address || '—'}</strong><small>Adresse IP</small></div>
        <div><strong>{machine.data.agent_version || 'Non applicable'}</strong><small>Version agent</small></div>
        <div><strong>{osLabel(machine.data.os_information)}</strong><small>Système</small></div>
        <div><Timestamp value={machine.data.last_seen} compact /><small>Dernier contact</small></div>
      </div>

      <section className="panel">
        <div className="panel-head"><div><h2>État actuel</h2><p>Dernière valeur réelle reçue pour chaque indicateur principal.</p></div></div>
        <DataState state={metrics} retry={metrics.refresh} empty="Aucune métrique n’a encore été reçue pour cette machine.">
          <div className="metric-card-grid">{currentMetrics.map((metric) => <MetricCard key={metric.id || `${metric.metric_name}-${metric.timestamp}`} metric={metric} icon={metricIcon(metric.metric_name)} />)}</div>
        </DataState>
      </section>

      <section className="panel">
        <div className="panel-head"><div><h2>Historique normalisé</h2><p>Chaque graphique regroupe uniquement des unités compatibles. Les détails affichent la valeur exacte et son unité.</p></div></div>
        <DataState state={metrics} retry={metrics.refresh} empty="Pas encore d’historique disponible.">
          <div className="metric-chart-grid">{chartGroups.map((group) => <MetricHistoryChart key={group.key} group={group} />)}</div>
        </DataState>
      </section>

      <section className="panel">
        <h2>Tendances prédictives</h2>
        <p className="muted">Estimations linéaires explicables : elles indiquent un risque potentiel, jamais une certitude.</p>
        <DataState state={trends} retry={trends.refresh} empty="Pas assez d’historique réel pour estimer une tendance.">
          <Table label="Tendances prédictives" rows={trends.data || []} columns={[
            { key: 'metric_name', label: 'Métrique', render: (value) => metricLabel(value) },
            { key: 'last_value', label: 'Valeur actuelle', render: (value, row) => formatRawValue(value, row.unit).text },
            { key: 'trend', label: 'Tendance', render: formatTrend },
            { key: 'rate_of_change_per_hour', label: 'Variation / h', render: (value, row) => formatMetricChangePerHour(value, row.unit) },
            { key: 'risk_score', label: 'Risque estimé', render: (value) => { const risk = formatRiskLevel(value); return badge(`${risk.label} · ${formatPercent(value)}`, risk.tone) } },
            { key: 'confidence', label: 'Confiance', render: (value) => statusLabel(value) },
            { key: 'estimated_threshold_breach_at', label: 'Franchissement potentiel', render: (value) => value ? <Timestamp value={value} relative={false} /> : 'Non estimé' },
          ]} />
        </DataState>
      </section>

      <div className="two-col">
        <section className="panel"><h2>Alertes et recommandations</h2><DataState state={alerts} retry={alerts.refresh} empty="Aucune alerte active pour cette machine.">{alerts.data?.slice(0, 5).map((alert) => <article className="event" key={alert.id}>
          <Severity value={alert.severity} />
          <div><strong>{alert.message}</strong><AlertMeasure alert={alert} /><p>{alert.recommendation || alert.structured_recommendation?.actions?.[0] || 'Analyse en cours.'}</p><Timestamp value={alert.timestamp} compact /></div>
        </article>)}</DataState></section>
        <section className="panel"><h2>Anomalies ML</h2><DataState state={anomalies} retry={anomalies.refresh} empty="Aucune anomalie détectée.">{anomalies.data?.slice(0, 5).map((anomaly) => {
          const signal = formatAnomalySignal(anomaly.score, anomaly.threshold)
          return <article className="event" key={anomaly.id}><BrainCircuit aria-hidden="true" /><div><strong>{signal.label}</strong><ModelReference models={models.data} technicalVersion={anomaly.model_version} /><p>Écart technique {formatReadableNumber(signal.delta, 3)}</p><Timestamp value={anomaly.detected_at} compact /></div></article>
        })}</DataState></section>
      </div>
    </>}</DataState>
  </Page>
}

export function Agents() {
  const { user } = useAuth()
  const canManage = isManager(user)
  const state = useApi('/agents/', { list: true })
  const environments = useApi('/environments/', { list: true, enabled: canManage })
  const { feedback, pending, runAction, clearFeedback } = useActionFeedback()
  const [environmentId, setEnvironmentId] = useState('')
  const [ttl, setTtl] = useState(30)
  const [enrollment, setEnrollment] = useState(null)
  const windowsEnvironments = (environments.data || []).filter((item) => ['WINDOWS', 'MIXED'].includes(item.kind))

  async function createEnrollmentCode(event) {
    event.preventDefault()
    const response = await runAction(() => api.post(`/environments/${environmentId}/enrollment_code/`, { ttl_minutes: ttl }), 'Code créé. Copiez-le maintenant : il ne sera plus affiché ensuite.', 'Impossible de créer le code d’enrôlement.')
    if (response) setEnrollment(response.data)
  }

  async function revokeAgent(agent) {
    const response = await runAction(() => api.patch(`/agents/${agent.id}/`, { enabled: false }), `L’agent ${agent.hostname} a été révoqué.`, 'Impossible de révoquer cet agent.')
    if (response) state.refresh()
  }

  async function copyEnrollmentCode() {
    if (!enrollment?.enrollment_code) return
    try {
      await navigator.clipboard.writeText(enrollment.enrollment_code)
    } catch {
      // The one-time value remains selectable when clipboard access is denied.
    }
  }

  const installerUrl = import.meta.env.VITE_AGENT_INSTALLER_URL
  const actions = installerUrl ? <a className="primary compact" href={installerUrl} rel="noreferrer"><Download />Télécharger l’agent</a> : null
  const columns = [
    { key: 'hostname', label: 'Agent / machine', render: (value) => <div className="primary-cell"><strong>{value}</strong><small>Agent Windows</small></div> },
    { key: 'version', label: 'Version', render: (value) => value || 'Non renseignée' },
    { key: 'enabled', label: 'Autorisation', render: (value) => <Status value={value ? 'ENABLED' : 'DISABLED'} /> },
    { key: 'last_heartbeat', label: 'Dernier heartbeat', render: (value) => <Timestamp value={value} compact /> },
    { key: 'id', label: 'Action', render: (_value, row) => canManage && row.enabled ? <button className="danger-quiet" disabled={pending} onClick={() => revokeAgent(row)}><Power />Révoquer</button> : '—' },
  ]

  return <Page title="Agents Windows" description="Enrôlement, versions, autorisations et état des heartbeats." actions={actions}>
    <ActionFeedback feedback={feedback} onDismiss={clearFeedback} />
    {canManage && <section className="panel enrollment-panel">
      <div className="panel-head"><div><h2>Enrôler un nouvel agent</h2><p>Générez un code à usage unique pour un environnement Windows autorisé.</p></div><Bot aria-hidden="true" /></div>
      <form className="inline-form" onSubmit={createEnrollmentCode}>
        <label>Environnement<select required value={environmentId} onChange={(event) => { setEnvironmentId(event.target.value); setEnrollment(null) }}><option value="">Sélectionner…</option>{windowsEnvironments.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
        <label>Validité (minutes)<input type="number" min="1" max="1440" value={ttl} onChange={(event) => setTtl(Number(event.target.value))} /></label>
        <button className="primary compact" disabled={pending || !environmentId}><Plus />Générer</button>
      </form>
      {enrollment && <div className="one-time-secret" role="status"><div><strong>Code d’enrôlement à usage unique</strong><p>Valable {formatDuration(enrollment.expires_in_minutes * 60)}. Il ne sera pas conservé dans cette interface.</p></div><code>{enrollment.enrollment_code}</code><button onClick={copyEnrollmentCode}><Copy />Copier</button></div>}
      {!environments.loading && !windowsEnvironments.length && <EmptyState title="Aucun environnement Windows" message="Créez d’abord un environnement Windows ou mixte pour autoriser l’enrôlement." />}
    </section>}
    <DataState state={state} retry={state.refresh} emptyTitle="Aucun agent" empty="Aucun agent Windows n’est enregistré."><Table label="Agents Windows" columns={columns} rows={state.data} /></DataState>
  </Page>
}

function alertTransitions(status) {
  if (status === 'NEW') return [['ACKNOWLEDGED', 'Acquitter'], ['IN_PROGRESS', 'Prendre en charge']]
  if (status === 'ACKNOWLEDGED') return [['IN_PROGRESS', 'Prendre en charge'], ['RESOLVED', 'Résoudre']]
  if (status === 'IN_PROGRESS') return [['RESOLVED', 'Résoudre']]
  return []
}

export function Alerts() {
  const { user } = useAuth()
  const canManage = isManager(user)
  const state = useApi('/alerts/', { list: true })
  const { feedback, pending, runAction, clearFeedback } = useActionFeedback()
  const [filter, setFilter] = useState('OPEN')
  const [query, setQuery] = useState('')
  const rows = useMemo(() => (state.data || []).filter((alert) => {
    const statusMatch = filter === 'ALL' || (filter === 'OPEN' ? alert.status !== 'RESOLVED' : alert.status === filter)
    const textMatch = [alert.hostname, alert.message, alert.type, alert.source].some((value) => String(value || '').toLowerCase().includes(query.trim().toLowerCase()))
    return statusMatch && textMatch
  }), [filter, query, state.data])

  async function transition(alert, status) {
    const response = await runAction(() => api.patch(`/alerts/${alert.id}/`, { status }), `Alerte mise à jour : ${statusLabel(status)}.`, 'Impossible de modifier cette alerte.')
    if (response) state.refresh()
  }

  const actions = <div className="filter-actions"><label className="search-control"><Search /><span className="sr-only">Rechercher une alerte</span><input value={query} onChange={(event) => setQuery(event.target.value)} placeholder="Machine ou problème…" /></label><select aria-label="Filtrer les alertes" value={filter} onChange={(event) => setFilter(event.target.value)}><option value="OPEN">Actives</option><option value="ALL">Toutes</option><option value="NEW">Nouvelles</option><option value="ACKNOWLEDGED">Acquittées</option><option value="IN_PROGRESS">En cours</option><option value="RESOLVED">Résolues</option></select></div>
  const columns = [
    { key: 'severity', label: 'Sévérité', render: (value) => <Severity value={value} /> },
    { key: 'hostname', label: 'Machine' },
    { key: 'message', label: 'Problème', render: (value, row) => <div className="primary-cell alert-problem"><strong>{value}</strong><AlertMeasure alert={row} />{row.recommendation && <small>{row.recommendation}</small>}</div> },
    { key: 'source', label: 'Source', render: sourceLabel },
    { key: 'timestamp', label: 'Détectée', render: (value) => <Timestamp value={value} compact /> },
    { key: 'occurrences', label: 'Occurrences', render: formatCount },
    { key: 'status', label: 'État', render: (value) => <Status value={value} /> },
    { key: 'id', label: 'Action', render: (_id, row) => { const transitions = alertTransitions(row.status); return canManage && transitions.length ? <div className="row-actions">{transitions.map(([status, label]) => <button disabled={pending} key={status} onClick={(event) => { event.stopPropagation(); transition(row, status) }}>{label}</button>)}</div> : '—' } },
  ]
  return <Page title="Alertes centralisées" description="Déduplication, corrélation, escalade et recommandations." actions={actions}>
    <ActionFeedback feedback={feedback} onDismiss={clearFeedback} />
    <DataState state={state} retry={state.refresh} emptyTitle="Aucune alerte" empty="Aucune alerte : les moteurs continuent leur analyse.">
      {rows.length ? <Table label="Alertes centralisées" columns={columns} rows={rows} /> : <EmptyState title="Aucune alerte correspondante" message="Modifiez les filtres pour afficher d’autres alertes." />}
    </DataState>
  </Page>
}

function anomalyFeatures(explanation = {}) {
  return Object.entries(explanation.features || {}).filter(([, value]) => value !== null && value !== undefined).slice(0, 3)
}

export function Anomalies() {
  const { user } = useAuth()
  const canManage = isManager(user)
  const state = useApi('/anomalies/', { list: true })
  const models = useApi('/ml/models/', { list: true })
  const { feedback, pending, runAction, clearFeedback } = useActionFeedback()

  async function acknowledge(anomaly) {
    const response = await runAction(() => api.patch(`/anomalies/${anomaly.id}/`, { acknowledged: true }), 'Anomalie acquittée.', 'Impossible d’acquitter cette anomalie.')
    if (response) state.refresh()
  }

  const columns = [
    { key: 'hostname', label: 'Machine' },
    { key: 'score', label: 'Interprétation', render: (value, row) => { const signal = formatAnomalySignal(value, row.threshold); return <div className="primary-cell"><strong>{badge(signal.label, signal.tone)}</strong><small>Écart technique : {formatReadableNumber(signal.delta, 3)}</small></div> } },
    { key: 'explanation', label: 'Métriques analysées', render: (value) => { const features = anomalyFeatures(value); return features.length ? <div className="feature-list">{features.map(([name, featureValue]) => <span key={name}>{metricLabel(name)} <b>{formatRawValue(featureValue, metricDefaultUnit(name)).text}</b></span>)}</div> : 'Non détaillées' } },
    { key: 'model_version', label: 'Modèle', render: (value) => <ModelReference models={models.data} technicalVersion={value} /> },
    { key: 'detected_at', label: 'Détectée', render: (value) => <Timestamp value={value} compact /> },
    { key: 'acknowledged', label: 'État', render: (value) => value ? <Status value="ACKNOWLEDGED" /> : <Status value="NEW" /> },
    { key: 'id', label: 'Action', render: (_id, row) => canManage && !row.acknowledged ? <button disabled={pending} onClick={() => acknowledge(row)}><Check />Acquitter</button> : '—' },
  ]
  return <Page title="Anomalies" description="Signaux détectés par les modèles Isolation Forest actifs, avec contexte explicable.">
    <ActionFeedback feedback={feedback} onDismiss={clearFeedback} />
    <DataState state={state} retry={state.refresh} emptyTitle="Aucune anomalie" empty="Aucune anomalie détectée sur les données réelles."><Table label="Anomalies ML" columns={columns} rows={state.data} /></DataState>
  </Page>
}

function metadataLabel(key) {
  const labels = {
    vendor: 'Constructeur',
    model: 'Modèle matériel',
    vm_count: 'Nombre de VM',
    os: 'Système',
    guest_name: 'Système invité',
    guest_id: 'Identifiant invité',
    datastores: 'Datastores',
    url: 'URL',
    type: 'Type',
    accessible: 'Accessible',
    multiple_host_access: 'Accès multi-hôte',
    generation: 'Génération',
    version: 'Version',
  }
  return labels[key] || key.replace(/_/g, ' ').replace(/^./, (letter) => letter.toUpperCase())
}

function metadataValue(key, value) {
  if (value === null || value === undefined || value === '') return '—'
  if (key.endsWith('_bytes')) return formatBytes(value)
  if (key.endsWith('_mib')) return formatBytes(Number(value) * 1024 ** 2)
  if (typeof value === 'boolean') return value ? 'Oui' : 'Non'
  if (Array.isArray(value)) return value.join(', ') || '—'
  if (typeof value === 'object') return 'Voir les détails techniques'
  if (key.includes('count')) return formatCount(value)
  return String(value)
}

function MetadataPanel({ metadata = {} }) {
  const entries = Object.entries(metadata).filter(([, value]) => typeof value !== 'object' || Array.isArray(value))
  if (!Object.keys(metadata).length) return <EmptyState title="Aucune métadonnée" message="Cette source n’a pas fourni de métadonnées supplémentaires." />
  return <>
    <dl className="metadata-grid">{entries.map(([key, value]) => <div key={key}><dt>{metadataLabel(key)}</dt><dd>{metadataValue(key, value)}</dd></div>)}</dl>
    <details className="technical-details"><summary>Détails techniques bruts</summary><pre>{JSON.stringify(metadata, null, 2)}</pre></details>
  </>
}

function IntegrationPage({ source, title, icon: Icon }) {
  const { user } = useAuth()
  const canManage = isManager(user)
  const state = useApi(`/${source.toLowerCase()}/overview/`)
  const navigate = useNavigate()
  const { feedback, pending, runAction, clearFeedback } = useActionFeedback()
  const assets = state.data ? [...state.data.hosts, ...state.data.vms, ...(state.data.datastores || [])] : []

  async function collect(connector) {
    const response = await runAction(() => api.post(`/connectors/${connector.id}/collect/`), `Collecte ${title} placée dans la file de traitement.`, 'Impossible de planifier la collecte.')
    if (response) state.refresh()
  }

  const connectorColumns = [
    { key: 'name', label: 'Connecteur', render: (value, row) => <div className="primary-cell"><strong>{value}</strong><small>{row.endpoint}</small></div> },
    { key: 'enabled', label: 'Configuration', render: (value) => <Status value={value ? 'ENABLED' : 'DISABLED'} /> },
    { key: 'last_sync_at', label: 'Dernière collecte', render: (value) => <Timestamp value={value} compact /> },
    { key: 'last_error', label: 'Santé', render: (value) => value ? <span title={value}><Status value="FAILED" label="Erreur" /></span> : <Status value="AVAILABLE" /> },
  ]
  if (canManage) connectorColumns.push({ key: 'id', label: 'Action', render: (_id, row) => <button disabled={pending || !row.enabled} onClick={() => collect(row)}><RefreshCw />Collecter</button> })

  return <Page title={title} description={`Découverte, état et métriques réelles ${title}.`}>
    <ActionFeedback feedback={feedback} onDismiss={clearFeedback} />
    <DataState state={state} retry={state.refresh}>{state.data && <>
      <div className="integration-summary">
        <article><Icon aria-hidden="true" /><strong>{formatCount(state.data.connectors.length)}</strong><span>Connecteurs</span></article>
        <article><Server aria-hidden="true" /><strong>{formatCount(state.data.hosts.length)}</strong><span>Hôtes</span></article>
        <article><Boxes aria-hidden="true" /><strong>{formatCount(state.data.vms.length)}</strong><span>Machines virtuelles</span></article>
      </div>
      <section className="panel">
        <div className="panel-head"><div><h2>Connecteurs</h2><p>Les secrets sont référencés par variable ou coffre et ne sont jamais retournés à l’interface.</p></div></div>
        {state.data.connectors.length ? <Table label={`Connecteurs ${title}`} rows={state.data.connectors} columns={connectorColumns} /> : <EmptyState title={`Aucun connecteur ${source === 'VMWARE' ? 'VMware' : 'Hyper-V'}`} message={`Configurez un connecteur ${source === 'VMWARE' ? 'vCenter/VMware' : 'Hyper-V'} pour commencer la supervision réelle.`} />}
      </section>
      <section className="panel">
        <div className="panel-head"><div><h2>Ressources découvertes</h2><p>Hôtes, machines virtuelles et stockage provenant des collectes réelles.</p></div></div>
        {assets.length ? <Table label={`Ressources ${title}`} rows={assets} columns={[
          { key: 'kind', label: 'Type', render: kindLabel },
          { key: 'name', label: 'Nom' },
          { key: 'state', label: 'État', render: (value) => <Status value={value} /> },
          { key: 'last_seen', label: 'Dernière observation', render: (value) => <Timestamp value={value} compact /> },
        ]} onRow={(row) => navigate(`/${source.toLowerCase()}/${row.id}`)} /> : <EmptyState title="Aucune ressource réelle collectée" message="L’inventaire restera vide jusqu’à la première collecte réussie. Aucune donnée de démonstration n’est ajoutée." />}
      </section>
    </>}</DataState>
  </Page>
}

export const VMware = () => <IntegrationPage source="VMWARE" title="VMware / vCenter" icon={CloudCog} />
export const HyperV = () => <IntegrationPage source="HYPERV" title="Microsoft Hyper-V" icon={Boxes} />

function AssetDetail({ source }) {
  const { id } = useParams()
  const asset = useApi(`/assets/${id}/`)
  const machineId = asset.data?.machine
  const metrics = useApi(machineId ? `/metrics/?machine=${machineId}` : null, { list: true, enabled: Boolean(machineId) })
  const chartGroups = useMemo(() => buildMetricChartGroups(metrics.data || []), [metrics.data])
  const currentMetrics = useMemo(() => featuredMetrics(metrics.data || []), [metrics.data])
  return <Page title={asset.data?.name || source} description="Identité, état, parent, métadonnées et métriques réelles.">
    <DataState state={asset} retry={asset.refresh}>{asset.data && <>
      <div className="detail-strip">
        <div><Status value={asset.data.state} /><small>État</small></div>
        <div><strong>{kindLabel(asset.data.kind)}</strong><small>Type</small></div>
        <div><strong>{asset.data.parent_external_id || 'Ressource racine'}</strong><small>Identifiant parent</small></div>
        <div><Timestamp value={asset.data.last_seen} compact /><small>Dernière observation</small></div>
      </div>
      <section className="panel"><div className="panel-head"><div><h2>Informations de la ressource</h2><p>Métadonnées structurées transmises par le connecteur {source}.</p></div></div><MetadataPanel metadata={asset.data.metadata} /></section>
      <section className="panel">
        <div className="panel-head"><div><h2>État actuel</h2><p>Dernières mesures normalisées associées à cette ressource.</p></div></div>
        {!machineId ? <EmptyState title="Aucune machine normalisée associée" message="Cette ressource ne possède pas encore de série métrique exploitable." /> : <DataState state={metrics} retry={metrics.refresh} empty="Aucune mesure réelle n’a encore été collectée."><div className="metric-card-grid">{currentMetrics.map((metric) => <MetricCard key={metric.id || `${metric.metric_name}-${metric.timestamp}`} metric={metric} icon={metricIcon(metric.metric_name)} />)}</div></DataState>}
      </section>
      {machineId && <section className="panel"><div className="panel-head"><div><h2>Historique</h2><p>Graphiques homogènes par unité.</p></div></div><DataState state={metrics} retry={metrics.refresh} empty="Pas encore d’historique disponible."><div className="metric-chart-grid">{chartGroups.map((group) => <MetricHistoryChart key={group.key} group={group} />)}</div></DataState></section>}
      {machineId && <section className="panel"><h2>Dernières mesures</h2><DataState state={metrics} retry={metrics.refresh}><Table label={`Mesures ${source}`} rows={(metrics.data || []).slice(0, 50)} columns={[
        { key: 'timestamp', label: 'Date', render: (value) => <Timestamp value={value} relative={false} /> },
        { key: 'metric_name', label: 'Métrique', render: metricLabel },
        { key: 'metric_value', label: 'Valeur', render: (_value, row) => formatMetricReading(row).text },
        { key: 'status', label: 'Statut', render: (value) => <Status value={value || 'OK'} /> },
      ]} /></DataState></section>}
    </>}</DataState>
  </Page>
}

export const VMwareDetail = () => <AssetDetail source="VMware" />
export const HyperVDetail = () => <AssetDetail source="Hyper-V" />

export function ModelReference({ models = [], technicalVersion }) {
  const model = findModelByTechnicalVersion(models, technicalVersion)
  return <div className="model-reference">
    <strong>{getModelDisplayName(model || { algorithm: 'IsolationForest' })}</strong>
    {technicalVersion && <details><summary>ID technique</summary><code>{technicalVersion}</code></details>}
  </div>
}

export function MLModelCard({ model }) {
  return <article className="panel model-card">
    <div className="panel-head"><div><h2>{getModelDisplayName(model)}</h2><p>{model.active ? 'Version actuelle' : 'Version historique'}</p></div><Status value={model.status} /></div>
    <div className="model-badges">{model.active && badge('Modèle actif', 'normal')}{model.dataset?.synthetic && badge('Dataset synthétique déclaré', 'warning')}</div>
    <dl>
      <div><dt>Entraîné</dt><dd>{model.trained_at ? formatTimestamp(model.trained_at) : 'Pas encore'}</dd></div>
      <div><dt>Échantillons</dt><dd>{formatCount(model.dataset?.rows)}</dd></div>
      <div><dt>Contamination</dt><dd>{formatPercent(model.parameters?.contamination, { fraction: true })}</dd></div>
      <div><dt>Taux anomalies validation</dt><dd>{formatPercent(model.evaluation_metrics?.validation_anomaly_rate, { fraction: true })}</dd></div>
    </dl>
    <details className="technical-details"><summary>Détails scientifiques</summary><dl>
      <div><dt>ID technique</dt><dd><code>{model.version}</code></dd></div>
      <div><dt>Algorithme</dt><dd>{getAlgorithmDisplayName(model.algorithm)}</dd></div>
      <div><dt>Estimateurs</dt><dd>{formatCount(model.parameters?.n_estimators)}</dd></div>
      <div><dt>Seuil technique</dt><dd>{formatReadableNumber(model.decision_threshold, 4)}</dd></div>
      <div><dt>Validation</dt><dd>{model.evaluation_metrics?.method || 'Non évalué'}</dd></div>
      <div><dt>Vérité terrain</dt><dd>{model.evaluation_metrics?.ground_truth_available ? 'Disponible' : 'Absente'}</dd></div>
    </dl><p className="muted">Features : {(model.features || []).map(metricLabel).join(', ') || 'Non renseignées'}</p></details>
  </article>
}

export function ML() {
  const { user } = useAuth()
  const canManage = isManager(user)
  const models = useApi('/ml/models/', { list: true })
  const anomalies = useApi('/anomalies/', { list: true })
  const { feedback, pending, runAction, clearFeedback } = useActionFeedback()
  const history = useMemo(() => orderModelHistory(models.data || []), [models.data])
  const activeModel = history.find((model) => model.active)

  async function train() {
    const response = await runAction(() => api.post('/ml/models/train/', { days: 30, idempotency_key: `manual-${Date.now()}` }), 'Entraînement placé dans la file Celery.', 'Impossible de planifier l’entraînement.')
    if (response) models.refresh()
  }

  async function evaluate() {
    const response = await runAction(() => api.post('/ml/models/evaluate/', { days: 30, idempotency_key: `manual-eval-${Date.now()}` }), 'Évaluation placée dans la file Celery.', 'Impossible de planifier l’évaluation.')
    if (response) models.refresh()
  }

  const actions = canManage ? <><button onClick={evaluate} disabled={pending}>Évaluer règles / ML</button><button className="primary compact" onClick={train} disabled={pending}><BrainCircuit />Entraîner</button></> : null
  return <Page title="Machine Learning" description="Isolation Forest reproductible, modèles versionnés et résultats explicables." actions={actions}>
    <ActionFeedback feedback={feedback} onDismiss={clearFeedback} />
    <div className="ml-summary">
      <article><BrainCircuit /><span>Modèle actif</span><strong>{activeModel ? getModelDisplayName(activeModel) : 'Aucun modèle actif'}</strong></article>
      <article><Gauge /><span>Statut</span><strong>{activeModel ? statusLabel(activeModel.status) : 'Non disponible'}</strong></article>
      <article><Activity /><span>Anomalies détectées</span><strong>{formatCount(anomalies.data?.length)}</strong></article>
      <article><Timer /><span>Dernière analyse observée</span><strong>{anomalies.data?.[0]?.detected_at ? formatTimestamp(anomalies.data[0].detected_at) : 'Aucune'}</strong></article>
    </div>
    <DataState state={models} retry={models.refresh} emptyTitle="Aucun modèle ML" empty="Aucun modèle n’a encore été entraîné avec les métriques réelles.">
      <div className="model-grid">{history.map((model) => <MLModelCard key={model.id} model={model} />)}</div>
    </DataState>
    <section className="panel"><div className="panel-head"><div><h2>Dernières anomalies</h2><p>Interprétation relative au seuil du modèle ; le score brut reste disponible comme détail technique.</p></div></div><DataState state={anomalies} retry={anomalies.refresh} empty="Aucune anomalie détectée."><Table label="Anomalies ML récentes" rows={anomalies.data.slice(0, 20)} columns={[
      { key: 'hostname', label: 'Machine' },
      { key: 'score', label: 'Signal', render: (value, row) => { const signal = formatAnomalySignal(value, row.threshold); return badge(signal.label, signal.tone) } },
      { key: 'model_version', label: 'Modèle', render: (value) => <ModelReference models={history} technicalVersion={value} /> },
      { key: 'detected_at', label: 'Date', render: (value) => <Timestamp value={value} compact /> },
    ]} /></DataState></section>
  </Page>
}

export function Users() {
  const { user } = useAuth()
  const state = useApi('/users/', { list: true })
  const columns = [
    { key: 'email', label: 'Utilisateur', render: (value, row) => <div className="primary-cell"><strong>{value}</strong><small>{row.first_name || row.last_name ? `${row.first_name || ''} ${row.last_name || ''}`.trim() : row.username}</small></div> },
    { key: 'role', label: 'Rôle', render: (value) => <span className="chip">{roleLabel(value)}</span> },
    ...(user?.is_superuser ? [{ key: 'customer', label: 'Client', render: (value) => value || 'Administration globale' }] : []),
    { key: 'is_active', label: 'État', render: (value) => <Status value={value ? 'ENABLED' : 'DISABLED'} /> },
  ]
  return <Page title="Utilisateurs" description="Rôles, accès et rattachement au client courant."><DataState state={state} retry={state.refresh} emptyTitle="Aucun utilisateur" empty="Aucun utilisateur n’est visible dans votre périmètre."><Table label="Utilisateurs et rôles" rows={state.data} columns={columns} /></DataState></Page>
}

const RULE_METRICS = Object.entries(METRIC_LABELS).map(([value, label]) => ({ value, label, unit: metricDefaultUnit(value) }))

function ruleDescription(rule) {
  return `${metricLabel(rule.metric)} ${rule.operator} ${formatRawValue(rule.threshold, metricDefaultUnit(rule.metric)).text} pendant ${formatDuration(rule.duration_seconds)}`
}

export function SettingsPage() {
  const rules = useApi('/rules/', { list: true })
  const prefs = useApi('/notifications/preferences/', { list: true })
  const environments = useApi('/environments/', { list: true })
  const machines = useApi('/machines/', { list: true })
  const connectors = useApi('/connectors/', { list: true })
  const { feedback, pending, runAction, clearFeedback } = useActionFeedback()
  const [rule, setRule] = useState({ name: '', metric: 'system.cpu.utilization', operator: '>', threshold: 90, duration_seconds: 300, severity: 'HIGH', cooldown_seconds: 300, enabled: true, environment: null, machine: null })
  const [pref, setPref] = useState({ channel: 'EMAIL', destination: '', minimum_severity: 'HIGH', cooldown_seconds: 300, enabled: true, user: null })

  async function addRule(event) {
    event.preventDefault()
    const response = await runAction(() => api.post('/rules/', rule), 'Règle créée.', 'Impossible de créer cette règle.')
    if (response) { setRule((current) => ({ ...current, name: '' })); rules.refresh() }
  }

  async function addPref(event) {
    event.preventDefault()
    const response = await runAction(() => api.post('/notifications/preferences/', pref), 'Préférence de notification enregistrée.', 'Impossible d’enregistrer cette préférence.')
    if (response) { setPref((current) => ({ ...current, destination: '' })); prefs.refresh() }
  }

  async function toggleRule(item) {
    const response = await runAction(() => api.post(`/rules/${item.id}/toggle/`), `Règle ${item.enabled ? 'désactivée' : 'activée'}.`, 'Impossible de modifier cette règle.')
    if (response) rules.refresh()
  }

  const selectedRuleUnit = metricDefaultUnit(rule.metric)
  return <Page title="Configuration" description="Règles, notifications et sources avec unités explicites.">
    <ActionFeedback feedback={feedback} onDismiss={clearFeedback} />
    <div className="settings-grid">
      <section className="panel">
        <div className="panel-head"><div><h2>Moteur de règles</h2><p>Condition, seuil dans l’unité native et durée minimale.</p></div><ShieldAlert /></div>
        <form className="form-grid" onSubmit={addRule}>
          <label>Nom<input required value={rule.name} onChange={(event) => setRule({ ...rule, name: event.target.value })} /></label>
          <label>Métrique<select required value={rule.metric} onChange={(event) => setRule({ ...rule, metric: event.target.value })}>{RULE_METRICS.map((item) => <option value={item.value} key={item.value}>{item.label}</option>)}</select></label>
          <label>Opérateur<select value={rule.operator} onChange={(event) => setRule({ ...rule, operator: event.target.value })}>{['>', '<', '>=', '<=', '==', '!='].map((operator) => <option key={operator}>{operator}</option>)}</select></label>
          <label>Seuil ({selectedRuleUnit || 'valeur native'})<input type="number" step="any" value={rule.threshold} onChange={(event) => setRule({ ...rule, threshold: Number(event.target.value) })} /></label>
          <label>Durée minimale (secondes)<input type="number" min="0" value={rule.duration_seconds} onChange={(event) => setRule({ ...rule, duration_seconds: Number(event.target.value) })} /><small>{formatDuration(rule.duration_seconds)}</small></label>
          <label>Sévérité<select value={rule.severity} onChange={(event) => setRule({ ...rule, severity: event.target.value })}>{['INFO', 'WARNING', 'HIGH', 'CRITICAL'].map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>Environnement<select value={rule.environment || ''} onChange={(event) => setRule({ ...rule, environment: event.target.value || null })}><option value="">Tous</option>{environments.data.map((item) => <option value={item.id} key={item.id}>{item.name}</option>)}</select></label>
          <label>Machine<select value={rule.machine || ''} onChange={(event) => setRule({ ...rule, machine: event.target.value || null })}><option value="">Toutes</option>{machines.data.map((item) => <option value={item.id} key={item.id}>{item.hostname}</option>)}</select></label>
          <button className="primary compact" disabled={pending}><Plus />Ajouter la règle</button>
        </form>
        <DataState state={rules} retry={rules.refresh} emptyTitle="Aucune règle" empty="Aucune règle de supervision n’est configurée.">{rules.data.map((item) => <div className="setting-row" key={item.id}><div><strong>{item.name}</strong><p>{ruleDescription(item)}</p><small>Cooldown {formatDuration(item.cooldown_seconds, { compact: true })}</small></div><Severity value={item.severity} /><Status value={item.enabled ? 'ENABLED' : 'DISABLED'} /><button disabled={pending} onClick={() => toggleRule(item)}><Power />{item.enabled ? 'Désactiver' : 'Activer'}</button></div>)}</DataState>
      </section>
      <section className="panel">
        <div className="panel-head"><div><h2>Notifications</h2><p>Email actif ; architecture prête pour les futurs canaux.</p></div><Bell /></div>
        <form className="form-grid" onSubmit={addPref}>
          <label>Destination email<input type="email" required value={pref.destination} onChange={(event) => setPref({ ...pref, destination: event.target.value })} /></label>
          <label>Sévérité minimale<select value={pref.minimum_severity} onChange={(event) => setPref({ ...pref, minimum_severity: event.target.value })}>{['HIGH', 'CRITICAL'].map((value) => <option key={value}>{value}</option>)}</select></label>
          <label>Cooldown (secondes)<input type="number" min="0" value={pref.cooldown_seconds} onChange={(event) => setPref({ ...pref, cooldown_seconds: Number(event.target.value) })} /><small>{formatDuration(pref.cooldown_seconds)}</small></label>
          <button className="primary compact" disabled={pending}><Save />Enregistrer</button>
        </form>
        <DataState state={prefs} retry={prefs.refresh} emptyTitle="Aucune préférence" empty="Aucune destination email n’est configurée.">{prefs.data.map((item) => <div className="setting-row" key={item.id}><div><strong>{item.destination}</strong><p>{item.channel} · à partir de {item.minimum_severity} · cooldown {formatDuration(item.cooldown_seconds, { compact: true })}</p></div><Status value={item.enabled ? 'ENABLED' : 'DISABLED'} /></div>)}</DataState>
        <div className="panel-head section-gap"><div><h2>Connecteurs</h2><p>Sources VMware et Hyper-V configurées.</p></div><Database /></div>
        <DataState state={connectors} retry={connectors.refresh} emptyTitle="Aucun connecteur" empty="Aucun connecteur de virtualisation n’est configuré.">{connectors.data.map((item) => <div className="setting-row" key={item.id}><div><strong>{item.name}</strong><p>{sourceLabel(item.kind)} · {item.endpoint}</p></div><Status value={!item.enabled ? 'DISABLED' : item.last_error ? 'FAILED' : 'AVAILABLE'} /></div>)}</DataState>
      </section>
    </div>
  </Page>
}

const AUDIT_ACTIONS = [
  'USER_LOGIN', 'USER_LOGOUT', 'USER_CREATED', 'USER_UPDATED', 'USER_DELETED',
  'AGENT_ENROLLMENT_CODE_CREATED', 'AGENT_ENROLLED', 'AGENT_REVOKED', 'AGENT_UPDATED',
  'MACHINE_CREATED', 'MACHINE_UPDATED', 'MACHINE_DELETED', 'ALERT_CREATED', 'ALERT_UPDATED',
  'ALERT_ACKNOWLEDGED', 'ALERT_IN_PROGRESS', 'ALERT_RESOLVED', 'MODEL_TRAINING_QUEUED',
  'MODEL_EVALUATION_QUEUED', 'MODEL_TRAINED', 'CONNECTOR_COLLECTION_QUEUED', 'CONFIG_CHANGED',
]
const AUDIT_LABELS = {
  USER_LOGIN: 'Connexion utilisateur', USER_LOGOUT: 'Déconnexion utilisateur', USER_CREATED: 'Utilisateur créé', USER_UPDATED: 'Utilisateur modifié', USER_DELETED: 'Utilisateur supprimé',
  AGENT_ENROLLMENT_CODE_CREATED: 'Code d’enrôlement créé', AGENT_ENROLLED: 'Agent enrôlé', AGENT_REVOKED: 'Agent révoqué', AGENT_UPDATED: 'Agent modifié',
  MACHINE_CREATED: 'Machine créée', MACHINE_UPDATED: 'Machine modifiée', MACHINE_DELETED: 'Machine supprimée', ALERT_CREATED: 'Alerte créée', ALERT_UPDATED: 'Alerte modifiée',
  ALERT_ACKNOWLEDGED: 'Alerte acquittée', ALERT_IN_PROGRESS: 'Alerte prise en charge', ALERT_RESOLVED: 'Alerte résolue', MODEL_TRAINING_QUEUED: 'Entraînement planifié',
  MODEL_EVALUATION_QUEUED: 'Évaluation planifiée', MODEL_TRAINED: 'Modèle entraîné', CONNECTOR_COLLECTION_QUEUED: 'Collecte planifiée', CONFIG_CHANGED: 'Configuration modifiée',
}
const EMPTY_AUDIT_FILTERS = { search: '', action: '', actor: '', target_type: '', ip_address: '', from: '', to: '' }

export function Audit() {
  const [filters, setFilters] = useState(EMPTY_AUDIT_FILTERS)
  const [applied, setApplied] = useState(EMPTY_AUDIT_FILTERS)
  const [page, setPage] = useState(1)
  const path = useMemo(() => {
    const params = new URLSearchParams({ page: String(page), page_size: '25', ordering: '-timestamp' })
    for (const [key, value] of Object.entries(applied)) {
      if (!value) continue
      const normalized = ['from', 'to'].includes(key) ? new Date(value).toISOString() : value
      params.set(key, normalized)
    }
    return `/audit/?${params}`
  }, [applied, page])
  const state = useApi(path)
  const rows = state.data?.results || []
  const pages = Math.max(1, Math.ceil((state.data?.count || 0) / 25))

  function applyFilters(event) { event.preventDefault(); setPage(1); setApplied({ ...filters }) }
  function clearFilters() { setFilters(EMPTY_AUDIT_FILTERS); setApplied(EMPTY_AUDIT_FILTERS); setPage(1) }

  const columns = [
    { key: 'timestamp', label: 'Date', render: (value) => <Timestamp value={value} relative={false} /> },
    { key: 'action', label: 'Action', render: (value) => <span className="chip">{AUDIT_LABELS[value] || value}</span> },
    { key: 'actor_email', label: 'Acteur', render: (value) => value || 'Système' },
    { key: 'target_repr', label: 'Cible', render: (value, row) => value || `${row.target_type}:${row.target_id}` },
    { key: 'ip_address', label: 'Adresse IP' },
    { key: 'metadata', label: 'Métadonnées', render: (value) => Object.keys(value || {}).length ? <details className="audit-metadata"><summary>Afficher</summary><pre>{JSON.stringify(value, null, 2)}</pre></details> : '—' },
  ]
  return <Page title="Journal d’audit" description="Événements de sécurité et changements opérationnels immuables.">
    <form className="panel audit-filters" onSubmit={applyFilters}>
      <label>Recherche<input aria-label="Recherche audit" value={filters.search} onChange={(event) => setFilters({ ...filters, search: event.target.value })} placeholder="Acteur, action, cible…" /></label>
      <label>Action<select value={filters.action} onChange={(event) => setFilters({ ...filters, action: event.target.value })}><option value="">Toutes</option>{AUDIT_ACTIONS.map((action) => <option value={action} key={action}>{AUDIT_LABELS[action] || action}</option>)}</select></label>
      <label>Acteur (ID)<input inputMode="numeric" value={filters.actor} onChange={(event) => setFilters({ ...filters, actor: event.target.value })} /></label>
      <label>Type de cible<input value={filters.target_type} onChange={(event) => setFilters({ ...filters, target_type: event.target.value })} placeholder="inventory.Machine" /></label>
      <label>Adresse IP<input value={filters.ip_address} onChange={(event) => setFilters({ ...filters, ip_address: event.target.value })} placeholder="203.0.113.10" /></label>
      <label>Depuis<input type="datetime-local" value={filters.from} onChange={(event) => setFilters({ ...filters, from: event.target.value })} /></label>
      <label>Jusqu’à<input type="datetime-local" value={filters.to} onChange={(event) => setFilters({ ...filters, to: event.target.value })} /></label>
      <div className="audit-filter-actions"><button type="button" onClick={clearFilters}>Effacer</button><button className="primary compact" type="submit">Rechercher</button></div>
    </form>
    <DataState state={state} retry={state.refresh}>{!state.loading && !rows.length ? <EmptyState title="Aucun événement" message="Aucun événement ne correspond aux filtres appliqués." /> : <><Table label="Journal d’audit" rows={rows} columns={columns} /><div className="audit-pagination"><span>{formatCount(state.data?.count)} événements · page {page} sur {pages}</span><div><button disabled={page <= 1} onClick={() => setPage((value) => value - 1)}>Précédente</button><button disabled={page >= pages} onClick={() => setPage((value) => value + 1)}>Suivante</button></div></div></>}</DataState>
  </Page>
}

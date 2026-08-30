const formatterCache = new Map()

function numberFormatter(maximumFractionDigits = 1, minimumFractionDigits = 0) {
  const key = `${minimumFractionDigits}:${maximumFractionDigits}`
  if (!formatterCache.has(key)) {
    formatterCache.set(key, new Intl.NumberFormat('fr-FR', {
      minimumFractionDigits,
      maximumFractionDigits,
    }))
  }
  return formatterCache.get(key)
}

export function hasNumericValue(value) {
  return value !== null && value !== undefined && value !== '' && Number.isFinite(Number(value))
}

export function formatReadableNumber(value, digits = 1) {
  if (!hasNumericValue(value)) return '—'
  return numberFormatter(digits).format(Number(value))
}

export function formatReadableValue(value, unit = '', digits = 1) {
  if (!hasNumericValue(value)) return '—'
  const suffix = unit ? ` ${unit}` : ''
  return `${formatReadableNumber(value, digits)}${suffix}`
}

const BYTE_UNITS = ['o', 'Ko', 'Mo', 'Go', 'To', 'Po']
const BIT_UNITS = ['b', 'Kb', 'Mb', 'Gb', 'Tb', 'Pb']

function scaled(value, units, base = 1024) {
  if (!hasNumericValue(value)) return null
  const numericValue = Number(value)
  const magnitude = Math.abs(numericValue)
  const index = magnitude > 0
    ? Math.min(Math.floor(Math.log(magnitude) / Math.log(base)), units.length - 1)
    : 0
  const safeIndex = Math.max(0, index)
  return { value: numericValue / (base ** safeIndex), unit: units[safeIndex], factor: base ** safeIndex }
}

export function formatBytes(value) {
  const result = scaled(value, BYTE_UNITS)
  return result ? formatReadableValue(result.value, result.unit) : '—'
}

export const formatMemory = formatBytes
export const formatStorage = formatBytes

export function formatByteRate(value) {
  const result = scaled(value, BYTE_UNITS)
  return result ? formatReadableValue(result.value, `${result.unit}/s`) : '—'
}

export function formatBitRate(value) {
  const result = scaled(value, BIT_UNITS, 1000)
  return result ? formatReadableValue(result.value, `${result.unit}/s`) : '—'
}

export function formatRate(value, unit = 'bytes/s') {
  const normalized = normalizeUnit(unit)
  if (normalized === 'bytes/s') return formatByteRate(toBaseValue(value, unit))
  if (normalized === 'bits/s') return formatBitRate(toBaseValue(value, unit))
  return formatReadableValue(value, unit)
}

export function formatPercent(value, { fraction = false } = {}) {
  if (!hasNumericValue(value)) return '—'
  const percent = Number(value) * (fraction ? 100 : 1)
  return formatReadableValue(percent, '%')
}

export function formatLatency(value, unit = 'ms') {
  if (!hasNumericValue(value)) return '—'
  const milliseconds = normalizeUnit(unit) === 'seconds' ? Number(value) * 1000 : Number(value)
  if (Math.abs(milliseconds) >= 1000) return formatReadableValue(milliseconds / 1000, 's')
  return formatReadableValue(milliseconds, 'ms')
}

export function formatDuration(value, { compact = false, maxParts = compact ? 2 : 3 } = {}) {
  if (!hasNumericValue(value) || Number(value) < 0) return '—'
  let remaining = Math.round(Number(value))
  if (remaining === 0) return '0 s'
  const units = [['j', 86400], ['h', 3600], ['min', 60], ['s', 1]]
  const parts = []
  for (const [label, seconds] of units) {
    const amount = Math.floor(remaining / seconds)
    if (amount > 0) {
      parts.push(`${amount} ${label}`)
      remaining -= amount * seconds
    }
    if (parts.length >= maxParts) break
  }
  return parts.join(' ')
}

export function formatTemperature(value, unit = '°C') {
  if (!hasNumericValue(value)) return '—'
  if (String(unit).toUpperCase().includes('F')) return formatReadableValue((Number(value) - 32) * (5 / 9), '°C')
  return formatReadableValue(value, '°C')
}

export function formatFrequency(value, unit = 'MHz') {
  if (!hasNumericValue(value)) return '—'
  const rawUnit = String(unit || '').toLowerCase()
  let megahertz = Number(value)
  if (rawUnit === 'hz') megahertz /= 1_000_000
  if (rawUnit === 'khz') megahertz /= 1_000
  if (rawUnit === 'ghz') megahertz *= 1_000
  if (Math.abs(megahertz) >= 1000) return formatReadableValue(megahertz / 1000, 'GHz')
  return formatReadableValue(megahertz, 'MHz')
}

export function formatCount(value) {
  if (!hasNumericValue(value)) return '—'
  return numberFormatter(0).format(Math.round(Number(value)))
}

const exactDateFormatter = new Intl.DateTimeFormat('fr-FR', {
  day: '2-digit', month: '2-digit', year: 'numeric', hour: '2-digit', minute: '2-digit',
})

export function formatTimestamp(value) {
  if (!value) return '—'
  const date = new Date(value)
  return Number.isNaN(date.getTime()) ? '—' : exactDateFormatter.format(date)
}

export function formatRelativeTime(value, now = Date.now()) {
  if (!value) return 'Jamais'
  const date = new Date(value)
  if (Number.isNaN(date.getTime())) return 'Date invalide'
  const deltaSeconds = Math.round((Number(now) - date.getTime()) / 1000)
  const future = deltaSeconds < 0
  const absolute = Math.abs(deltaSeconds)
  let text
  if (absolute < 60) text = `${absolute} s`
  else if (absolute < 3600) text = `${Math.floor(absolute / 60)} min`
  else if (absolute < 86400) text = `${Math.floor(absolute / 3600)} h`
  else if (absolute < 604800) text = `${Math.floor(absolute / 86400)} j`
  else return formatTimestamp(value)
  return future ? `Dans ${text}` : `Il y a ${text}`
}

export const STATUS_LABELS = {
  ONLINE: 'En ligne', OFFLINE: 'Hors ligne', UNKNOWN: 'Inconnu', DEGRADED: 'Dégradé',
  CRITICAL: 'Critique', WARNING: 'Avertissement', NORMAL: 'Normal', NEW: 'Nouvelle',
  ACKNOWLEDGED: 'Acquittée', IN_PROGRESS: 'En cours', RESOLVED: 'Résolue', RUNNING: 'En cours',
  STOPPED: 'Arrêté', AVAILABLE: 'Disponible', UNAVAILABLE: 'Indisponible', POWEREDON: 'En marche',
  POWEREDOFF: 'Arrêtée', SUSPENDED: 'Suspendue', PAUSED: 'Suspendue', READY: 'Prêt',
  TRAINING: 'En entraînement', FAILED: 'Échec', ARCHIVED: 'Archivé', OK: 'Normal',
  UNREACHABLE: 'Injoignable', ENABLED: 'Activé', DISABLED: 'Désactivé',
}

export const SEVERITY_LABELS = { INFO: 'Information', WARNING: 'Avertissement', HIGH: 'Élevée', CRITICAL: 'Critique' }
export const ROLE_LABELS = { ADMIN: 'Administrateur', SUPERVISOR: 'Superviseur', VIEWER: 'Lecture seule' }
export const SOURCE_LABELS = { WINDOWS: 'Windows', VMWARE: 'VMware', HYPERV: 'Hyper-V', MIXED: 'Mixte' }

function normalizedKey(value) {
  return String(value || 'UNKNOWN').replace(/[\s_-]/g, '').toUpperCase()
}

export function statusLabel(value) {
  const direct = String(value || 'UNKNOWN').toUpperCase()
  return STATUS_LABELS[direct] || STATUS_LABELS[normalizedKey(value)] || String(value || 'Inconnu')
}
export function severityLabel(value) { return SEVERITY_LABELS[String(value || 'INFO').toUpperCase()] || String(value || 'Information') }
export function roleLabel(value) { return ROLE_LABELS[String(value || '').toUpperCase()] || String(value || '—') }
export function sourceLabel(value) { return SOURCE_LABELS[String(value || '').toUpperCase()] || String(value || '—') }

export const METRIC_LABELS = {
  'system.cpu.utilization': 'CPU',
  'system.memory.utilization': 'RAM',
  'system.disk.utilization': 'Disque utilisé',
  'system.disk.free': 'Disque libre',
  'system.disk.io.read': 'Lecture disque',
  'system.disk.io.write': 'Écriture disque',
  'system.network.in': 'Réseau entrant',
  'system.network.out': 'Réseau sortant',
  'system.network.latency': 'Latence réseau',
  'system.uptime': 'Durée de fonctionnement',
  'system.process.count': 'Processus',
  'system.gpu.utilization': 'GPU',
  'windows.service.state': 'Service Windows',
  'virtual.machine.state': 'État de la VM',
  'vmware.datastore.utilization': 'Datastore utilisé',
  'machine.online': 'Disponibilité machine',
}

export function metricLabel(name) { return METRIC_LABELS[name] || String(name || 'Mesure').replace(/[._]/g, ' ') }

export const METRIC_UNITS = {
  'system.cpu.utilization': '%',
  'system.memory.utilization': '%',
  'system.disk.utilization': '%',
  'system.disk.free': 'bytes',
  'system.disk.io.read': 'bytes/s',
  'system.disk.io.write': 'bytes/s',
  'system.network.in': 'bytes/s',
  'system.network.out': 'bytes/s',
  'system.network.latency': 'ms',
  'system.uptime': 'seconds',
  'system.process.count': 'count',
  'system.gpu.utilization': '%',
  'windows.service.state': 'state',
  'virtual.machine.state': 'state',
  'vmware.datastore.utilization': '%',
  'machine.online': 'state',
}

export function metricDefaultUnit(name) { return METRIC_UNITS[name] || '' }

export function normalizeUnit(unit = '') {
  const raw = String(unit || '').trim()
  const lower = raw.toLowerCase()
  if (/^[kmg]b\/s$/i.test(raw) && raw.includes('B')) return 'bytes/s'
  if (['bytes', 'byte', 'b', 'o', 'octet', 'octets'].includes(lower) && raw !== 'b') return 'bytes'
  if (['bytes/s', 'byte/s', 'b/s', 'o/s', 'octets/s', 'kib/s', 'mib/s', 'gib/s'].includes(lower) && raw !== 'b/s') return 'bytes/s'
  if (['bits/s', 'bit/s', 'bps', 'b/s', 'kb/s', 'mb/s', 'gb/s'].includes(lower)) return 'bits/s'
  if (['%', 'percent', 'percentage'].includes(lower)) return '%'
  if (['ms', 'millisecond', 'milliseconds'].includes(lower)) return 'ms'
  if (['s', 'sec', 'second', 'seconds'].includes(lower)) return 'seconds'
  if (['count', 'counter', 'items', 'processes', 'packets'].includes(lower)) return 'count'
  if (['state', 'status', 'boolean', 'bool'].includes(lower)) return 'state'
  if (['°c', 'c', 'celsius'].includes(lower)) return '°C'
  if (['hz', 'khz', 'mhz', 'ghz'].includes(lower)) return 'frequency'
  return raw
}

function toBaseValue(value, unit = '') {
  if (!hasNumericValue(value)) return null
  const lower = String(unit || '').toLowerCase()
  let numericValue = Number(value)
  if (lower === 'kib/s') numericValue *= 1024
  if (lower === 'mib/s') numericValue *= 1024 ** 2
  if (lower === 'gib/s') numericValue *= 1024 ** 3
  if (lower === 'kb/s') numericValue *= 1000
  if (lower === 'mb/s') numericValue *= 1000 ** 2
  if (lower === 'gb/s') numericValue *= 1000 ** 3
  return numericValue
}

export function metricDimension(metric) {
  const metadata = metric?.metadata || {}
  return metadata.device || metadata.mountpoint || metadata.interface || metadata.service_name || metadata.service
    || metadata.gpu_name || (metadata.gpu_index !== undefined ? `GPU ${metadata.gpu_index}` : '')
    || metadata.datastore || metadata.resource_external_id || ''
}

export function metricSeriesLabel(metric) {
  const label = metricLabel(metric?.metric_name)
  const dimension = metricDimension(metric)
  return dimension ? `${label} · ${dimension}` : label
}

function stateReading(metric) {
  if (metric?.status) return statusLabel(metric.status)
  if (metric?.metric_name === 'windows.service.state') return Number(metric.metric_value) === 1 ? 'En cours' : 'Arrêté'
  if (metric?.metric_name === 'virtual.machine.state') return Number(metric.metric_value) === 1 ? 'En marche' : 'Arrêtée'
  return Number(metric?.metric_value) === 1 ? 'Actif' : 'Inactif'
}

export function formatRawValue(value, unit = '') {
  if (!hasNumericValue(value)) return { value: null, unit: '', text: '—' }
  const normalized = normalizeUnit(unit)
  const baseValue = toBaseValue(value, unit)
  if (normalized === 'bytes' || normalized === 'bytes/s') {
    const result = scaled(baseValue, BYTE_UNITS)
    const displayUnit = normalized === 'bytes/s' ? `${result.unit}/s` : result.unit
    return { value: result.value, unit: displayUnit, text: formatReadableValue(result.value, displayUnit) }
  }
  if (normalized === 'bits/s') {
    const result = scaled(baseValue, BIT_UNITS, 1000)
    return { value: result.value, unit: `${result.unit}/s`, text: formatReadableValue(result.value, `${result.unit}/s`) }
  }
  if (normalized === '%') return { value: baseValue, unit: '%', text: formatPercent(baseValue) }
  if (normalized === 'ms') {
    const text = formatLatency(baseValue, 'ms')
    return { value: baseValue >= 1000 ? baseValue / 1000 : baseValue, unit: baseValue >= 1000 ? 's' : 'ms', text }
  }
  if (normalized === 'seconds') return { value: baseValue, unit: 's', text: formatDuration(baseValue) }
  if (normalized === 'count') return { value: Math.round(baseValue), unit: '', text: formatCount(baseValue) }
  if (normalized === '°C') return { value: baseValue, unit: '°C', text: formatTemperature(baseValue, unit) }
  if (normalized === 'frequency') {
    const text = formatFrequency(baseValue, unit)
    return { value: baseValue, unit: text.split(' ').at(-1), text }
  }
  return { value: baseValue, unit: normalized, text: formatReadableValue(baseValue, normalized) }
}

export function formatMetricReading(metric) {
  const label = metricSeriesLabel(metric)
  if (normalizeUnit(metric?.unit) === 'state' || ['windows.service.state', 'virtual.machine.state'].includes(metric?.metric_name)) {
    return { label, value: metric?.metric_value, unit: '', text: stateReading(metric), detail: '' }
  }
  if (!hasNumericValue(metric?.metric_value)) return { label, value: null, unit: '', text: '—', detail: '' }
  const formatted = formatRawValue(metric.metric_value, metric.unit || '')
  const metadata = metric.metadata || {}
  let detail = ''
  if (metric.metric_name === 'system.memory.utilization' && hasNumericValue(metadata.total_bytes) && hasNumericValue(metadata.available_bytes)) {
    detail = `${formatMemory(Number(metadata.total_bytes) - Number(metadata.available_bytes))} / ${formatMemory(metadata.total_bytes)}`
  }
  if (metric.metric_name === 'system.gpu.utilization' && hasNumericValue(metadata.memory_total_mib)) {
    const used = hasNumericValue(metadata.memory_used_mib) ? Number(metadata.memory_used_mib) * 1024 ** 2 : null
    detail = used === null ? `${formatMemory(Number(metadata.memory_total_mib) * 1024 ** 2)} au total` : `${formatMemory(used)} / ${formatMemory(Number(metadata.memory_total_mib) * 1024 ** 2)}`
  }
  return { label, ...formatted, detail }
}

export function formatMetricChangePerHour(value, unit = '') {
  if (!hasNumericValue(value)) return '—'
  return `${formatRawValue(value, unit).text} par h`
}

export function formatRiskLevel(value) {
  if (!hasNumericValue(value)) return { label: 'Indéterminé', tone: 'unknown' }
  const score = Number(value)
  if (score >= 75) return { label: 'Critique', tone: 'critical' }
  if (score >= 50) return { label: 'Élevé', tone: 'high' }
  if (score >= 25) return { label: 'Modéré', tone: 'warning' }
  return { label: 'Faible', tone: 'normal' }
}

export function formatAnomalySignal(score, threshold) {
  if (!hasNumericValue(score) || !hasNumericValue(threshold)) return { label: 'Signal non interprétable', tone: 'unknown', delta: null }
  const delta = Number(score) - Number(threshold)
  return { label: delta >= 0 ? 'Au-dessus du seuil du modèle' : 'Sous le seuil du modèle', tone: delta >= 0 ? 'high' : 'normal', delta }
}

export function formatTrend(value) {
  const labels = { increasing: 'Croissante', rising: 'Croissante', decreasing: 'Décroissante', falling: 'Décroissante', stable: 'Stable', insufficient_data: 'Données insuffisantes' }
  return labels[String(value || '').toLowerCase()] || String(value || 'Indéterminée')
}

const GROUP_ORDER = ['percent', 'storage', 'throughput', 'bitrate', 'latency', 'duration', 'count', 'temperature', 'frequency', 'state', 'other']

function groupDefinition(unit) {
  switch (normalizeUnit(unit)) {
    case '%': return { key: 'percent', title: 'Utilisation', baseUnit: '%' }
    case 'bytes': return { key: 'storage', title: 'Capacité disponible', baseUnit: 'bytes' }
    case 'bytes/s': return { key: 'throughput', title: 'Débits', baseUnit: 'bytes/s' }
    case 'bits/s': return { key: 'bitrate', title: 'Débits réseau', baseUnit: 'bits/s' }
    case 'ms': return { key: 'latency', title: 'Latence', baseUnit: 'ms' }
    case 'seconds': return { key: 'duration', title: 'Disponibilité', baseUnit: 'seconds' }
    case 'count': return { key: 'count', title: 'Comptages', baseUnit: 'count' }
    case '°C': return { key: 'temperature', title: 'Température', baseUnit: '°C' }
    case 'frequency': return { key: 'frequency', title: 'Fréquence', baseUnit: 'frequency' }
    case 'state': return { key: 'state', title: 'État opérationnel', baseUnit: 'state' }
    default: return { key: `other:${unit || 'value'}`, title: 'Autres mesures', baseUnit: unit || '' }
  }
}

function chartScaleFor(unit, maximum) {
  const magnitude = Math.abs(maximum || 0)
  if (unit === 'bytes' || unit === 'bytes/s') {
    const suffix = unit === 'bytes/s' ? '/s' : ''
    const units = [[1024 ** 4, `To${suffix}`], [1024 ** 3, `Go${suffix}`], [1024 ** 2, `Mo${suffix}`], [1024, `Ko${suffix}`]]
    const selected = units.find(([factor]) => magnitude >= factor)
    return selected ? { factor: selected[0], unit: selected[1] } : { factor: 1, unit: `o${suffix}` }
  }
  if (unit === 'bits/s') {
    const units = [[1000 ** 4, 'Tb/s'], [1000 ** 3, 'Gb/s'], [1000 ** 2, 'Mb/s'], [1000, 'Kb/s']]
    const selected = units.find(([factor]) => magnitude >= factor)
    return selected ? { factor: selected[0], unit: selected[1] } : { factor: 1, unit: 'b/s' }
  }
  if (unit === 'seconds') {
    if (magnitude >= 86400) return { factor: 86400, unit: 'j' }
    if (magnitude >= 3600) return { factor: 3600, unit: 'h' }
    if (magnitude >= 60) return { factor: 60, unit: 'min' }
    return { factor: 1, unit: 's' }
  }
  return { factor: 1, unit: ['count', 'state'].includes(unit) ? '' : unit }
}

function metricTimeLabel(timestamp) {
  const date = new Date(timestamp)
  if (Number.isNaN(date.getTime())) return '—'
  return date.toLocaleTimeString('fr-FR', { hour: '2-digit', minute: '2-digit', second: '2-digit' })
}

export function buildMetricChartGroups(metrics = []) {
  const groups = new Map()
  for (const metric of metrics) {
    if (!hasNumericValue(metric?.metric_value) || !metric?.timestamp) continue
    const definition = groupDefinition(metric.unit)
    if (!groups.has(definition.key)) groups.set(definition.key, { ...definition, metrics: [], seriesMap: new Map() })
    const group = groups.get(definition.key)
    const identity = `${metric.metric_name}|${metricDimension(metric)}`
    if (!group.seriesMap.has(identity)) group.seriesMap.set(identity, { identity, label: metricSeriesLabel(metric) })
    group.metrics.push({ ...metric, numericValue: toBaseValue(metric.metric_value, metric.unit), identity })
  }

  return [...groups.values()].map((group) => {
    const maximum = Math.max(...group.metrics.map((metric) => Math.abs(metric.numericValue)), 0)
    const scale = chartScaleFor(group.baseUnit, maximum)
    const series = [...group.seriesMap.values()].sort((left, right) => left.label.localeCompare(right.label, 'fr')).map((item, index) => ({ ...item, dataKey: `series_${index}` }))
    const seriesByIdentity = new Map(series.map((item) => [item.identity, item]))
    const buckets = new Map()
    for (const metric of [...group.metrics].sort((left, right) => new Date(left.timestamp) - new Date(right.timestamp))) {
      const timestamp = new Date(metric.timestamp).toISOString()
      const row = buckets.get(timestamp) || { timestamp, time: metricTimeLabel(metric.timestamp) }
      const dataKey = seriesByIdentity.get(metric.identity).dataKey
      row[dataKey] = metric.numericValue / scale.factor
      row[`${dataKey}_raw`] = metric.metric_value
      row[`${dataKey}_metric`] = metric
      buckets.set(timestamp, row)
    }
    return { key: group.key, title: group.title, unit: scale.unit, rawUnit: group.baseUnit, series, data: [...buckets.values()].slice(-60) }
  }).sort((left, right) => GROUP_ORDER.indexOf(left.key.split(':')[0]) - GROUP_ORDER.indexOf(right.key.split(':')[0]))
}

export function latestMetrics(metrics = []) {
  const latest = new Map()
  for (const metric of metrics) {
    if (!metric?.metric_name) continue
    const key = `${metric.metric_name}|${metricDimension(metric)}`
    const existing = latest.get(key)
    if (!existing || new Date(metric.timestamp) > new Date(existing.timestamp)) latest.set(key, metric)
  }
  return [...latest.values()].sort((left, right) => metricSeriesLabel(left).localeCompare(metricSeriesLabel(right), 'fr'))
}

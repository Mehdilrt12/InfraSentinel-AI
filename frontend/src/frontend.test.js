import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { MemoryRouter, Route, Routes } from 'react-router-dom'
import App from './App'
import { api, hasAccessToken, listData, resolveApiUrl, setAccessToken } from './api'
import { AuthProvider, isAdministrator, isManager } from './auth'
import { DataState, formatNumber, MetricValue, Severity, Status, Table } from './components'
import Dashboard from './pages/Dashboard'
import { Login, Register } from './pages/AuthPages'
import { realtimeRevisionFor } from './hooks'
import { getModelDisplayName, orderModelHistory } from './mlModelPresentation'
import {
  buildMetricChartGroups,
  formatAnomalySignal,
  formatBitRate,
  formatByteRate,
  formatBytes,
  formatCount,
  formatDuration,
  formatFrequency,
  formatLatency,
  formatMetricReading,
  formatPercent,
  formatRawValue,
  formatReadableNumber,
  formatReadableValue,
  formatRelativeTime,
  formatRiskLevel,
  formatTemperature,
  formatTimestamp,
  hasNumericValue,
  statusLabel,
} from './metricFormatting'
import * as Resources from './pages/Resources'
import { advanceEventSignal, advancePollSignal } from './realtime'

const storageValues = new Map()
globalThis.localStorage = {
  getItem: (key) => storageValues.get(key) ?? null,
  setItem: (key, value) => storageValues.set(key, String(value)),
  removeItem: (key) => storageValues.delete(key),
  clear: () => storageValues.clear(),
}

describe('API normalization', () => {
  it('accepts paginated DRF lists', () => expect(listData({ results: [{ id: 1 }] })).toEqual([{ id: 1 }]))
  it('accepts plain arrays', () => expect(listData([{ id: 2 }])).toEqual([{ id: 2 }]))
  it('returns an empty list for missing data', () => expect(listData(null)).toEqual([]))
})

describe('runtime URL defaults', () => {
  it('never embeds credentials in API URL', async () => { const { API_URL } = await import('./api'); expect(API_URL).not.toMatch(/@/) })
  it('uses the safe same-origin API fallback', () => expect(resolveApiUrl(undefined)).toBe('/api'))
})

describe('dashboard data states', () => {
  const render = (state) => renderToStaticMarkup(createElement(DataState, { state }, createElement('span', null, 'contenu')))
  it('renders loading', () => expect(render({ loading: true })).toContain('Chargement des données'))
  it('renders empty', () => expect(render({ loading: false, data: [], error: null })).toContain('Aucune donnée'))
  it('renders API or offline errors', () => expect(render({ loading: false, data: null, error: 'Vous êtes hors ligne.' })).toContain('Vous êtes hors ligne'))
  it('renders partial data warning and content', () => { const html = render({ loading: false, data: { id: 1 }, error: null, partial: true }); expect(html).toContain('données partielles'); expect(html).toContain('contenu') })
  it('renders successful content', () => expect(render({ loading: false, data: { id: 1 }, error: null, partial: false })).toContain('contenu'))
})

describe('secure browser API client', () => {
  it('keeps the access token in memory and adds it only to Authorization', async () => {
    localStorage.clear(); setAccessToken('access-secret')
    const handler = api.interceptors.request.handlers[0].fulfilled
    const config = await handler({ headers: {}, data: { metric: 'cpu' } })
    expect(config.headers.Authorization).toBe('Bearer access-secret')
    expect(JSON.stringify(config.data)).not.toContain('access-secret')
    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
    expect(hasAccessToken()).toBe(true)
  })

  it('leaves unauthenticated requests without Authorization', async () => {
    localStorage.clear(); setAccessToken(null)
    const handler = api.interceptors.request.handlers[0].fulfilled
    const config = await handler({ headers: {} })
    expect(config.headers.Authorization).toBeUndefined()
    expect(hasAccessToken()).toBe(false)
  })

  it('uses credentialed requests for HttpOnly refresh cookies', () => {
    expect(api.defaults.withCredentials).toBe(true)
  })
})

describe('visual RBAC helpers', () => {
  it('allows management only to supervisors, admins and platform superusers', () => {
    expect(isManager({ role: 'VIEWER' })).toBe(false)
    expect(isManager({ role: 'SUPERVISOR' })).toBe(true)
    expect(isManager({ is_superuser: true, role: 'VIEWER' })).toBe(true)
  })
  it('reserves user administration to admins', () => {
    expect(isAdministrator({ role: 'SUPERVISOR' })).toBe(false)
    expect(isAdministrator({ role: 'ADMIN' })).toBe(true)
  })
})

describe('monitoring UI primitives', () => {
  it('renders severity and status semantics', () => {
    expect(renderToStaticMarkup(createElement(Severity, { value: 'CRITICAL' }))).toContain('critical')
    expect(renderToStaticMarkup(createElement(Status, { value: 'OFFLINE' }))).toContain('offline')
  })

  it('renders table values, fallbacks and custom cells', () => {
    const html = renderToStaticMarkup(createElement(Table, {
      rows: [{ id: 1, hostname: 'host-1', value: null }],
      columns: [
        { key: 'hostname', label: 'Machine' },
        { key: 'value', label: 'Valeur' },
        { key: 'id', label: 'Custom', render: (value) => createElement('strong', null, `#${value}`) },
      ],
    }))
    expect(html).toContain('host-1'); expect(html).toContain('—'); expect(html).toContain('#1')
  })

  it('formats missing and numeric values for the French dashboard', () => {
    expect(formatNumber(null)).toBe('—')
    expect(formatNumber(1234.56, 1)).toMatch(/1[\s\u202f]234,6/)
  })

  it('formats generic metric values through the centralized semantic formatter', () => {
    const html = renderToStaticMarkup(createElement(MetricValue, { label: 'Stockage', value: 1024 ** 3, unit: 'bytes' }))
    expect(html).toContain('Stockage')
    expect(html).toContain('1 Go')
    expect(html).not.toContain('1073741824')
  })
})

describe('readable metric charts', () => {
  it('uses French numbers with at most one decimal', () => {
    expect(formatReadableNumber(1234.56)).toMatch(/1[\s\u202f]234,6/)
    expect(formatReadableNumber(12)).toBe('12')
    expect(formatReadableValue(59.399, 'Go')).toBe('59,4 Go')
  })

  it('formats raw tooltip readings with a human-sized unit', () => {
    expect(formatMetricReading({ metric_name: 'system.disk.io.read', metric_value: 88965.7286, unit: 'bytes/s', metadata: {} })).toMatchObject({ label: 'Lecture disque', unit: 'Ko/s', text: '86,9 Ko/s' })
    expect(formatMetricReading({ metric_name: 'system.network.latency', metric_value: 7.77869999, unit: 'ms', metadata: {} })).toMatchObject({ label: 'Latence réseau', unit: 'ms', text: '7,8 ms' })
    expect(formatMetricReading({ metric_name: 'system.gpu.utilization', metric_value: 0, unit: '%', metadata: {} })).toMatchObject({ label: 'GPU', unit: '%', text: '0 %' })
    expect(formatRawValue(11097.3187, 'bytes/s')).toMatchObject({ unit: 'Ko/s', text: '10,8 Ko/s' })
  })

  it('separates incompatible units and selects larger readable units', () => {
    const timestamp = '2026-08-27T22:05:00Z'
    const groups = buildMetricChartGroups([
      { timestamp, metric_name: 'system.cpu.utilization', metric_value: 14.54, unit: '%', metadata: {} },
      { timestamp, metric_name: 'system.disk.free', metric_value: 64 * 1024 ** 3, unit: 'bytes', metadata: { device: 'C:\\' } },
      { timestamp, metric_name: 'system.network.in', metric_value: 2.5 * 1024 ** 2, unit: 'bytes/s', metadata: {} },
      { timestamp, metric_name: 'system.uptime', metric_value: 3.5 * 3600, unit: 'seconds', metadata: {} },
    ])

    expect(groups.map((group) => group.unit)).toEqual(['%', 'Go', 'Mo/s', 'h'])
    expect(groups[1].data[0].series_0).toBe(64)
    expect(groups[1].series[0].label).toContain('C:\\')
    expect(groups[2].data[0].series_0).toBe(2.5)
    expect(groups[2].data[0].series_0_raw).toBe(2.5 * 1024 ** 2)
    expect(groups[3].data[0].series_0).toBe(3.5)
  })

  it('keeps separate disk series for separate volumes', () => {
    const timestamp = '2026-08-27T22:05:00Z'
    const [group] = buildMetricChartGroups([
      { timestamp, metric_name: 'system.disk.utilization', metric_value: 80, unit: '%', metadata: { device: 'C:\\' } },
      { timestamp, metric_name: 'system.disk.utilization', metric_value: 20, unit: '%', metadata: { device: 'D:\\' } },
    ])
    expect(group.series).toHaveLength(2)
    expect(Object.values(group.data[0])).toEqual(expect.arrayContaining([80, 20]))
  })
})

describe('targeted real-time refresh', () => {
  const initial = { revision: 0, eventTypes: [], eventRevisions: {}, pollRevision: 0 }

  it('invalidates only API resources subscribed to the received event', () => {
    const afterMetric = advanceEventSignal(initial, ['metric.update'])
    expect(realtimeRevisionFor(afterMetric.eventRevisions, afterMetric.pollRevision, ['metric.update'])).toBe(1)
    expect(realtimeRevisionFor(afterMetric.eventRevisions, afterMetric.pollRevision, ['alert.created'])).toBe(0)

    const afterAlert = advanceEventSignal(afterMetric, ['alert.created'])
    expect(realtimeRevisionFor(afterAlert.eventRevisions, afterAlert.pollRevision, ['metric.update'])).toBe(1)
    expect(realtimeRevisionFor(afterAlert.eventRevisions, afterAlert.pollRevision, ['alert.created'])).toBe(1)
  })

  it('keeps polling as a refresh fallback for every subscription', () => {
    const afterPoll = advancePollSignal(initial)
    expect(realtimeRevisionFor(afterPoll.eventRevisions, afterPoll.pollRevision, ['metric.update'])).toBe(1)
    expect(realtimeRevisionFor(afterPoll.eventRevisions, afterPoll.pollRevision, ['alert.created'])).toBe(1)
  })
})

describe('centralized enterprise unit formatting', () => {
  it('converts bytes through French binary units without meaningless precision', () => {
    expect(formatBytes(512)).toBe('512 o')
    expect(formatBytes(1536)).toBe('1,5 Ko')
    expect(formatBytes(1024 ** 2)).toBe('1 Mo')
    expect(formatBytes(1024 ** 3)).toBe('1 Go')
    expect(formatBytes(50 * 1024 ** 3)).toBe('50 Go')
    expect(formatBytes(1024 ** 4)).toBe('1 To')
    expect(formatBytes(2 * 1024 ** 5)).toBe('2 Po')
  })

  it('keeps byte rates and bit rates semantically distinct', () => {
    expect(formatByteRate(12.8 * 1024 ** 2)).toBe('12,8 Mo/s')
    expect(formatBitRate(2.4 * 1000 ** 2)).toBe('2,4 Mb/s')
    expect(formatRawValue(1, 'MB/s').text).toBe('976,6 Ko/s')
    expect(formatRawValue(1, 'Mb/s').text).toBe('1 Mb/s')
  })

  it('formats percentages only with an explicit fraction contract', () => {
    expect(formatPercent(0)).toBe('0 %')
    expect(formatPercent(43.729381)).toBe('43,7 %')
    expect(formatPercent(0.8734, { fraction: true })).toBe('87,3 %')
  })

  it('formats latency, uptime, temperature, frequency and counters by semantics', () => {
    expect(formatLatency(350)).toBe('350 ms')
    expect(formatLatency(1400)).toBe('1,4 s')
    expect(formatDuration(49)).toBe('49 s')
    expect(formatDuration(125)).toBe('2 min 5 s')
    expect(formatDuration(3900)).toBe('1 h 5 min')
    expect(formatDuration(187200)).toBe('2 j 4 h')
    expect(formatTemperature(72)).toBe('72 °C')
    expect(formatFrequency(2400, 'MHz')).toBe('2,4 GHz')
    expect(formatFrequency(800, 'MHz')).toBe('800 MHz')
    expect(formatCount(1000)).toMatch(/1[\s\u202f]000/)
  })

  it('never converts missing values into real zero measurements', () => {
    expect(hasNumericValue(null)).toBe(false)
    expect(hasNumericValue(undefined)).toBe(false)
    expect(hasNumericValue('')).toBe(false)
    expect(formatBytes(null)).toBe('—')
    expect(formatMetricReading({ metric_name: 'system.network.latency', metric_value: null, unit: 'ms' }).text).toBe('—')
    expect(buildMetricChartGroups([{ timestamp: '2026-08-28T00:00:00Z', metric_name: 'system.network.latency', metric_value: null, unit: 'ms' }])).toEqual([])
  })

  it('supports signed values only where the semantic formatter permits them', () => {
    expect(formatByteRate(-2048)).toBe('-2 Ko/s')
    expect(formatDuration(-1)).toBe('—')
  })

  it('formats exact and relative French timestamps', () => {
    const value = '2026-08-28T06:34:00Z'
    expect(formatTimestamp(value)).toMatch(/28\/08\/2026/)
    expect(formatRelativeTime(value, Date.parse('2026-08-28T06:38:00Z'))).toBe('Il y a 4 min')
    expect(formatRelativeTime(null)).toBe('Jamais')
  })

  it('localizes operational states and explains ML scores relative to their threshold', () => {
    expect(statusLabel('IN_PROGRESS')).toBe('En cours')
    expect(statusLabel('poweredOn')).toBe('En marche')
    expect(formatMetricReading({ metric_name: 'windows.service.state', metric_value: 0, unit: 'state', status: 'stopped', metadata: { service_name: 'Spooler' } })).toMatchObject({ label: 'Service Windows · Spooler', text: 'Arrêté' })
    expect(formatAnomalySignal(0.91, 0.75)).toMatchObject({ label: 'Au-dessus du seuil du modèle', tone: 'high' })
    expect(formatRiskLevel(82)).toEqual({ label: 'Critique', tone: 'critical' })
  })
})

describe('human-readable ML model presentation', () => {
  const technicalVersion = 'iforest-20260827T234946-0dbe1975'
  const activeModel = {
    id: 'model-6',
    version: technicalVersion,
    display_number: 6,
    algorithm: 'IsolationForest',
    active: true,
    status: 'READY',
    trained_at: '2026-08-28T00:49:46Z',
    parameters: { contamination: 0.02, n_estimators: 200 },
    dataset: { rows: 35, synthetic: false },
    evaluation_metrics: { validation_anomaly_rate: 0, method: 'chronological_holdout', ground_truth_available: false },
    features: ['system.cpu.utilization'],
    decision_threshold: 0.42,
  }

  it('uses the persistent display number without changing the technical ID', () => {
    expect(getModelDisplayName(activeModel)).toBe('Isolation Forest — Modèle 6')
    expect(activeModel.version).toBe(technicalVersion)
    expect(getModelDisplayName({ algorithm: 'IsolationForest' })).toBe('Isolation Forest')
  })

  it('keeps history numbering and order stable across refreshed arrays', () => {
    const models = [
      { id: '4', display_number: 4, version: 'technical-4' },
      activeModel,
      { id: '5', display_number: 5, version: 'technical-5' },
    ]
    const refreshed = [models[2], models[0], models[1]]
    expect(orderModelHistory(models).map((model) => model.display_number)).toEqual([6, 5, 4])
    expect(orderModelHistory(refreshed).map((model) => model.display_number)).toEqual([6, 5, 4])
    expect(models.map((model) => model.display_number)).toEqual([4, 6, 5])
  })

  it('renders the human title and active badge while keeping the raw ID in scientific details', () => {
    const html = renderToStaticMarkup(createElement(Resources.MLModelCard, { model: activeModel }))
    expect(html).toContain('Isolation Forest — Modèle 6')
    expect(html).toContain('Modèle actif')
    expect(html).toContain('Prêt')
    expect(html).toContain('Détails scientifiques')
    expect(html).toContain('ID technique')
    expect(html).toContain(technicalVersion)
    expect(html).not.toContain(`<h2>${technicalVersion}</h2>`)
  })

  it('does not label an inactive history entry as active', () => {
    const html = renderToStaticMarkup(createElement(Resources.MLModelCard, { model: { ...activeModel, id: 'model-5', display_number: 5, version: 'technical-5', active: false } }))
    expect(html).toContain('Isolation Forest — Modèle 5')
    expect(html).toContain('Version historique')
    expect(html).not.toContain('Modèle actif')
  })
})

describe('phase 14 route components', () => {
  it('keeps the application and every critical resource page importable', () => {
    expect(typeof App).toBe('function')
    for (const name of ['Machines', 'MachineDetail', 'Agents', 'Alerts', 'Anomalies', 'VMware', 'VMwareDetail', 'HyperV', 'HyperVDetail', 'ML', 'Users', 'SettingsPage', 'Audit']) {
      expect(typeof Resources[name], name).toBe('function')
    }
  })

  it('renders audit search, filters and immutable event table controls', () => {
    const html = renderToStaticMarkup(createElement(Resources.Audit))
    expect(html).toContain('Recherche audit')
    expect(html).toContain('Type de cible')
    expect(html).toContain('Adresse IP')
    expect(html).toContain('MODEL_TRAINED')
  })

  it('server-renders every critical page without an immediate component crash', () => {
    const pages = [
      ['/login', '/login', createElement(Login), 'Connexion'],
      ['/register', '/register', createElement(Register), null],
      ['/dashboard', '/dashboard', createElement(Dashboard), 'Vue globale'],
      ['/machines', '/machines', createElement(Resources.Machines), 'Machines'],
      ['/machines/:id', '/machines/test-machine', createElement(Resources.MachineDetail), 'Détail machine'],
      ['/agents', '/agents', createElement(Resources.Agents), 'Agents Windows'],
      ['/alerts', '/alerts', createElement(Resources.Alerts), 'Alertes centralisées'],
      ['/anomalies', '/anomalies', createElement(Resources.Anomalies), 'Anomalies'],
      ['/vmware', '/vmware', createElement(Resources.VMware), 'VMware'],
      ['/vmware/:id', '/vmware/test-asset', createElement(Resources.VMwareDetail), 'VMware'],
      ['/hyperv', '/hyperv', createElement(Resources.HyperV), 'Microsoft Hyper-V'],
      ['/hyperv/:id', '/hyperv/test-asset', createElement(Resources.HyperVDetail), 'Hyper-V'],
      ['/ml', '/ml', createElement(Resources.ML), 'Machine Learning'],
      ['/users', '/users', createElement(Resources.Users), 'Utilisateurs'],
      ['/settings', '/settings', createElement(Resources.SettingsPage), 'Configuration'],
      ['/audit', '/audit', createElement(Resources.Audit), 'Journal d’audit'],
    ]

    pages.forEach(([pattern, entry, element, expected]) => {
      const html = renderToStaticMarkup(createElement(AuthProvider, null,
        createElement(MemoryRouter, { initialEntries: [entry] },
          createElement(Routes, null, createElement(Route, { path: pattern, element })),
        ),
      ))
      if (expected) expect(html, entry).toContain(expected)
    })
  })
})

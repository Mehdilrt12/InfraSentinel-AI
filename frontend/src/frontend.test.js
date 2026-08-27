import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import App from './App'
import { api, hasAccessToken, listData, resolveApiUrl, setAccessToken } from './api'
import { isAdministrator, isManager } from './auth'
import { DataState, formatNumber, Severity, Status, Table } from './components'
import * as Resources from './pages/Resources'

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
})

import { describe, expect, it } from 'vitest'
import { createElement } from 'react'
import { renderToStaticMarkup } from 'react-dom/server'
import { listData } from './api'
import { DataState } from './components'

describe('API normalization', () => {
  it('accepts paginated DRF lists', () => expect(listData({ results: [{ id: 1 }] })).toEqual([{ id: 1 }]))
  it('accepts plain arrays', () => expect(listData([{ id: 2 }])).toEqual([{ id: 2 }]))
  it('returns an empty list for missing data', () => expect(listData(null)).toEqual([]))
})

describe('runtime URL defaults', () => {
  it('never embeds credentials in API URL', async () => { const { API_URL } = await import('./api'); expect(API_URL).not.toMatch(/@/) })
  it('uses an HTTP(S) API URL', async () => { const { API_URL } = await import('./api'); expect(API_URL).toMatch(/^https?:\/\//) })
})

describe('dashboard data states', () => {
  const render = (state) => renderToStaticMarkup(createElement(DataState, { state }, createElement('span', null, 'contenu')))
  it('renders loading', () => expect(render({ loading: true })).toContain('Chargement des données'))
  it('renders empty', () => expect(render({ loading: false, data: [], error: null })).toContain('Aucune donnée'))
  it('renders API or offline errors', () => expect(render({ loading: false, data: null, error: 'Vous êtes hors ligne.' })).toContain('Vous êtes hors ligne'))
  it('renders partial data warning and content', () => { const html = render({ loading: false, data: { id: 1 }, error: null, partial: true }); expect(html).toContain('données partielles'); expect(html).toContain('contenu') })
  it('renders successful content', () => expect(render({ loading: false, data: { id: 1 }, error: null, partial: false })).toContain('contenu'))
})

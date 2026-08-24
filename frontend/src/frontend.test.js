import { describe, expect, it } from 'vitest'
import { listData } from './api'

describe('API normalization', () => {
  it('accepts paginated DRF lists', () => expect(listData({ results: [{ id: 1 }] })).toEqual([{ id: 1 }]))
  it('accepts plain arrays', () => expect(listData([{ id: 2 }])).toEqual([{ id: 2 }]))
  it('returns an empty list for missing data', () => expect(listData(null)).toEqual([]))
})

describe('runtime URL defaults', () => {
  it('never embeds credentials in API URL', async () => { const { API_URL } = await import('./api'); expect(API_URL).not.toMatch(/@/) })
  it('uses an HTTP(S) API URL', async () => { const { API_URL } = await import('./api'); expect(API_URL).toMatch(/^https?:\/\//) })
})


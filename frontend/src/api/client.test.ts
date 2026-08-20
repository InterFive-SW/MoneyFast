import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'

interface MockResponseOptions {
  ok?: boolean
  status?: number
  statusText?: string
  json?: () => Promise<unknown>
}

function mockFetch(options: MockResponseOptions = {}) {
  const fetchMock = vi.fn().mockResolvedValue({
    ok: options.ok ?? true,
    status: options.status ?? 200,
    statusText: options.statusText ?? 'OK',
    json: options.json ?? (async () => ({})),
  })
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

function mockFetchRejects(error: Error) {
  const fetchMock = vi.fn().mockRejectedValue(error)
  vi.stubGlobal('fetch', fetchMock)
  return fetchMock
}

beforeEach(() => {
  localStorage.clear()
  vi.spyOn(console, 'error').mockImplementation(() => {})
})

afterEach(() => {
  vi.unstubAllGlobals()
  vi.restoreAllMocks()
})

describe('apiClient — özel request() (GET yardımcı metodları)', () => {
  it('access_token yoksa Authorization başlığı eklenmez', async () => {
    const fetchMock = mockFetch({ json: async () => [] })
    await apiClient.getPositions()
    const headers = fetchMock.mock.calls[0][1].headers
    expect(headers.Authorization).toBeUndefined()
  })

  it('access_token varsa Authorization: Bearer başlığı eklenir', async () => {
    localStorage.setItem('access_token', 'test-token-123')
    const fetchMock = mockFetch({ json: async () => [] })
    await apiClient.getOrders()
    const headers = fetchMock.mock.calls[0][1].headers
    expect(headers.Authorization).toBe('Bearer test-token-123')
  })

  it('response.ok false ise durum koduyla birlikte hata fırlatır', async () => {
    mockFetch({ ok: false, status: 500, statusText: 'Internal Server Error' })
    await expect(apiClient.getPositions()).rejects.toThrow('API Hatası: 500 Internal Server Error')
  })

  it('fetch ağ hatası fırlatırsa hatayı loglayıp yeniden fırlatır', async () => {
    mockFetchRejects(new Error('network down'))
    await expect(apiClient.getPositions()).rejects.toThrow('network down')
    expect(console.error).toHaveBeenCalled()
  })

  it('tüm yatırım/piyasa GET yardımcı metodları doğru endpoint\'e istek atar', async () => {
    const fetchMock = mockFetch({ json: async () => ({}) })

    await apiClient.getPortfolioSummary()
    await apiClient.getPortfolioChart()
    await apiClient.getPositions()
    await apiClient.getOrders()
    await apiClient.getAssetAllocation()
    await apiClient.getWatchlist()
    await apiClient.getTopMovers()
    await apiClient.getDividends()
    await apiClient.getSectorAllocation()
    await apiClient.getHeatmap()
    await apiClient.getMarketTickers()
    await apiClient.getMarketNews()

    expect(fetchMock).toHaveBeenCalledTimes(12)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/investment/portfolio/summary')
    expect(fetchMock.mock.calls[10][0]).toBe('/api/market/tickers')
  })
})

describe('apiClient.get() — genel GET metodu', () => {
  it('url zaten "/api" ile başlıyorsa çift önek oluşmaz', async () => {
    const fetchMock = mockFetch({ json: async () => ({}) })
    await apiClient.get('/api/investment/positions')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/investment/positions')
  })

  it('url "/api" ile başlamıyorsa baseUrl otomatik eklenir', async () => {
    const fetchMock = mockFetch({ json: async () => ({}) })
    await apiClient.get('/investment/positions')
    expect(fetchMock.mock.calls[0][0]).toBe('/api/investment/positions')
  })

  it('url "http" ile başlıyorsa baseUrl hiç eklenmez, olduğu gibi kullanılır', async () => {
    const fetchMock = mockFetch({ json: async () => ({}) })
    await apiClient.get('https://example.com/external')
    expect(fetchMock.mock.calls[0][0]).toBe('https://example.com/external')
  })

  it('response.ok false ise hata fırlatır', async () => {
    mockFetch({ ok: false, status: 404, statusText: 'Not Found' })
    await expect(apiClient.get('/investment/positions')).rejects.toThrow('API Hatası: 404 Not Found')
  })

  it('fetch ağ hatası fırlatırsa hatayı loglayıp yeniden fırlatır', async () => {
    mockFetchRejects(new Error('network down'))
    await expect(apiClient.get('/investment/positions')).rejects.toThrow('network down')
    expect(console.error).toHaveBeenCalled()
  })

  it('access_token varsa Authorization başlığı eklenir', async () => {
    localStorage.setItem('access_token', 'abc')
    const fetchMock = mockFetch({ json: async () => ({}) })
    await apiClient.get('/investment/positions')
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer abc')
  })
})

describe('apiClient.post() — genel POST metodu', () => {
  it('veri verilirse JSON body olarak gönderilir', async () => {
    const fetchMock = mockFetch({ json: async () => ({ message: 'ok' }) })
    await apiClient.post('/investment/orders/confirm', { symbol: 'THYAO', quantity: 5 })
    const [, init] = fetchMock.mock.calls[0]
    expect(init.method).toBe('POST')
    expect(init.body).toBe(JSON.stringify({ symbol: 'THYAO', quantity: 5 }))
  })

  it('veri verilmezse body undefined olur', async () => {
    const fetchMock = mockFetch({ json: async () => ({}) })
    await apiClient.post('/investment/orders/confirm')
    expect(fetchMock.mock.calls[0][1].body).toBeUndefined()
  })

  it('confirmOrder yardımcı metodu post() üzerinden doğru endpoint\'e gider', async () => {
    const fetchMock = mockFetch({ json: async () => ({ message: 'ok' }) })
    await apiClient.confirmOrder({ symbol: 'THYAO', quantity: 1, type: 'Alış' } as any)
    expect(fetchMock.mock.calls[0][0]).toBe('/api/investment/orders/confirm')
  })

  it('url "http" ile başlıyorsa baseUrl eklenmez', async () => {
    const fetchMock = mockFetch({ json: async () => ({}) })
    await apiClient.post('https://example.com/external', { a: 1 })
    expect(fetchMock.mock.calls[0][0]).toBe('https://example.com/external')
  })

  it('url zaten "/api" ile başlıyorsa çift önek oluşmaz', async () => {
    const fetchMock = mockFetch({ json: async () => ({}) })
    await apiClient.post('/api/investment/orders/confirm', { a: 1 })
    expect(fetchMock.mock.calls[0][0]).toBe('/api/investment/orders/confirm')
  })

  it('response.ok false ise hata fırlatır', async () => {
    mockFetch({ ok: false, status: 400, statusText: 'Bad Request' })
    await expect(apiClient.post('/investment/orders/confirm', {})).rejects.toThrow('API Hatası: 400 Bad Request')
  })

  it('fetch ağ hatası fırlatırsa hatayı loglayıp yeniden fırlatır', async () => {
    mockFetchRejects(new Error('network down'))
    await expect(apiClient.post('/investment/orders/confirm', {})).rejects.toThrow('network down')
    expect(console.error).toHaveBeenCalled()
  })

  it('access_token varsa Authorization başlığı eklenir', async () => {
    localStorage.setItem('access_token', 'xyz')
    const fetchMock = mockFetch({ json: async () => ({}) })
    await apiClient.post('/investment/orders/confirm', {})
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer xyz')
  })
})

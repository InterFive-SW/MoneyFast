/**
 * The HTTP client.
 *
 * Worth testing because the bugs it has actually had were silent: a query
 * parameter named `top_k` when the backend reads `limit`, which FastAPI
 * ignored — so every screen quietly received the default 20 rows instead of
 * the 200 it asked for, and nothing failed.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from './client'

function mockFetch(body: unknown = {}, ok = true) {
  const fn = vi.fn().mockResolvedValue({
    ok,
    status: ok ? 200 : 500,
    json: async () => body,
    text: async () => JSON.stringify(body),
  })
  vi.stubGlobal('fetch', fn)
  return fn
}

/** The URL of the most recent call. */
function calledUrl(fn: ReturnType<typeof vi.fn>): string {
  return String(fn.mock.calls[0][0])
}

describe('getInstruments', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('sends `limit`, which is the parameter the backend actually reads', () => {
    const fetchMock = mockFetch({ instruments: [] })
    apiClient.getInstruments({ limit: 200 })
    expect(calledUrl(fetchMock)).toContain('limit=200')
    expect(calledUrl(fetchMock)).not.toContain('top_k')
  })

  it('repeats the key for each symbol, which is how FastAPI reads a list', () => {
    const fetchMock = mockFetch({ instruments: [] })
    apiClient.getInstruments({ symbols: ['THYAO', 'ASELS'] })
    const url = calledUrl(fetchMock)
    expect(url).toContain('symbols=THYAO')
    expect(url).toContain('symbols=ASELS')
  })

  it('passes the screening filters through', () => {
    const fetchMock = mockFetch({ instruments: [] })
    apiClient.getInstruments({ sector: 'Industrials', max_pe: 10, min_pe: 2, max_pb: 3, sort_by: 'pe_ratio' })
    const url = calledUrl(fetchMock)
    expect(url).toContain('sector=Industrials')
    expect(url).toContain('max_pe=10')
    expect(url).toContain('min_pe=2')
    expect(url).toContain('max_pb=3')
    expect(url).toContain('sort_by=pe_ratio')
  })

  it('omits the query string entirely when nothing was asked for', () => {
    const fetchMock = mockFetch({ instruments: [] })
    apiClient.getInstruments()
    expect(calledUrl(fetchMock)).not.toContain('?')
  })

  it('does not send a filter that was not set', () => {
    const fetchMock = mockFetch({ instruments: [] })
    apiClient.getInstruments({ limit: 5 })
    expect(calledUrl(fetchMock)).not.toContain('sector')
  })
})

describe('authentication', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('attaches the bearer token when there is a session', async () => {
    localStorage.setItem('access_token', 'abc123')
    const fetchMock = mockFetch([])
    await apiClient.getPositions()
    const headers = fetchMock.mock.calls[0][1].headers
    expect(headers.Authorization).toBe('Bearer abc123')
  })

  it('sends no Authorization header when signed out', async () => {
    const fetchMock = mockFetch([])
    await apiClient.getPositions()
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined()
  })
})

describe('endpoint paths', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it.each([
    ['getPositions', '/api/investment/positions'],
    ['getPortfolioSummary', '/api/investment/portfolio/summary'],
    ['getOrders', '/api/investment/orders'],
    ['getWatchlist', '/api/investment/watchlist'],
    ['getTopMovers', '/api/investment/top-movers'],
    ['getDividends', '/api/investment/dividends'],
    ['getAssetAllocation', '/api/investment/asset-allocation'],
    ['getSectorAllocation', '/api/investment/sector-allocation'],
    ['getHeatmap', '/api/investment/heatmap'],
    ['getPortfolioChart', '/api/investment/portfolio/chart'],
    ['getMarketTickers', '/api/market/tickers'],
    ['getMarketNews', '/api/market/news'],
    ['getPortfolioAnalysis', '/api/analytics/portfolio'],
    ['getCurrentUser', '/api/auth/me'],
  ])('%s calls %s', (method, path) => {
    const fetchMock = mockFetch({})
    ;(apiClient as never as Record<string, () => void>)[method]()
    expect(calledUrl(fetchMock)).toBe(path)
  })

  it('encodes a symbol into the candles path', () => {
    const fetchMock = mockFetch({})
    apiClient.getCandles('BRK B', 30)
    expect(calledUrl(fetchMock)).toContain('symbol=BRK%20B')
    expect(calledUrl(fetchMock)).toContain('limit=30')
  })

  it('encodes a proposal id rather than interpolating it raw', () => {
    const fetchMock = mockFetch({})
    apiClient.confirmProposal('PROP/1')
    expect(calledUrl(fetchMock)).toContain('PROP%2F1')
  })
})

describe('failures', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('rejects on a non-ok response instead of returning an empty body', async () => {
    // Silently resolving would render an error as "no holdings".
    mockFetch({ detail: 'boom' }, false)
    await expect(apiClient.getPositions()).rejects.toBeDefined()
  })
})


describe('the generic get/post escape hatches', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('strips a duplicate /api prefix rather than requesting /api/api/...', () => {
    const fetchMock = mockFetch({})
    apiClient.get('/api/market/tickers')
    expect(calledUrl(fetchMock)).toBe('/api/market/tickers')
  })

  it('leaves a relative path alone', () => {
    const fetchMock = mockFetch({})
    apiClient.get('/market/tickers')
    expect(calledUrl(fetchMock)).toBe('/api/market/tickers')
  })

  it('passes an absolute URL through untouched', () => {
    const fetchMock = mockFetch({})
    apiClient.get('https://example.test/thing')
    expect(calledUrl(fetchMock)).toBe('https://example.test/thing')
  })

  it('sends a bearer token on a generic GET', async () => {
    localStorage.setItem('access_token', 'abc')
    const fetchMock = mockFetch({})
    await apiClient.get('/x')
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer abc')
  })

  it('omits the token on a generic GET when signed out', async () => {
    const fetchMock = mockFetch({})
    await apiClient.get('/x')
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined()
  })

  it('rejects a failed generic GET', async () => {
    mockFetch({}, false)
    vi.spyOn(console, 'error').mockImplementation(() => {})
    await expect(apiClient.get('/x')).rejects.toThrow('API Hatası')
  })

  it('serialises a POST body', async () => {
    const fetchMock = mockFetch({})
    await apiClient.post('/x', { a: 1 })
    expect(fetchMock.mock.calls[0][1].body).toBe(JSON.stringify({ a: 1 }))
  })

  it('sends no body when there is nothing to send', async () => {
    const fetchMock = mockFetch({})
    await apiClient.post('/x')
    expect(fetchMock.mock.calls[0][1].body).toBeUndefined()
  })

  it('sends a bearer token on a generic POST', async () => {
    localStorage.setItem('access_token', 'abc')
    const fetchMock = mockFetch({})
    await apiClient.post('/x', {})
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBe('Bearer abc')
  })

  it('omits the token on a generic POST when signed out', async () => {
    const fetchMock = mockFetch({})
    await apiClient.post('/x', {})
    expect(fetchMock.mock.calls[0][1].headers.Authorization).toBeUndefined()
  })

  it('rejects a failed POST rather than resolving with nothing', async () => {
    mockFetch({}, false)
    vi.spyOn(console, 'error').mockImplementation(() => {})
    await expect(apiClient.post('/x', {})).rejects.toThrow('API Hatası')
  })
})

describe('the trading endpoints', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('stages a transaction against the real staging path', async () => {
    const fetchMock = mockFetch({})
    await apiClient.stageTransaction({ user_id: 'u', transaction_type: 'BUY' } as never)
    expect(calledUrl(fetchMock)).toBe('/api/investment/transactions/stage')
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
  })
})


describe('remaining query and URL branches', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('passes the market filter through', () => {
    const fetchMock = mockFetch({ instruments: [] })
    apiClient.getInstruments({ market: 'BIST' })
    expect(calledUrl(fetchMock)).toContain('market=BIST')
  })

  it('strips a duplicate /api prefix on a POST too', async () => {
    const fetchMock = mockFetch({})
    await apiClient.post('/api/auth/login', {})
    expect(calledUrl(fetchMock)).toBe('/api/auth/login')
  })

  it('passes an absolute POST URL through untouched', async () => {
    const fetchMock = mockFetch({})
    await apiClient.post('https://example.test/hook', {})
    expect(calledUrl(fetchMock)).toBe('https://example.test/hook')
  })
})

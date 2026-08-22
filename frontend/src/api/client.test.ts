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


describe('the banking endpoints', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it.each([
    ['getBankAccounts', '/api/banking/accounts'],
    ['getSavingsGoals', '/api/banking/savings-goals'],
  ])('%s calls %s', (method, path) => {
    const fetchMock = mockFetch([])
    ;(apiClient as never as Record<string, () => void>)[method]()
    expect(calledUrl(fetchMock)).toBe(path)
  })

  it('encodes the account number into the statement path', () => {
    const fetchMock = mockFetch({})
    apiClient.getStatement('TR 001', 5)
    expect(calledUrl(fetchMock)).toContain('TR%20001')
    expect(calledUrl(fetchMock)).toContain('limit=5')
  })

  it('passes the spending window', () => {
    const fetchMock = mockFetch({})
    apiClient.getSpending(90)
    expect(calledUrl(fetchMock)).toContain('days=90')
  })

  it('defaults the spending window to a month', () => {
    const fetchMock = mockFetch({})
    apiClient.getSpending()
    expect(calledUrl(fetchMock)).toContain('days=30')
  })

  it('passes the balance-history limit', () => {
    const fetchMock = mockFetch({})
    apiClient.getBalanceHistory(60)
    expect(calledUrl(fetchMock)).toContain('limit=60')
  })

  it('defaults the statement limit', () => {
    const fetchMock = mockFetch({})
    apiClient.getStatement('1000000000001')
    expect(calledUrl(fetchMock)).toContain('limit=20')
  })
})

// ==========================================================================
// Session renewal
//
// There was no 401 handling at all. An access token lives 30 minutes, so a
// session did not end -- it silently became anonymous. The panel endpoints do
// not require a token, so nothing looked broken, while the chat went on
// staging transaction proposals owned by "anonymous" that could never be
// confirmed.
// ==========================================================================
describe('watchlist', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('adds by symbol', () => {
    const fetchMock = mockFetch({ status: 'added' })
    apiClient.addToWatchlist('THYAO')
    expect(calledUrl(fetchMock)).toContain('/investment/watchlist/THYAO')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('POST')
  })

  it('removes by symbol with DELETE', () => {
    const fetchMock = mockFetch({ status: 'removed' })
    apiClient.removeFromWatchlist('THYAO')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('DELETE')
  })

  it('encodes the symbol into the path', () => {
    const fetchMock = mockFetch({})
    apiClient.addToWatchlist('BRK B')
    expect(calledUrl(fetchMock)).toContain('BRK%20B')
  })
})

describe('getRiskProfile', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('reads the user-scoped profile endpoint', () => {
    const fetchMock = mockFetch({ score: 42 })
    apiClient.getRiskProfile()
    // Not /risk/calculate: that one is the MCP contract and takes positions in
    // the body, which a client could rewrite to render someone else's risk.
    expect(calledUrl(fetchMock)).toContain('/api/risk/profile')
  })
})

describe('401 handling', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => {
    vi.unstubAllGlobals()
    vi.restoreAllMocks()
  })

  /** First call 401s, the refresh succeeds, the retry returns `body`. */
  function mockRefreshFlow(body: unknown) {
    let call = 0
    const fn = vi.fn(async (url: string, _init?: RequestInit) => {
      call += 1
      if (String(url).includes('/auth/refresh')) {
        return { ok: true, status: 200, json: async () => ({ access_token: 'fresh' }) }
      }
      if (call === 1) return { ok: false, status: 401, json: async () => ({}) }
      return { ok: true, status: 200, json: async () => body }
    })
    vi.stubGlobal('fetch', fn)
    return fn
  }

  it('refreshes once and retries the original request', async () => {
    localStorage.setItem('access_token', 'stale')
    localStorage.setItem('refresh_token', 'a-refresh-token')
    const fetchMock = mockRefreshFlow([{ symbol: 'ASELS' }])

    const result = await apiClient.getPositions()

    expect(result).toEqual([{ symbol: 'ASELS' }])
    expect(localStorage.getItem('access_token')).toBe('fresh')
    const urls = fetchMock.mock.calls.map((c) => String(c[0]))
    expect(urls.filter((u) => u.includes('/auth/refresh'))).toHaveLength(1)
  })

  it('sends the renewed token on the retry, not the stale one', async () => {
    localStorage.setItem('access_token', 'stale')
    localStorage.setItem('refresh_token', 'a-refresh-token')
    const fetchMock = mockRefreshFlow([])

    await apiClient.getPositions()

    const last = fetchMock.mock.calls[fetchMock.mock.calls.length - 1][1] as RequestInit
    expect((last.headers as Record<string, string>).Authorization).toBe('Bearer fresh')
  })

  it('clears the session when there is nothing to refresh with', async () => {
    localStorage.setItem('access_token', 'stale')
    const fn = vi.fn(async (_url?: string, _init?: RequestInit) => ({ ok: false, status: 401, json: async () => ({}) }))
    vi.stubGlobal('fetch', fn)
    const assign = vi.fn()
    vi.stubGlobal('location', { pathname: '/dashboard', assign } as never)

    await expect(apiClient.getPositions()).rejects.toThrow()
    expect(localStorage.getItem('access_token')).toBeNull()
  })

  it('does not try to refresh a failed login', async () => {
    localStorage.setItem('refresh_token', 'a-refresh-token')
    const fn = vi.fn(async (_url?: string, _init?: RequestInit) => ({ ok: false, status: 401, json: async () => ({}) }))
    vi.stubGlobal('fetch', fn)

    await expect(apiClient.post('/api/auth/login', {})).rejects.toThrow()

    const urls = fn.mock.calls.map((c) => String(c[0]))
    expect(urls.filter((u) => u.includes('/auth/refresh'))).toHaveLength(0)
  })

  it('a dead refresh token ends the session rather than looping', async () => {
    localStorage.setItem('access_token', 'stale')
    localStorage.setItem('refresh_token', 'expired')
    const fn = vi.fn(async (url: string, _init?: RequestInit) =>
      String(url).includes('/auth/refresh')
        ? { ok: false, status: 401, json: async () => ({}) }
        : { ok: false, status: 401, json: async () => ({}) },
    )
    vi.stubGlobal('fetch', fn)
    vi.stubGlobal('location', { pathname: '/dashboard', assign: vi.fn() } as never)

    await expect(apiClient.getPositions()).rejects.toThrow()
    expect(localStorage.getItem('refresh_token')).toBeNull()
  })

  it('does not redirect when the user is already on the login page', async () => {
    localStorage.setItem('access_token', 'stale')
    const assign = vi.fn()
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 401, json: async () => ({}) })))
    vi.stubGlobal('location', { pathname: '/login', assign } as never)

    await expect(apiClient.getPositions()).rejects.toThrow()
    expect(assign).not.toHaveBeenCalled()
  })

  it('concurrent 401s share one refresh', async () => {
    // A page load fires ten requests at once. If each ran its own refresh the
    // calls would race and most of the work would be wasted, so the refresh
    // is single-flight. The gate is held open here to make the overlap real
    // rather than a timing accident.
    localStorage.setItem('access_token', 'stale')
    localStorage.setItem('refresh_token', 'a-refresh-token')

    let release: () => void = () => {}
    const gate = new Promise<void>((resolve) => { release = resolve })
    const seen: string[] = []
    let refreshed = false

    vi.stubGlobal('fetch', vi.fn(async (url: string, _init?: RequestInit) => {
      const target = String(url)
      seen.push(target)
      if (target.includes('/auth/refresh')) {
        await gate
        refreshed = true
        return { ok: true, status: 200, json: async () => ({ access_token: 'fresh' }) }
      }
      if (!refreshed) return { ok: false, status: 401, json: async () => ({}) }
      return { ok: true, status: 200, json: async () => [] }
    }))

    const both = Promise.all([apiClient.getPositions(), apiClient.getOrders()])
    // Both first attempts have 401'd and both are now waiting on the refresh.
    await Promise.resolve()
    await Promise.resolve()
    release()
    await both

    expect(seen.filter((u) => u.includes('/auth/refresh'))).toHaveLength(1)
  })
})

// ==========================================================================
// streamChat
// ==========================================================================
describe('streamChat', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  /** A body that delivers `chunks` as separate network reads. */
  function streamOf(chunks: string[], ok = true) {
    const encoder = new TextEncoder()
    let i = 0
    const body = {
      getReader: () => ({
        read: async () =>
          i < chunks.length
            ? { done: false, value: encoder.encode(chunks[i++]) }
            : { done: true, value: undefined },
      }),
    }
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok, status: ok ? 200 : 500, body })))
  }

  it('reports each stage and then the finished answer', async () => {
    streamOf([
      'event: stage\ndata: {"stage":"Talebiniz sınıflandırılıyor..."}\n\n',
      'event: stage\ndata: {"stage":"Yanıt yazılıyor..."}\n\n',
      'event: done\ndata: {"final_output":"Merhaba"}\n\n',
    ])
    const stages: string[] = []
    let answer: any = null

    const ok = await apiClient.streamChat(
      { user_message: 'selam' },
      { onStage: (s) => stages.push(s), onDone: (p) => { answer = p } },
    )

    expect(ok).toBe(true)
    expect(stages).toEqual(['Talebiniz sınıflandırılıyor...', 'Yanıt yazılıyor...'])
    expect(answer.final_output).toBe('Merhaba')
  })

  it('reassembles an event split across two reads', async () => {
    // SSE frames do not respect network chunk boundaries; a naive parser
    // drops the half-delivered event and the answer never arrives.
    streamOf(['event: done\ndata: {"final_ou', 'tput":"Bölünmüş"}\n\n'])
    let answer: any = null

    await apiClient.streamChat({}, { onDone: (p) => { answer = p } })

    expect(answer.final_output).toBe('Bölünmüş')
  })

  it('returns false when the stream cannot be opened, so the caller falls back', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: false, status: 503, body: null })))
    expect(await apiClient.streamChat({}, {})).toBe(false)
  })

  it('returns false when fetch itself throws', async () => {
    vi.stubGlobal('fetch', vi.fn(async () => { throw new Error('offline') }))
    expect(await apiClient.streamChat({}, {})).toBe(false)
  })

  it('stops on an in-band error event', async () => {
    // The response is already 200 by then, so a failure cannot be an HTTP code.
    streamOf(['event: error\ndata: {"error":"groq exploded"}\n\n'])
    let answer: any = null
    const ok = await apiClient.streamChat({}, { onDone: (p) => { answer = p } })
    expect(ok).toBe(false)
    expect(answer).toBeNull()
  })

  it('ignores a null payload', async () => {
    streamOf(['event: ping\ndata: null\n\n', 'event: done\ndata: {"final_output":"Tamam"}\n\n'])
    let answer: any = null
    await apiClient.streamChat({}, { onDone: (p) => { answer = p } })
    expect(answer.final_output).toBe('Tamam')
  })

  it('works with no handlers supplied', async () => {
    streamOf(['event: stage\ndata: {"stage":"..."}\n\n',
              'event: done\ndata: {"final_output":"Tamam"}\n\n'])
    expect(await apiClient.streamChat({}, {})).toBe(true)
  })

  it('ignores malformed frames rather than aborting the turn', async () => {
    streamOf([
      'event: stage\ndata: not-json\n\n',
      ': keep-alive comment\n\n',
      'event: done\ndata: {"final_output":"Tamam"}\n\n',
    ])
    let answer: any = null
    await apiClient.streamChat({}, { onDone: (p) => { answer = p } })
    expect(answer.final_output).toBe('Tamam')
  })
})

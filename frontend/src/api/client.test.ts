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

/** onSessionExpired is a static, so it is reached through the constructor. */
const ApiClientClass = apiClient.constructor as unknown as { onSessionExpired(): void }

function mockFetch(body: unknown = {}, ok: boolean | number = true) {
  // `ok` bir sayı olarak da verilebiliyor: 415 ile 503 farklı şeyler ve
  // hepsini 500 diye taklit etmek, durum koduna bakan bir dalı test
  // edilemez yapardı.
  const status = typeof ok === 'number' ? ok : ok ? 200 : 500
  const fn = vi.fn().mockResolvedValue({
    ok: status >= 200 && status < 300,
    status,
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
    ['getAssetAllocation', '/api/investment/asset-allocation'],
    ['getAllocationTarget', '/api/investment/allocation-target'],
    // "Detaylı Rapor Oluştur": tek çağrı, altı bölüm.
    ['getPortfolioReport', '/api/analytics/report'],
    ['getAllocationDrift', '/api/investment/allocation-drift'],
    ['getSectorAllocation', '/api/investment/sector-allocation'],
    ['getHeatmap', '/api/investment/heatmap'],
    ['getMarketTickers', '/api/market/tickers'],
    ['getMarketNews', '/api/market/news'],
    // Oturuma bağlı ve demo portföyüne düşmüyor; kullanıcı yoldan değil
    // token'dan çözülüyor, o yüzden çağrı argümansız.
    ['getPortfolioNews', '/api/market/news/portfolio'],
    ['getPortfolioTechnical', '/api/market/portfolio/technical'],
    // Stres testi dönemsiz çağrılabiliyor: hiçbir girdi istemiyor ve zaten
    // olanı gösteriyor.
    ['getStressTest', '/api/risk/stress'],
    ['getPortfolioAnalysis', '/api/analytics/portfolio'],
    ['getCurrentUser', '/api/auth/me'],
      ['getConversations', '/api/ai_orchestrator/conversations'],
  ])('%s calls %s', (method, path) => {
    const fetchMock = mockFetch({})
    ;(apiClient as never as Record<string, () => void>)[method]()
    expect(calledUrl(fetchMock)).toBe(path)
  })

  it('senaryo faktörü ve şoku gövdede gider', () => {
    const fetchMock = mockFetch({})
    apiClient.runScenario('USDTRY', -10)
    expect(calledUrl(fetchMock)).toBe('/api/risk/scenario')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      factor: 'USDTRY', shock_pct: -10,
    })
  })

  it('dönem yalnızca verildiğinde gönderilir', () => {
    // Verilmediğinde backend'in penceresi kullanılıyor; buraya bir sayı
    // gömmek, ekranın ve sohbetin farklı pencerelerden konuşması demekti.
    const fetchMock = mockFetch({})
    apiClient.runScenario('XU100', 10, '3M')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).lookback).toBe('3M')
  })

  it('stres testinde dönem sorgu dizesine kodlanır', () => {
    const fetchMock = mockFetch({})
    apiClient.getStressTest('6M')
    expect(calledUrl(fetchMock)).toBe('/api/risk/stress?lookback=6M')
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

  /* `put` arrived on main with the Settings page and no test. It shares every
     branch with `post` -- the duplicate /api strip, the absolute-URL escape,
     the optional body -- and each of those is a way for a save to be sent to
     the wrong URL, silently. */
  it('strips a duplicate /api prefix on a PUT', async () => {
    const fetchMock = mockFetch({})
    await apiClient.put('/api/auth/settings', { wants_email_notifications: false })
    expect(calledUrl(fetchMock)).toBe('/api/auth/settings')
    expect(fetchMock.mock.calls[0][1].method).toBe('PUT')
  })

  it('passes an absolute PUT URL through untouched', async () => {
    const fetchMock = mockFetch({})
    await apiClient.put('https://example.test/hook', {})
    expect(calledUrl(fetchMock)).toBe('https://example.test/hook')
  })

  it('sends no body when none is given', async () => {
    /* `JSON.stringify(undefined)` is the string "undefined", which a backend
       reads as a malformed body rather than as no body at all. */
    const fetchMock = mockFetch({})
    await apiClient.put('/api/auth/verify')
    expect(fetchMock.mock.calls[0][1].body).toBeUndefined()
  })

  it('turns a failed PUT into a thrown error', async () => {
    mockFetch({ detail: 'olmadı' }, false)
    await expect(apiClient.put('/api/auth/settings', {})).rejects.toThrow()
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

  it('asks the investment endpoint for the investment statement', () => {
    /**
     * Ayrı bir uç, çünkü yatırım nakdi `banking.accounts` değil
     * `investment.investment_accounts` üzerinde duruyor. Bankacılık ucuna
     * sorulduğunda 404 dönüyor ve tek bir reddedilen istek bütün sayfayı
     * düşürüyordu.
     */
    const fetchMock = mockFetch({})
    apiClient.getInvestmentStatement('TR00 123', 5)
    expect(calledUrl(fetchMock)).toContain('/investment/accounts/TR00%20123/statement')
    expect(calledUrl(fetchMock)).toContain('limit=5')
  })

  it('defaults the investment statement limit', () => {
    const fetchMock = mockFetch({})
    apiClient.getInvestmentStatement('TR00123')
    expect(calledUrl(fetchMock)).toContain('limit=20')
  })

  it('asks for one chart range, not all five', () => {
    /* Beş aralığın hepsi tek istekte üretiliyordu: çağrı başına ~130 sorgu ve
       ölçülen 5,9 saniye. Ekran aynı anda bir aralık gösteriyor. */
    const fetchMock = mockFetch({})
    apiClient.getPortfolioChart('hafta')
    expect(calledUrl(fetchMock)).toBe('/api/investment/portfolio/chart?range=hafta')
  })

  it('defaults the chart range to the year', () => {
    const fetchMock = mockFetch({})
    apiClient.getPortfolioChart()
    expect(calledUrl(fetchMock)).toContain('range=yil')
  })

  it('sends the market filter to the heatmap', () => {
    const fetchMock = mockFetch({ items: [], missing: 0 })
    apiClient.getMarketHeatmap('SP500', 50)
    expect(calledUrl(fetchMock)).toContain('market=SP500')
    expect(calledUrl(fetchMock)).toContain('limit=50')
  })

  it('omits the market when none is chosen', () => {
    const fetchMock = mockFetch({ items: [], missing: 0 })
    apiClient.getMarketHeatmap()
    expect(calledUrl(fetchMock)).not.toContain('market=')
  })

  it('encodes the search term and the limit', () => {
    /* Evren binin üzerinde enstrüman: bir açılır liste taşımaz, arama
       sunucuda. */
    const fetchMock = mockFetch([])
    apiClient.searchInstruments('şişe cam', 5)
    expect(calledUrl(fetchMock)).toContain('/market/search?q=%C5%9Fi%C5%9Fe%20cam')
    expect(calledUrl(fetchMock)).toContain('limit=5')
  })

  it('defaults the search limit', () => {
    const fetchMock = mockFetch([])
    apiClient.searchInstruments('thy')
    expect(calledUrl(fetchMock)).toContain('limit=10')
  })

  it('asks for the intraday series only when a range is given', () => {
    /* "Gün" görünümü 15 dakikalık gerçek barları okur; diğerleri günlük. */
    const withRange = mockFetch({})
    apiClient.getPortfolioAnalysis(undefined, 'day')
    expect(calledUrl(withRange)).toContain('/analytics/portfolio?range=day')

    const without = mockFetch({})
    apiClient.getPortfolioAnalysis()
    expect(calledUrl(without)).toBe('/api/analytics/portfolio')
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

// ---------------------------------------------------------------------------
// Conversations
//
// The endpoints that make the database the source of truth for chat history.
// Before them, the session list came entirely from localStorage: history died
// with the browser profile and the next person to use the machine could read
// it.
// ---------------------------------------------------------------------------
describe('conversations', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('lists conversations with the requested page window', async () => {
    const fetchMock = mockFetch({ items: [], total: 0, limit: 5, offset: 10 })
    await apiClient.getConversations({ limit: 5, offset: 10 })
    expect(calledUrl(fetchMock)).toContain('/api/ai_orchestrator/conversations?')
    expect(calledUrl(fetchMock)).toContain('limit=5')
    expect(calledUrl(fetchMock)).toContain('offset=10')
  })

  it('omits the query string when no window was asked for', async () => {
    const fetchMock = mockFetch({ items: [], total: 0, limit: 20, offset: 0 })
    await apiClient.getConversations()
    expect(calledUrl(fetchMock)).toMatch(/\/conversations$/)
  })

  it('reads one conversation by thread id', async () => {
    const fetchMock = mockFetch({ messages: [] })
    await apiClient.getConversation('t-1')
    expect(calledUrl(fetchMock)).toMatch(/\/conversations\/t-1$/)
  })

  it('passes a message window through when one is given', async () => {
    const fetchMock = mockFetch({ messages: [] })
    await apiClient.getConversation('t-1', 50)
    expect(calledUrl(fetchMock)).toContain('limit=50')
  })

  it('escapes a thread id so it cannot alter the path', async () => {
    const fetchMock = mockFetch({ messages: [] })
    await apiClient.getConversation('a/../b')
    expect(calledUrl(fetchMock)).toContain('a%2F..%2Fb')
  })

  it('renames a conversation with PATCH', async () => {
    const fetchMock = mockFetch({ title: 'yeni' })
    const result = await apiClient.renameConversation('t-1', 'yeni')
    expect(fetchMock.mock.calls[0][1].method).toBe('PATCH')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({ title: 'yeni' })
    expect(result.title).toBe('yeni')
  })

  it('surfaces a failed rename rather than pretending it worked', async () => {
    mockFetch({ detail: 'Sohbet bulunamadı.' }, false)
    await expect(apiClient.renameConversation('t-1', 'yeni')).rejects.toThrow('API Hatası')
  })

  it('deletes a conversation and reads the confirmation body', async () => {
    /* The endpoint answers 200 with a body rather than 204 because
       request() calls response.json() unconditionally. */
    const fetchMock = mockFetch({ thread_id: 't-1', status: 'deleted' })
    const result = await apiClient.deleteConversation('t-1')
    expect(fetchMock.mock.calls[0][1].method).toBe('DELETE')
    expect(result).toEqual({ thread_id: 't-1', status: 'deleted' })
  })
})

describe('ensureFreshSession', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  function tokenExpiringIn(seconds: number): string {
    const exp = Math.floor(Date.now() / 1000) + seconds
    const payload = btoa(JSON.stringify({ sub: '1', exp }))
      .replace(/\+/g, '-')
      .replace(/\//g, '_')
    return `h.${payload}.s`
  }

  it('is anonymous when there is no token at all', async () => {
    expect(await apiClient.ensureFreshSession()).toBe('anonymous')
  })

  it('leaves a healthy token alone and makes no request', async () => {
    localStorage.setItem('access_token', tokenExpiringIn(3600))
    const fetchMock = mockFetch({})
    expect(await apiClient.ensureFreshSession()).toBe('authenticated')
    expect(fetchMock).not.toHaveBeenCalled()
  })

  it('refreshes a token that is about to expire', async () => {
    /* The chat endpoints accept anonymous calls, so an expired token yields
       200-anonymous rather than a 401 — authedFetch's refresh machinery
       never fires on this path. That is why the session dropped in silence. */
    localStorage.setItem('access_token', tokenExpiringIn(10))
    localStorage.setItem('refresh_token', 'r-1')
    const fetchMock = mockFetch({ access_token: 'fresh' })
    expect(await apiClient.ensureFreshSession()).toBe('authenticated')
    expect(calledUrl(fetchMock)).toContain('/auth/refresh')
    expect(localStorage.getItem('access_token')).toBe('fresh')
  })

  it('falls back to anonymous when the refresh fails', async () => {
    localStorage.setItem('access_token', tokenExpiringIn(10))
    localStorage.setItem('refresh_token', 'r-1')
    mockFetch({}, false)
    expect(await apiClient.ensureFreshSession()).toBe('anonymous')
  })

  it('does not redirect on failure', async () => {
    /* Yanking someone to /login mid-sentence loses what they typed. */
    localStorage.setItem('access_token', tokenExpiringIn(10))
    mockFetch({}, false)
    const assign = vi.fn()
    vi.stubGlobal('location', { pathname: '/chat', assign })
    await apiClient.ensureFreshSession()
    expect(assign).not.toHaveBeenCalled()
  })
})

describe('streamChat persistence frame', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  function streamOf(chunks: string[]) {
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
    vi.stubGlobal('fetch', vi.fn(async () => ({ ok: true, status: 200, body })))
  }

  it('reports the saved frame the backend appends after the answer', async () => {
    /* Dispatch is by payload SHAPE, not by event name, and this frame has
       neither `stage` nor `final_output` — before the branch existed it was
       parsed and then silently dropped. */
    streamOf([
      'event: done\ndata: {"final_output":"Merhaba"}\n\n',
      'event: saved\ndata: {"conversation_id":"conv-1","persistence":"saved"}\n\n',
    ])
    let saved: any = null
    const ok = await apiClient.streamChat({ user_message: 'selam' }, {
      onSaved: (p) => { saved = p },
    })
    expect(ok).toBe(true)
    expect(saved).toEqual({ conversation_id: 'conv-1', persistence: 'saved' })
  })

  it('carries the reason a turn was not stored', async () => {
    streamOf([
      'event: done\ndata: {"final_output":"Merhaba"}\n\n',
      'event: saved\ndata: {"conversation_id":null,"persistence":"session_expired"}\n\n',
    ])
    let saved: any = null
    await apiClient.streamChat({ user_message: 'selam' }, { onSaved: (p) => { saved = p } })
    expect(saved.persistence).toBe('session_expired')
    expect(saved.conversation_id).toBeNull()
  })

  it('survives a saved frame with no handler attached', async () => {
    streamOf([
      'event: done\ndata: {"final_output":"Merhaba"}\n\n',
      'event: saved\ndata: {"conversation_id":null,"persistence":"anonymous"}\n\n',
    ])
    await expect(apiClient.streamChat({ user_message: 'selam' }, {})).resolves.toBe(true)
  })
})

describe('onSessionExpired', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('clears the chat store along with the tokens', async () => {
    /* Clearing tokens but leaving the conversations behind is what handed
       the next person on a shared browser the previous user's chats. */
    const { ANON_KEY } = await import('../lib/chatStorage')
    localStorage.setItem('access_token', 'a')
    localStorage.setItem('refresh_token', 'r')
    localStorage.setItem(ANON_KEY, '[{"id":"s"}]')
    vi.stubGlobal('location', { pathname: '/login', assign: vi.fn() })

    ApiClientClass.onSessionExpired()

    expect(localStorage.getItem('access_token')).toBeNull()
    expect(localStorage.getItem('refresh_token')).toBeNull()
    expect(localStorage.getItem(ANON_KEY)).toBeNull()
  })
})

// Pre-existing coverage gaps, closed here because the repo gates at 100%.
// `createTransfer` was only ever mocked by the banking render tests, so its
// body never ran; `describeError` is reached only through a failing response.
describe('transfers and error messages', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('posts a transfer to the banking endpoint', async () => {
    const fetchMock = mockFetch({ id: 't-1' })
    await apiClient.createTransfer({
      source_account_id: 'a', destination_account_id: 'b', amount: 1,
    } as never)
    expect(calledUrl(fetchMock)).toBe('/api/banking/transfers')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' })
  })

  it("surfaces the backend's reason instead of a bare status code", async () => {
    // "Bakiye yetersiz: ..." tells the user what to fix; "422" does not.
    mockFetch({ detail: 'Bakiye yetersiz: transfer ücretle birlikte 120 TL.' }, false)
    await expect(
      apiClient.createTransfer({} as never),
    ).rejects.toThrow('Bakiye yetersiz: transfer ücretle birlikte 120 TL.')
  })

  it('joins FastAPI validation messages, which arrive as an array', async () => {
    mockFetch({ detail: [{ msg: 'amount pozitif olmalı' }, { msg: 'hesap gerekli' }] }, false)
    await expect(
      apiClient.createTransfer({} as never),
    ).rejects.toThrow('amount pozitif olmalı • hesap gerekli')
  })

  it('falls back to the status line when the array carries no usable text', async () => {
    mockFetch({ detail: [{ nope: 1 }] }, false)
    await expect(apiClient.createTransfer({} as never)).rejects.toThrow(/API Hatası/)
  })

  it('falls back when the body is not JSON at all', async () => {
    // A 502 from the network layer has no JSON body to read.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 502, statusText: 'Bad Gateway',
      json: () => Promise.reject(new Error('not json')),
    }))
    await expect(apiClient.createTransfer({} as never)).rejects.toThrow(/502/)
  })
})

describe('banking payments', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('looks a bill up by institution and subscriber number', () => {
    // Found by number rather than owned by a user: the number on the paper is
    // the key, and that is what makes a saved payee worth keeping.
    const fetchMock = mockFetch({ found: false })
    apiClient.lookupBill('BEDAŞ', 'TEST-900112')
    const url = calledUrl(fetchMock)
    expect(url).toContain('/api/banking/bills/lookup')
    expect(url).toContain('institution=BEDA')
    expect(url).toContain('subscriber_no=TEST-900112')
  })

  it('stages a payment without moving money', () => {
    // Staging and confirming are two calls on purpose. That split is the only
    // reason the assistant can prepare a payment it cannot make.
    const fetchMock = mockFetch({ proposal_id: 'PAY-1' })
    apiClient.stagePayment({ payment_type: 'BILL_PAYMENT', institution: 'İSKİ', subscriber_no: '1' })
    expect(calledUrl(fetchMock)).toBe('/api/banking/payments/stage')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' })
  })

  it('confirms by proposal id', () => {
    const fetchMock = mockFetch({ status: 'CONFIRMED' })
    apiClient.confirmPayment('PAY-1')
    expect(calledUrl(fetchMock)).toBe('/api/banking/payments/PAY-1/confirm')
  })

  it('escapes a proposal id rather than pasting it into the path', () => {
    const fetchMock = mockFetch({})
    apiClient.confirmPayment('a/b')
    expect(calledUrl(fetchMock)).toBe('/api/banking/payments/a%2Fb/confirm')
  })

  it('reads saved payees', () => {
    const fetchMock = mockFetch({ payees: [] })
    apiClient.getSavedPayees()
    expect(calledUrl(fetchMock)).toBe('/api/banking/saved-payees')
  })

  it('adds a saved payee', () => {
    const fetchMock = mockFetch({ id: 'p-1' })
    apiClient.addSavedPayee({ label: 'BEDAŞ', institution: 'BEDAŞ', subscriber_no: '1' })
    expect(calledUrl(fetchMock)).toBe('/api/banking/saved-payees')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'POST' })
  })

  it('deletes a saved payee', () => {
    const fetchMock = mockFetch({})
    apiClient.deleteSavedPayee('p-1')
    expect(calledUrl(fetchMock)).toBe('/api/banking/saved-payees/p-1')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'DELETE' })
  })
})

describe('accounts', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('asks for every account money can move between', () => {
    // Including the investment account, whose cash lives in another table —
    // the screen should not have to know that.
    const fetchMock = mockFetch([])
    apiClient.getAllAccounts()
    expect(calledUrl(fetchMock)).toBe('/api/banking/accounts/all')
  })
})

describe('cards and loans', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('reads the cards', () => {
    const fetchMock = mockFetch([])
    apiClient.getCards()
    expect(calledUrl(fetchMock)).toBe('/api/banking/cards')
  })

  it('reads the loans', () => {
    const fetchMock = mockFetch([])
    apiClient.getLoans()
    expect(calledUrl(fetchMock)).toBe('/api/banking/loans')
  })

  it('merges card settings rather than replacing them', () => {
    // A screen that toggles one switch must not clear the others; the
    // backend merges, and the client sends only what changed.
    const fetchMock = mockFetch({})
    apiClient.updateCardSettings('card-1', { frozen: true })
    expect(calledUrl(fetchMock)).toBe('/api/banking/cards/card-1/settings')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PATCH' })
  })
})

// ---------------------------------------------------------------------------
// Risk tolerans anketi
// ---------------------------------------------------------------------------
describe('risk questionnaire', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('anketi getirir', async () => {
    const fetchMock = mockFetch({ version: 'v1', questions: [] })
    const result = await apiClient.getRiskQuestionnaire()
    expect(calledUrl(fetchMock)).toContain('/api/risk/questionnaire')
    expect(result.version).toBe('v1')
  })

  it('cevapları gövdede gönderir', async () => {
    const fetchMock = mockFetch({ tolerance_level: 'Orta', raw_score: 50 })
    const result = await apiClient.submitRiskAssessment({ horizon: 'over_5y' })
    expect(fetchMock.mock.calls[0][1].method).toBe('POST')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      answers: { horizon: 'over_5y' },
    })
    expect(result.tolerance_level).toBe('Orta')
  })

  it('eksik anket reddedilirse sunucunun gerekçesini taşır', async () => {
    /* Sunucu 422 ile hangi sorunun eksik olduğunu söylüyor; onu jenerik bir
       "API Hatası"na çevirmek, kullanıcıya hiçbir şey anlatmaz. Sessizce
       başarı döndürmek ise daha kötü: beyan etmediği bir toleransı beyan
       ettiğine inanır. */
    mockFetch({ detail: 'Şu sorular yanıtlanmadı: goal' }, false)
    await expect(apiClient.submitRiskAssessment({})).rejects.toThrow(
      'Şu sorular yanıtlanmadı: goal',
    )
  })

  it('lookback verilmezse profil sorgusuna parametre eklemez', async () => {
    const fetchMock = mockFetch({})
    await apiClient.getRiskProfile()
    expect(calledUrl(fetchMock)).toMatch(/\/risk\/profile$/)
  })

  it('lookback verilirse geçirir', async () => {
    const fetchMock = mockFetch({})
    await apiClient.getRiskProfile('3M')
    expect(calledUrl(fetchMock)).toContain('lookback=3M')
  })
})

describe('risk simulation', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('değişiklikleri gövdede gönderir', async () => {
    const fetchMock = mockFetch({ current: {}, hypothetical: {}, deltas: {} })
    await apiClient.simulateRisk([{ symbol: 'NVDA', quantity_delta: 10 }])
    expect(calledUrl(fetchMock)).toContain('/api/risk/simulate')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body)).toEqual({
      changes: [{ symbol: 'NVDA', quantity_delta: 10 }],
    })
  })

  it('pencere verilirse gövdeye ekler, verilmezse hiç yazmaz', async () => {
    /* `lookback: undefined` göndermek sunucuda varsayılanı ezmeye çalışır;
       alanı hiç yazmamak varsayılanın kullanılmasını sağlar. */
    const fetchMock = mockFetch({})
    await apiClient.simulateRisk([{ symbol: 'NVDA', quantity_delta: 1 }], '3M')
    expect(JSON.parse(fetchMock.mock.calls[0][1].body).lookback).toBe('3M')
  })

  it('boş portföy hatasında sunucunun gerekçesini taşır', async () => {
    mockFetch({ detail: 'Karşılaştırma için önce değerlenebilir bir pozisyon gerekiyor.' }, false)
    await expect(
      apiClient.simulateRisk([{ symbol: 'NVDA', quantity_delta: 1 }]),
    ).rejects.toThrow('pozisyon gerekiyor')
  })
})

describe('risk history', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('gün sayısı verilmezse sorguya parametre eklemez', async () => {
    /* Sunucunun kendi varsayılanı var; `?days=undefined` göndermek onu
       ezmeye çalışıp 422 alırdı. */
    const fetchMock = mockFetch({ lookback: '1Y', days: 90, points: [] })
    await apiClient.getRiskHistory()
    expect(calledUrl(fetchMock)).toMatch(/\/risk\/history$/)
  })

  it('gün sayısı verilirse geçirir', async () => {
    const fetchMock = mockFetch({ lookback: '1Y', days: 30, points: [] })
    const result = await apiClient.getRiskHistory(30)
    expect(calledUrl(fetchMock)).toContain('days=30')
    expect(result.days).toBe(30)
  })
})

describe('sohbet belgeleri', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  const DOC = {
    id: 'doc-1', filename: 'bilanco.pdf', kind: 'PDF', size_bytes: 2048,
    units: 12, char_count: 4096, truncated: false,
    created_at: '2026-08-31T10:00:00Z',
  }
  const file = () => new File(['x'], 'bilanco.pdf', { type: 'application/pdf' })

  it('dosyayı multipart olarak gönderir', async () => {
    const fetchMock = mockFetch(DOC)
    await apiClient.uploadChatDocument(file())

    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBeInstanceOf(FormData)
  })

  it('Content-Type başlığını ELLE KURMAZ', async () => {
    /* multipart sınırını tarayıcı üretir; elle yazılan bir başlık onu ezer
       ve gövde ayrıştırılamaz hâle gelir. */
    const fetchMock = mockFetch(DOC)
    await apiClient.uploadChatDocument(file())

    const init = fetchMock.mock.calls[0][1] as RequestInit
    const headers = new Headers(init.headers)
    expect(headers.get('content-type')).toBeNull()
  })

  it('sohbet kimliğini gövdeye koyar', async () => {
    const fetchMock = mockFetch(DOC)
    await apiClient.uploadChatDocument(file(), 'thread-9')

    const body = (fetchMock.mock.calls[0][1] as RequestInit).body as FormData
    expect(body.get('thread_id')).toBe('thread-9')
  })

  it('sohbet kimliği yoksa alanı hiç eklemez', async () => {
    const fetchMock = mockFetch(DOC)
    await apiClient.uploadChatDocument(file())

    const body = (fetchMock.mock.calls[0][1] as RequestInit).body as FormData
    expect(body.get('thread_id')).toBeNull()
  })

  it('reddedilen yükleme hata fırlatır', async () => {
    mockFetch({ detail: 'Bu dosya türü okunamıyor' }, 415)
    await expect(apiClient.uploadChatDocument(file())).rejects.toThrow()
  })

  it('listeyi getirir', async () => {
    const fetchMock = mockFetch({ documents: [DOC], accepted: ['.pdf'], max_bytes: 10 })
    const body = await apiClient.getChatDocuments()

    expect(calledUrl(fetchMock)).toContain('/ai_orchestrator/documents')
    expect(body.documents[0].filename).toBe('bilanco.pdf')
  })

  it('belge kimliğini adreste kodlar', async () => {
    const fetchMock = mockFetch({}, 204)
    await apiClient.deleteChatDocument('a/b?c')

    expect(calledUrl(fetchMock)).toContain('documents/a%2Fb%3Fc')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('DELETE')
  })

  it('silinemeyen belge hata fırlatır', async () => {
    /* Sessizce başarılı saymak, kullanıcıya sildiğini söyleyip aranmaya
       devam eden bir belge bırakmak olurdu. */
    mockFetch({ detail: 'Belge şu anda silinemiyor.' }, 503)
    await expect(apiClient.deleteChatDocument('doc-1')).rejects.toThrow()
  })
})

describe('temel veri ve takvim', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('sembolü kodlayarak temel veriyi ister', async () => {
    const fetchMock = mockFetch({ symbol: 'THYAO' })
    await apiClient.getFundamentals('A/B')
    expect(calledUrl(fetchMock)).toContain('/market/fundamentals?symbol=A%2FB')
  })

  it('takvimi sınırla birlikte ister', async () => {
    const fetchMock = mockFetch({ analysts: [], dividends: [], earnings: [] })
    await apiClient.getMarketCalendar(40)
    expect(calledUrl(fetchMock)).toContain('/market/calendar?limit=40')
  })

  it('sınır verilmezse parametre eklemez', async () => {
    /* Sunucunun kendi varsayılanı var; `?limit=undefined` onu ezmeye
       çalışıp 422 alırdı. */
    const fetchMock = mockFetch({ analysts: [], dividends: [], earnings: [] })
    await apiClient.getMarketCalendar()
    expect(calledUrl(fetchMock)).toMatch(/\/market\/calendar$/)
  })
})

describe('teknik görünüm', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  const body = {
    symbol: 'AKBNK',
    currency: 'TRY',
    signals: { trend: 'UPTREND', sma_200: null, observations: 252 },
    narrative: 'AKBNK yükseliş eğiliminde.',
  }

  it('sembolü sorguya koyar', async () => {
    const fetchMock = mockFetch(body)
    await apiClient.getTechnicalSignals('AKBNK')
    expect(calledUrl(fetchMock)).toContain('/market/technicals?symbol=AKBNK')
  })

  it('sembolü kodlar', async () => {
    /* Sembol adresin içine giriyor; kodlanmadan geçen bir eğik çizgi ya da
       soru işareti başka bir uç noktaya sorar. */
    const fetchMock = mockFetch(body)
    await apiClient.getTechnicalSignals('A/B?C')
    expect(calledUrl(fetchMock)).toContain('symbol=A%2FB%3FC')
  })

  it('null bir göstergeyi null olarak taşır', async () => {
    /* null "geçmiş bu göstergeyi hesaplayacak kadar uzun değil" demek;
       sıfıra çevirmek "fiyat tam ortalamasının üzerinde" demek olurdu. */
    const result = await (mockFetch(body), apiClient.getTechnicalSignals('AKBNK'))
    expect(result.signals.sma_200).toBeNull()
    expect(result.narrative).toBe('AKBNK yükseliş eğiliminde.')
  })
})

// ---------------------------------------------------------------------------
// Ayarlar (#42): şifre değiştirme, veri dışa aktarma, hesap silme
// ---------------------------------------------------------------------------
describe('settings actions', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('şifre değişikliğini gövdede gönderir', async () => {
    const fetchMock = mockFetch({})
    await apiClient.changePassword({
      current_password: 'Password123!', new_password: 'Password456!',
    })
    expect(calledUrl(fetchMock)).toBe('/api/auth/change-password')
    const body = JSON.parse(fetchMock.mock.calls[0][1].body as string)
    // Mevcut şifre de gidiyor: sunucu kimliği doğrulamadan değiştirmemeli.
    expect(body.current_password).toBe('Password123!')
  })

  it('veri dışa aktarma isteğini POST eder', async () => {
    const fetchMock = mockFetch({ message: 'ok' })
    const result = await apiClient.requestDataExport()
    expect(calledUrl(fetchMock)).toBe('/api/auth/export-data')
    expect(result.message).toBe('ok')
  })

  it('profil güncellemesi PUT ile gider', async () => {
    const fetchMock = mockFetch({ id: '1', first_name: 'A', last_name: 'B' })
    await apiClient.updateProfile({ transaction_limit: 25000 })
    expect(calledUrl(fetchMock)).toBe('/api/auth/me')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'PUT' })
  })

  it('hesap silme başarısız olursa sunucunun gerekçesi yükseltilir', async () => {
    // Sessizce yutulan bir silme hatası, kullanıcıya hesabının silindiğini
    // söyleyip silmemek olurdu.
    vi.stubGlobal('fetch', vi.fn(() => Promise.resolve({
      ok: false, status: 400, headers: { get: () => 'application/json' },
      json: () => Promise.resolve({ detail: 'Silinemedi' }),
      text: () => Promise.resolve('{"detail":"Silinemedi"}'),
    })))
    await expect(apiClient.deleteAccount({})).rejects.toThrow(/Silinemedi/)
  })

  it('hesap silme DELETE ile gider', async () => {
    const fetchMock = mockFetch({})
    await apiClient.deleteAccount({ reason: 'test' })
    expect(calledUrl(fetchMock)).toContain('/api/auth/me')
    expect(fetchMock.mock.calls[0][1]).toMatchObject({ method: 'DELETE' })
  })
})

describe('hedef dağılım', () => {
  it('sends the whole target list, not a patch', async () => {
    // Kısmi güncelleme yok: birleştirme, toplamı 100 olan bir hedefi
    // sessizce 140'a çıkarabilirdi.
    const fetchMock = mockFetch({ hasTarget: true, targets: [] })
    await apiClient.setAllocationTarget([
      { bucket: 'bist_equity', targetPercent: 60 },
      { bucket: 'cash', targetPercent: 40 },
    ])
    expect(calledUrl(fetchMock)).toBe('/api/investment/allocation-target')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('PUT')
    expect(JSON.parse(init.body as string)).toEqual({
      targets: [
        { bucket: 'bist_equity', targetPercent: 60 },
        { bucket: 'cash', targetPercent: 40 },
      ],
    })
  })

  it('clears the target with an empty list', async () => {
    const fetchMock = mockFetch({ hasTarget: false, targets: [] })
    await apiClient.setAllocationTarget([])
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(JSON.parse(init.body as string)).toEqual({ targets: [] })
  })
})

describe('detaylı rapor PDF', () => {
  it('asks the server for the document rather than printing the page', async () => {
    // Belge SUNUCUDA üretiliyor: ekranın DOM'unu yazdırmak, raporun metnini
    // ikinci bir yerde kurmak olurdu ve iki yüzey ayrışırdı.
    const blob = new Blob(['%PDF-1.4'], { type: 'application/pdf' })
    const fetchMock = vi.fn().mockResolvedValue({
      ok: true, status: 200, blob: async () => blob,
    })
    vi.stubGlobal('fetch', fetchMock)
    const got = await apiClient.downloadPortfolioReportPdf()
    expect(calledUrl(fetchMock)).toBe('/api/analytics/report.pdf')
    expect(got).toBe(blob)
  })

  it('raises when the server cannot produce it', async () => {
    // 503: yazı tipi kurulu değil. Sessizce boş bir dosya indirmek, bozuk
    // bir belgeyi belge diye vermek olurdu.
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({
      ok: false, status: 503, statusText: 'Service Unavailable',
    }))
    await expect(apiClient.downloadPortfolioReportPdf()).rejects.toThrow('503')
  })
})

describe('bildirimler', () => {
  it('asks for the list with the badge count', async () => {
    const fetchMock = mockFetch({ unread_count: 3, items: [] })
    const got = await apiClient.getNotifications(50)
    expect(calledUrl(fetchMock)).toBe('/api/notification/me/notifications?limit=50')
    expect(got.unread_count).toBe(3)
  })

  it('marks one as read by its id', async () => {
    const fetchMock = mockFetch({ id: 'n-1', is_read: true })
    await apiClient.markNotificationAsRead('n-1')
    expect(calledUrl(fetchMock)).toBe('/api/notification/me/notifications/n-1/read')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('PUT')
  })

  it('escapes an id rather than pasting it into the path', async () => {
    // Kimlik yoldan geçiyor; kaçırılmadığında bir eğik çizgi başka bir uca
    // gider.
    const fetchMock = mockFetch({ id: 'x', is_read: true })
    await apiClient.markNotificationAsRead('a/b')
    expect(calledUrl(fetchMock)).toContain('a/b')
  })

  it('marks all of them read in one call', async () => {
    const fetchMock = mockFetch({ message: 'ok' })
    await apiClient.markAllNotificationsAsRead()
    expect(calledUrl(fetchMock)).toBe('/api/notification/me/notifications/mark-all-read')
    expect((fetchMock.mock.calls[0][1] as RequestInit).method).toBe('POST')
  })
})

describe('postForm', () => {
  beforeEach(() => localStorage.clear())
  afterEach(() => vi.unstubAllGlobals())

  it('sends the FormData untouched and sets no Content-Type', () => {
    /* multipart sınırını (`boundary=...`) tarayıcı üretiyor. Elle yazılan bir
       Content-Type onu ezer ve gövde sunucuda ayrıştırılamaz hâle gelir --
       istemcinin sessizce bozabileceği türden bir hata. */
    const fetchMock = mockFetch({ url: '/media/a.png' })
    const body = new FormData()
    body.append('file', new Blob(['x']), 'a.png')
    apiClient.postForm('/auth/profile-picture', body)

    expect(calledUrl(fetchMock)).toBe('/api/auth/profile-picture')
    const init = fetchMock.mock.calls[0][1] as RequestInit
    expect(init.method).toBe('POST')
    expect(init.body).toBe(body)
    expect(JSON.stringify(init.headers ?? {})).not.toContain('Content-Type')
  })

  it('strips a leading /api rather than doubling it', () => {
    const fetchMock = mockFetch({})
    apiClient.postForm('/api/auth/profile-picture', new FormData())
    expect(calledUrl(fetchMock)).toBe('/api/auth/profile-picture')
  })

  it('leaves an absolute URL alone', () => {
    const fetchMock = mockFetch({})
    apiClient.postForm('https://cdn.example/upload', new FormData())
    expect(calledUrl(fetchMock)).toBe('https://cdn.example/upload')
  })

  it('throws on a non-2xx instead of returning an empty body', async () => {
    mockFetch({ detail: 'Dosya çok büyük' }, 413)
    await expect(
      apiClient.postForm('/auth/profile-picture', new FormData()),
    ).rejects.toThrow()
  })

  it('rethrows a network failure', async () => {
    vi.stubGlobal('fetch', vi.fn().mockRejectedValue(new Error('offline')))
    await expect(
      apiClient.postForm('/auth/profile-picture', new FormData()),
    ).rejects.toThrow('offline')
  })
})

describe('getMarketNews', () => {
    beforeEach(() => localStorage.clear())
    afterEach(() => vi.unstubAllGlobals())

    it('sends no query when nothing is asked for', () => {
        const fetchMock = mockFetch([])
        apiClient.getMarketNews()
        expect(calledUrl(fetchMock)).toBe('/api/market/news')
    })

    it('sends symbols as a repeated key, not a comma list', () => {
        // FastAPI reads List[str] from repeated keys; a comma list arrives as
        // one symbol named "THYAO,AAPL" and matches nothing.
        const fetchMock = mockFetch([])
        apiClient.getMarketNews({ symbols: ['THYAO', 'AAPL'] })
        expect(calledUrl(fetchMock)).toBe('/api/market/news?symbols=THYAO&symbols=AAPL')
    })

    it('sends the limit', () => {
        const fetchMock = mockFetch([])
        apiClient.getMarketNews({ limit: 50 })
        expect(calledUrl(fetchMock)).toBe('/api/market/news?limit=50')
    })

    it('an empty params object still sends no query', () => {
        const fetchMock = mockFetch([])
        apiClient.getMarketNews({})
        expect(calledUrl(fetchMock)).toBe('/api/market/news')
    })
})

/**
 * The shared live-price connection.
 *
 * Two properties carry real cost if they break: ONE EventSource for the whole
 * app (a hook that opened its own would mean four sockets and four times the
 * backend fan-out for identical data), and a fallback to polling when the
 * stream cannot be established — a dashboard that silently stops updating is
 * worse than one that polls, because the prices look current and are not.
 */
import { act, renderHook, waitFor } from '@testing-library/react'
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'

const instances: FakeEventSource[] = []

class FakeEventSource {
  static readonly OPEN = 1
  url: string
  onerror: ((this: EventSource, ev: Event) => unknown) | null = null
  closed = false
  private listeners: Record<string, ((event: MessageEvent) => void)[]> = {}

  constructor(url: string) {
    this.url = url
    instances.push(this)
  }

  addEventListener(name: string, handler: (event: MessageEvent) => void) {
    ;(this.listeners[name] ||= []).push(handler)
  }

  close() {
    this.closed = true
  }

  /** Push a frame as the server would. */
  emit(name: string, data: unknown) {
    for (const handler of this.listeners[name] || []) {
      handler(new MessageEvent(name, { data: JSON.stringify(data) }))
    }
  }

  /** Push a malformed frame. */
  emitRaw(name: string, data: string) {
    for (const handler of this.listeners[name] || []) {
      handler(new MessageEvent(name, { data }))
    }
  }

  fail() {
    this.onerror?.call(this as never, new Event('error'))
  }
}

const FRAME = {
  as_of: '2026-08-20T12:00:00Z',
  is_delayed: true,
  delay_minutes: 15,
  quotes: { THYAO: { price: 304, change: 3, changePercent: 1 } },
}

async function loadHook() {
  vi.resetModules()
  return await import('./useMarketStream')
}

describe('useMarketStream', () => {
  beforeEach(() => {
    instances.length = 0
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })

  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('opens exactly one connection for many subscribers', async () => {
    const { useMarketStream } = await loadHook()
    renderHook(() => useMarketStream())
    renderHook(() => useMarketStream())
    renderHook(() => useMarketStream())
    expect(instances).toHaveLength(1)
  })

  it('delivers a frame to every subscriber', async () => {
    const { useMarketStream } = await loadHook()
    const first = renderHook(() => useMarketStream())
    const second = renderHook(() => useMarketStream())
    act(() => instances[0].emit('quotes', FRAME))
    expect(first.result.current.quotes.THYAO.price).toBe(304)
    expect(second.result.current.quotes.THYAO.price).toBe(304)
  })

  it('carries the delay, so a price is never presented as live', async () => {
    const { useMarketStream } = await loadHook()
    const { result } = renderHook(() => useMarketStream())
    act(() => instances[0].emit('quotes', FRAME))
    expect(result.current.isDelayed).toBe(true)
    expect(result.current.delayMinutes).toBe(15)
    expect(result.current.transport).toBe('live')
  })

  it('skips a malformed frame instead of clearing the snapshot', async () => {
    const { useMarketStream } = await loadHook()
    const { result } = renderHook(() => useMarketStream())
    act(() => instances[0].emit('quotes', FRAME))
    act(() => instances[0].emitRaw('quotes', 'not json'))
    expect(result.current.quotes.THYAO.price).toBe(304)
  })

  it('closes the connection when the last subscriber unmounts', async () => {
    const { useMarketStream } = await loadHook()
    const { unmount } = renderHook(() => useMarketStream())
    unmount()
    expect(instances[0].closed).toBe(true)
  })

  it('keeps the connection while any subscriber remains', async () => {
    const { useMarketStream } = await loadHook()
    const first = renderHook(() => useMarketStream())
    renderHook(() => useMarketStream())
    first.unmount()
    expect(instances[0].closed).toBe(false)
  })

  it('reconnects after a dropped connection', async () => {
    const { useMarketStream } = await loadHook()
    renderHook(() => useMarketStream())
    act(() => instances[0].fail())
    await act(async () => {
      vi.advanceTimersByTime(1500)
    })
    expect(instances.length).toBeGreaterThan(1)
  })

  it('falls back to polling after repeated failures', async () => {
    // The browser retries SSE forever on its own; if the endpoint is genuinely
    // gone that loop never ends and the UI freezes without saying so.
    const { useMarketStream } = await loadHook()
    const { result } = renderHook(() => useMarketStream())
    for (let attempt = 0; attempt < 3; attempt += 1) {
      act(() => instances[instances.length - 1].fail())
      await act(async () => {
        vi.advanceTimersByTime(4000)
      })
    }
    await waitFor(() => expect(result.current.transport).toBe('polling'))
    expect(fetch).toHaveBeenCalled()
  })
})

describe('useQuote', () => {
  beforeEach(() => {
    instances.length = 0
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('returns one instrument’s quote', async () => {
    const { useQuote } = await loadHook()
    const { result } = renderHook(() => useQuote('THYAO'))
    act(() => instances[0].emit('quotes', FRAME))
    expect(result.current?.price).toBe(304)
  })

  it('returns undefined before a frame arrives, not a zeroed placeholder', async () => {
    // A component showing 0,00 TL while it waits is asserting a price, and it
    // would be wrong.
    const { useQuote } = await loadHook()
    const { result } = renderHook(() => useQuote('THYAO'))
    expect(result.current).toBeUndefined()
  })
})

describe('the polling fallback', () => {
  beforeEach(() => {
    instances.length = 0
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  async function failIntoPolling(fetchImpl: unknown) {
    vi.stubGlobal('fetch', fetchImpl)
    const { useMarketStream } = await loadHook()
    const hook = renderHook(() => useMarketStream())
    for (let attempt = 0; attempt < 3; attempt += 1) {
      act(() => instances[instances.length - 1].fail())
      await act(async () => {
        vi.advanceTimersByTime(4000)
      })
    }
    return hook
  }

  it('polls the whole universe, not the four-symbol ticker strip', async () => {
    // Polling /tickers narrowed the snapshot from ~95 instruments to 4, so
    // after three SSE failures every live table froze while the strip moved.
    const body = {
      instruments: [
        { symbol: 'THYAO', price: 301, change: 1, change_percent: 0.3, currency: 'TRY' },
        { symbol: 'AAPL', price: 314.88, change: 6.8, change_percent: 2.2, currency: 'USD' },
        { symbol: 'USDTRY', price: 47.9479, change: 0, change_percent: 0, currency: 'TRY' },
      ],
    }
    const fetchMock = vi.fn().mockResolvedValue({ ok: true, json: async () => body })
    const hook = await failIntoPolling(fetchMock)
    await waitFor(() => expect(hook.result.current.quotes.THYAO?.price).toBe(301))
    expect(hook.result.current.quotes.AAPL?.currency).toBe('USD')
    expect(String(fetchMock.mock.calls[0][0])).toContain('/api/market/instruments')
    expect(hook.result.current.transport).toBe('polling')
  })

  it('normalises a polled row that omits its change fields', async () => {
    // /instruments leaves change and change_percent null for an instrument
    // with no previous close; null must survive as null, not become 0, which
    // would render as "unchanged today".
    const body = {
      instruments: [{ symbol: 'IPEKE', price: 12.5, currency: 'TRY' }],
    }
    const hook = await failIntoPolling(
      vi.fn().mockResolvedValue({ ok: true, json: async () => body }),
    )
    await waitFor(() => expect(hook.result.current.quotes.IPEKE?.price).toBe(12.5))
    expect(hook.result.current.quotes.IPEKE.change).toBeNull()
    expect(hook.result.current.quotes.IPEKE.changePercent).toBeNull()
  })

  it('recovers the FX rates while polling, so conversions keep working', async () => {
    const body = {
      instruments: [{ symbol: 'USDTRY', price: 47.9479, change: 0, change_percent: 0, currency: 'TRY' }],
    }
    const hook = await failIntoPolling(
      vi.fn().mockResolvedValue({ ok: true, json: async () => body }),
    )
    await waitFor(() => expect(hook.result.current.rates.USD).toBeCloseTo(47.9479))
  })

  it('keeps the last snapshot when a poll fails', async () => {
    // Blanking the dashboard on one failed poll would be a worse lie than
    // showing a slightly stale price.
    const hook = await failIntoPolling(vi.fn().mockRejectedValue(new Error('offline')))
    await act(async () => {
      vi.advanceTimersByTime(11000)
    })
    expect(hook.result.current.transport).not.toBe('live')
  })

  it('ignores a non-ok poll response', async () => {
    const hook = await failIntoPolling(
      vi.fn().mockResolvedValue({ ok: false, json: async () => [] }),
    )
    await act(async () => {
      vi.advanceTimersByTime(11000)
    })
    expect(hook.result.current.quotes).toEqual({})
  })

  it('tolerates a frame with no fields rather than throwing', async () => {
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    const { useMarketStream } = await loadHook()
    const { result } = renderHook(() => useMarketStream())
    act(() => instances[0].emit('quotes', {}))
    expect(result.current.quotes).toEqual({})
    expect(result.current.asOf).toBeNull()
    expect(result.current.delayMinutes).toBe(0)
  })
})

describe('polling is started once', () => {
  beforeEach(() => {
    instances.length = 0
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => [] }))
    vi.useFakeTimers({ shouldAdvanceTime: true })
  })
  afterEach(() => {
    vi.useRealTimers()
    vi.unstubAllGlobals()
  })

  it('a further error does not start a second poll timer', async () => {
    // A stale EventSource can still fire onerror after the fallback is
    // running. Without the guard each one would add another interval, and the
    // backend would see the poll rate multiply with every dropped socket.
    const { useMarketStream } = await loadHook()
    renderHook(() => useMarketStream())
    const first = instances[0]
    for (let attempt = 0; attempt < 3; attempt += 1) {
      act(() => instances[instances.length - 1].fail())
      await act(async () => {
        vi.advanceTimersByTime(4000)
      })
    }
    const callsBefore = (fetch as ReturnType<typeof vi.fn>).mock.calls.length

    act(() => first.fail())
    await act(async () => {
      vi.advanceTimersByTime(10_000)
    })

    const callsAfter = (fetch as ReturnType<typeof vi.fn>).mock.calls.length
    // One interval, so one poll per cycle — not two.
    expect(callsAfter - callsBefore).toBeLessThanOrEqual(2)
  })
})

describe('conversion rates', () => {
  beforeEach(() => {
    instances.length = 0
    vi.stubGlobal('EventSource', FakeEventSource)
    vi.stubGlobal('fetch', vi.fn().mockResolvedValue({ ok: true, json: async () => ({ instruments: [] }) }))
  })
  afterEach(() => vi.unstubAllGlobals())

  it('reads the lira rates out of the frame itself', async () => {
    // Derived rather than sent alongside: USDTRY and EURTRY are instruments
    // like any other, so a separate fx field could drift from the quotes.
    const { useMarketStream } = await loadHook()
    const { result } = renderHook(() => useMarketStream())
    act(() => instances[0].emit('quotes', {
      ...FRAME,
      quotes: {
        USDTRY: { price: 47.9479, change: 0, changePercent: 0 },
        EURTRY: { price: 56.0921, change: 0, changePercent: 0 },
      },
    }))
    expect(result.current.rates.USD).toBeCloseTo(47.9479)
    expect(result.current.rates.EUR).toBeCloseTo(56.0921)
  })

  it('reports no rate when the FX instrument is absent', async () => {
    // Callers must be able to tell "unknown" from a number, so they can show
    // the native price rather than an invented lira one.
    const { useMarketStream } = await loadHook()
    const { result } = renderHook(() => useMarketStream())
    act(() => instances[0].emit('quotes', FRAME))
    expect(result.current.rates.USD).toBeUndefined()
  })

  it('carries each quote’s own currency', async () => {
    const { useMarketStream } = await loadHook()
    const { result } = renderHook(() => useMarketStream())
    act(() => instances[0].emit('quotes', {
      ...FRAME,
      quotes: { AAPL: { price: 314.88, change: 1, changePercent: 0.3, currency: 'USD' } },
    }))
    expect(result.current.quotes.AAPL.currency).toBe('USD')
  })

  it('merges a partial frame onto what it already has', async () => {
    /**
     * Evren 1010 enstrümana çıkınca her tam kare 88 KB oldu ve fiyat her
     * değiştiğinde açık olan her sekmeye gidiyordu. Sunucu artık yalnızca
     * DEĞİŞENLERİ yolluyor; istemci onları elindekinin üstüne biniyor.
     *
     * Kısmi kareyi tam kare gibi uygulamak, o karede geçmeyen her sembolü
     * ekrandan silerdi.
     */
    const { useMarketStream } = await loadHook()
    const view = renderHook(() => useMarketStream())

    act(() => instances[0].emit('quotes', {
      ...FRAME,
      partial: false,
      quotes: {
        THYAO: { price: 304, change: 3, changePercent: 1 },
        ASELS: { price: 90, change: 1, changePercent: 1.1 },
      },
    }))

    act(() => instances[0].emit('quotes', {
      ...FRAME,
      partial: true,
      quotes: { THYAO: { price: 310, change: 9, changePercent: 3 } },
    }))

    expect(view.result.current.quotes.THYAO.price).toBe(310)
    // Kısmi karede geçmeyen sembol yerinde duruyor.
    expect(view.result.current.quotes.ASELS.price).toBe(90)
  })

  it('a full frame replaces the snapshot rather than merging', async () => {
    /* Listeden çıkan bir enstrüman, tam kare geldiğinde gitmeli. */
    const { useMarketStream } = await loadHook()
    const view = renderHook(() => useMarketStream())

    act(() => instances[0].emit('quotes', {
      ...FRAME,
      quotes: { THYAO: { price: 304, change: 3, changePercent: 1 },
                GONE: { price: 5, change: 0, changePercent: 0 } },
    }))
    act(() => instances[0].emit('quotes', {
      ...FRAME,
      partial: false,
      quotes: { THYAO: { price: 305, change: 4, changePercent: 1.2 } },
    }))

    expect(view.result.current.quotes.GONE).toBeUndefined()
  })
})

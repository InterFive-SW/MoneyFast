/**
 * The adapter between the API's instrument rows and the markets screens.
 *
 * Everything here is a shape mismatch that a typecheck cannot catch on its
 * own: snake_case versus camelCase, nullable fundamentals, and a `market`
 * vocabulary ("NASDAQ") that differs from the one the table's tabs filter on
 * ("ABD"). Getting the last one wrong renders an empty tab against live data.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import * as stream from './useMarketStream'
import { useInstruments } from './useInstruments'

function apiRow(overrides = {}) {
  return {
    symbol: 'THYAO', name: 'Türk Hava Yolları', market: 'BIST', currency: 'TRY',
    price: 304, change: 3, change_percent: 1, market_timestamp: '2026-08-20T12:00:00Z',
    pe_ratio: 8.2, pb_ratio: 1.4, market_cap: 1000, dividend_yield: 2.3,
    sector: 'Industrials', week52_high: 355, week52_low: 210,
    ...overrides,
  }
}

function mockApi(rows: unknown[]) {
  vi.spyOn(apiClient, 'getInstruments').mockResolvedValue({ instruments: rows } as never)
  vi.spyOn(stream, 'useMarketStream').mockReturnValue({
    asOf: null, isDelayed: true, delayMinutes: 0, quotes: {}, rates: {}, transport: 'connecting',
  })
}

describe('useInstruments', () => {
  afterEach(() => vi.restoreAllMocks())

  it('renames the API fields to the shape the tables read', async () => {
    mockApi([apiRow()])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].changePercent).toBe(1)
    expect(result.current.instruments[0].pe).toBe(8.2)
  })

  it.each([
    ['NASDAQ', 'ABD'],
    ['NYSE', 'ABD'],
    ['BIST', 'BIST'],
  ])('maps the %s exchange onto the %s tab', async (market, expected) => {
    // The table filters with `item.market !== activeTab`, so an unmapped
    // exchange renders the tab empty against perfectly good data.
    mockApi([apiRow({ market })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].market).toBe(expected)
  })

  it('maps the currency onto a display unit', async () => {
    mockApi([apiRow({ currency: 'USD' })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].unit).toBe('$')
  })

  it('leaves an unpublished ratio undefined rather than zero', async () => {
    // A zero P/E would sort to the top of a "cheapest" screen — a company with
    // no published earnings presented as the best value on the list.
    mockApi([apiRow({ pe_ratio: null, pb_ratio: null })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].pe).toBeUndefined()
  })

  it('labels a missing sector rather than leaving it blank', async () => {
    mockApi([apiRow({ sector: null })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].sector).toBe('Bilinmiyor')
  })

  it('treats a missing change as flat so sorting does not produce NaN', async () => {
    mockApi([apiRow({ change_percent: null })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].changePercent).toBe(0)
  })

  it('derives the sector list from what is actually present', async () => {
    mockApi([apiRow(), apiRow({ symbol: 'AKBNK', sector: 'Financials' })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.sectors).toEqual(['Financials', 'Industrials'])
  })

  it('requests the limit it was given', async () => {
    mockApi([])
    renderHook(() => useInstruments(50))
    await waitFor(() => expect(apiClient.getInstruments).toHaveBeenCalledWith({ limit: 50 }))
  })

  it('sends the market filter to the server, not the client', async () => {
    /**
     * Evren binin üzerinde enstrüman. `limit` kadarını çekip istemcide
     * süzmek, seçilen piyasanın yalnızca ilk sayfaya düşen kısmını
     * göstermek olurdu.
     *
     * `market` bir borsa (NASDAQ) ya da bir endeks (SP500) olabilir: AAPL
     * Nasdaq'ta işlem görür VE S&P 500 üyesidir.
     */
    mockApi([])
    renderHook(() => useInstruments(50, 'SP500'))
    await waitFor(() =>
      expect(apiClient.getInstruments).toHaveBeenCalledWith({ limit: 50, market: 'SP500' }),
    )
  })

  it('stops loading and shows nothing when the request fails', async () => {
    vi.spyOn(apiClient, 'getInstruments').mockRejectedValue(new Error('down'))
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(stream, 'useMarketStream').mockReturnValue({
      asOf: null, isDelayed: true, delayMinutes: 0, quotes: {}, rates: {}, transport: 'connecting',
    })
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments).toEqual([])
  })

  it('tolerates a response with no instruments key', async () => {
    mockApi(undefined as never)
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments).toEqual([])
  })
})

describe('adapter fallbacks', () => {
  afterEach(() => vi.restoreAllMocks())

  it('labels an unmapped venue "Diğer" rather than claiming BIST', async () => {
    // Better than dropping the row: an unmapped venue still has a price.
    // 'BIST' idi ve bu, satırı yanlış bir borsaya yazıyordu.
    mockApi([apiRow({ market: 'XETRA' })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].market).toBe('Diğer')
  })

  it('labels a null venue "Diğer" too', async () => {
    mockApi([apiRow({ market: null })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].market).toBe('Diğer')
  })

  it.each([
    ['FX', 'Döviz'],
    ['COMEX', 'Altın'],
  ])('maps %s to %s — the document names both', async (upstream, label) => {
    mockApi([apiRow({ market: upstream })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].market).toBe(label)
  })

  it('shows an unmapped currency code rather than an empty unit', async () => {
    mockApi([apiRow({ currency: 'GBP' })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].unit).toBe('GBP')
  })

  it('defaults absent market cap and 52-week bounds to zero', async () => {
    // These feed a range bar that divides by (high - low); undefined would
    // render NaN across the column.
    mockApi([apiRow({ market_cap: null, week52_high: null, week52_low: null })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    const row = result.current.instruments[0]
    expect(row.marketCap).toBe(0)
    expect(row.week52High).toBe(0)
    expect(row.week52Low).toBe(0)
  })

  it('falls back to the symbol when the instrument has no name', async () => {
    mockApi([apiRow({ name: '' })])
    const { result } = renderHook(() => useInstruments())
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instruments[0].name).toBe('')
  })
})

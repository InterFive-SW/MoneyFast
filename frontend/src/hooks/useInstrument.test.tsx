/**
 * The single-instrument hook.
 *
 * Detail pages used to resolve their subject against MOCK_MARKET_INSTRUMENTS,
 * so clicking THYAO in a table showing 301,25 opened a page showing 295,50 —
 * forever. This is what makes the row and the page agree.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import * as stream from './useMarketStream'
import { useInstrument } from './useInstrument'

const ROW = {
  symbol: 'THYAO', name: 'Türk Hava Yolları', market: 'BIST', currency: 'TRY',
  price: 301.25, change: 1, change_percent: 0.3, market_timestamp: '2026-08-21T00:00:00Z',
  pe_ratio: 8.2, pb_ratio: 1.4, market_cap: 1000, dividend_yield: 2.3,
  sector: 'Industrials', week52_high: 355, week52_low: 210,
}

function mockStream(quotes = {}) {
  vi.spyOn(stream, 'useMarketStream').mockReturnValue({
    asOf: null, isDelayed: true, delayMinutes: 0, quotes, rates: {}, transport: 'live',
  })
}

describe('useInstrument', () => {
  afterEach(() => vi.restoreAllMocks())

  it('fetches the named instrument', async () => {
    mockStream()
    const spy = vi.spyOn(apiClient, 'getInstruments').mockResolvedValue({ instruments: [ROW] } as never)
    const { result } = renderHook(() => useInstrument('THYAO'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(spy).toHaveBeenCalledWith({ symbols: ['THYAO'], limit: 1 })
    expect(result.current.instrument?.price).toBe(301.25)
  })

  it('keeps the price on the live stream', async () => {
    // The whole point: the detail page must move with the table it came from.
    mockStream({ THYAO: { price: 310, change: 9, changePercent: 3 } })
    vi.spyOn(apiClient, 'getInstruments').mockResolvedValue({ instruments: [ROW] } as never)
    const { result } = renderHook(() => useInstrument('THYAO'))
    await waitFor(() => expect(result.current.instrument?.price).toBe(310))
  })

  it('reports nothing for a symbol the API does not know', async () => {
    mockStream()
    vi.spyOn(apiClient, 'getInstruments').mockResolvedValue({ instruments: [] } as never)
    const { result } = renderHook(() => useInstrument('NOPE'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instrument).toBeNull()
  })

  it('does not call the API for an empty symbol', async () => {
    mockStream()
    const spy = vi.spyOn(apiClient, 'getInstruments')
    const { result } = renderHook(() => useInstrument(''))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(spy).not.toHaveBeenCalled()
  })

  it('stops loading and shows nothing when the request fails', async () => {
    mockStream()
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(apiClient, 'getInstruments').mockRejectedValue(new Error('down'))
    const { result } = renderHook(() => useInstrument('THYAO'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instrument).toBeNull()
  })

  it('tolerates a response with no instruments key', async () => {
    mockStream()
    vi.spyOn(apiClient, 'getInstruments').mockResolvedValue({} as never)
    const { result } = renderHook(() => useInstrument('THYAO'))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.instrument).toBeNull()
  })

  it('refetches when the symbol changes', async () => {
    mockStream()
    const spy = vi.spyOn(apiClient, 'getInstruments').mockResolvedValue({ instruments: [ROW] } as never)
    const { rerender, result } = renderHook(({ s }) => useInstrument(s), {
      initialProps: { s: 'THYAO' },
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    rerender({ s: 'ASELS' })
    await waitFor(() => expect(spy).toHaveBeenCalledTimes(2))
  })
})

describe('unmounting mid-flight', () => {
  afterEach(() => vi.restoreAllMocks())

  it('does not set state after the component is gone', async () => {
    // React warns about this, and in a route change it happens constantly:
    // the user clicks away before the request lands.
    mockStream()
    let resolve!: (value: unknown) => void
    vi.spyOn(apiClient, 'getInstruments').mockReturnValue(
      new Promise((r) => { resolve = r }) as never,
    )
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { unmount } = renderHook(() => useInstrument('THYAO'))
    unmount()
    resolve({ instruments: [ROW] })
    await waitFor(() => expect(errors).not.toHaveBeenCalled())
  })

  it('swallows a rejection that arrives after unmount', async () => {
    mockStream()
    let reject!: (reason: unknown) => void
    vi.spyOn(apiClient, 'getInstruments').mockReturnValue(
      new Promise((_, r) => { reject = r }) as never,
    )
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const { unmount } = renderHook(() => useInstrument('THYAO'))
    unmount()
    reject(new Error('too late'))
    await new Promise((r) => setTimeout(r, 0))
  })
})

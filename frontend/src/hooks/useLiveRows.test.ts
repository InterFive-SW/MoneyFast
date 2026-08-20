/**
 * Overlaying live quotes onto fetched rows.
 *
 * The two failures this guards against: a row whose price ticks while the
 * value beside it stays frozen (an internally inconsistent row that reads as a
 * rendering bug), and a row being blanked or zeroed because no quote arrived.
 */
import { renderHook } from '@testing-library/react'
import { describe, expect, it, vi, beforeEach } from 'vitest'
import { useLiveRows } from './useLiveRows'
import * as stream from './useMarketStream'

function withQuotes(quotes: Record<string, { price: number; change: number | null; changePercent: number | null }>) {
  vi.spyOn(stream, 'useMarketStream').mockReturnValue({
    asOf: '2026-08-20T12:00:00Z',
    isDelayed: true,
    delayMinutes: 15,
    quotes,
    transport: 'live',
  })
}

interface Position {
  symbol: string
  price: number
  quantity: number
  avgCost: number
  change?: number | null
  changePercent?: number | null
}

const POSITION: Position = { symbol: 'THYAO', price: 300, quantity: 10, avgCost: 250 }

describe('useLiveRows', () => {
  beforeEach(() => vi.restoreAllMocks())

  it('replaces the price with the live one', () => {
    withQuotes({ THYAO: { price: 310, change: 10, changePercent: 3.33 } })
    const { result } = renderHook(() => useLiveRows([POSITION]))
    expect(result.current[0].price).toBe(310)
  })

  it('refreshes the change alongside the price', () => {
    // A new price beside yesterday's change is a row that contradicts itself.
    withQuotes({ THYAO: { price: 310, change: 10, changePercent: 3.33 } })
    const { result } = renderHook(() => useLiveRows([POSITION]))
    expect(result.current[0].changePercent).toBe(3.33)
  })

  it('leaves a row alone when no quote arrived for it', () => {
    // Not blanked and not zeroed: a stale price shown as stale beats a price
    // shown as 0,00 TL.
    withQuotes({})
    const { result } = renderHook(() => useLiveRows([POSITION]))
    expect(result.current[0]).toEqual(POSITION)
  })

  it('ignores a quote whose price is not a number', () => {
    withQuotes({ THYAO: { price: undefined as never, change: null, changePercent: null } })
    const { result } = renderHook(() => useLiveRows([POSITION]))
    expect(result.current[0].price).toBe(300)
  })

  it('keeps the fetched change when the frame carries none', () => {
    withQuotes({ THYAO: { price: 310, change: null, changePercent: null } })
    const row = { ...POSITION, change: 5, changePercent: 1.7 }
    const { result } = renderHook(() => useLiveRows([row]))
    expect(result.current[0].changePercent).toBe(1.7)
  })

  it('recomputes derived columns through the derive callback', () => {
    withQuotes({ THYAO: { price: 310, change: 10, changePercent: 3.33 } })
    const { result } = renderHook(() =>
      useLiveRows([POSITION], (row) => ({ ...row, totalValue: row.price * row.quantity } as never)),
    )
    expect((result.current[0] as never as { totalValue: number }).totalValue).toBe(3100)
  })

  it('passes the quote to derive so the previous close can be recovered', () => {
    withQuotes({ THYAO: { price: 310, change: 10, changePercent: 3.33 } })
    const seen: unknown[] = []
    renderHook(() =>
      useLiveRows([POSITION], (row, quote) => {
        seen.push(quote)
        return row
      }),
    )
    expect(seen[0]).toMatchObject({ change: 10 })
  })

  it('handles an empty list', () => {
    withQuotes({ THYAO: { price: 310, change: 10, changePercent: 3.33 } })
    const { result } = renderHook(() => useLiveRows([]))
    expect(result.current).toEqual([])
  })
})

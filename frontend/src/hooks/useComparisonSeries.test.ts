/**
 * Percent-change series for comparing instruments.
 *
 * The generator this replaces produced a seeded random walk with a built-in
 * positive bias, so every comparison line trended up regardless of what the
 * instrument had actually done.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import { useComparisonSeries } from './useComparisonSeries'

function candles(closes: number[], startDay = 1) {
  return {
    candles: closes.map((close, index) => ({
      timestamp: `2026-08-${String(startDay + index).padStart(2, '0')}T00:00:00Z`,
      open: close, high: close, low: close, close, volume: 1,
    })),
  }
}

describe('useComparisonSeries', () => {
  afterEach(() => vi.restoreAllMocks())

  it('rebases each series to percent change from its first close', async () => {
    // Rebasing is what lets a 300 TL stock and a 4.500 USD ounce of gold share
    // one axis: their prices cannot be compared, their moves can.
    vi.spyOn(apiClient, 'getCandles').mockResolvedValue(candles([100, 110, 90]) as never)
    const { result } = renderHook(() => useComparisonSeries(['THYAO'], 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data.map((row) => row.THYAO)).toEqual([0, 10, -10])
  })

  it('aligns two instruments on the same dates', async () => {
    vi.spyOn(apiClient, 'getCandles')
      .mockResolvedValueOnce(candles([100, 120]) as never)
      .mockResolvedValueOnce(candles([200, 300]) as never)
    const { result } = renderHook(() => useComparisonSeries(['A', 'B'], 2))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data[1]).toMatchObject({ A: 20, B: 50 })
  })

  it('keeps a date on which only one instrument traded', async () => {
    // Dropping it would silently shorten the chart; the other series simply
    // has no point that day.
    vi.spyOn(apiClient, 'getCandles')
      .mockResolvedValueOnce(candles([100, 120]) as never)
      .mockResolvedValueOnce(candles([200], 1) as never)
    const { result } = renderHook(() => useComparisonSeries(['A', 'B'], 2))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toHaveLength(2)
    expect(result.current.data[1].B).toBeUndefined()
  })

  it('sorts the rows chronologically', async () => {
    vi.spyOn(apiClient, 'getCandles').mockResolvedValue(candles([100, 110, 120]) as never)
    const { result } = renderHook(() => useComparisonSeries(['A'], 3))
    await waitFor(() => expect(result.current.loading).toBe(false))
    const dates = result.current.data.map((row) => row.date)
    expect([...dates].sort()).toEqual(dates)
  })

  it('skips a series whose first close is zero rather than dividing by it', async () => {
    vi.spyOn(apiClient, 'getCandles').mockResolvedValue(candles([0, 10]) as never)
    const { result } = renderHook(() => useComparisonSeries(['A'], 2))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual([])
  })

  it('requests nothing when no symbols are selected', async () => {
    const spy = vi.spyOn(apiClient, 'getCandles')
    const { result } = renderHook(() => useComparisonSeries([], 30))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(spy).not.toHaveBeenCalled()
    expect(result.current.data).toEqual([])
  })

  it('yields an empty chart when the request fails', async () => {
    vi.spyOn(console, 'error').mockImplementation(() => {})
    vi.spyOn(apiClient, 'getCandles').mockRejectedValue(new Error('down'))
    const { result } = renderHook(() => useComparisonSeries(['A'], 30))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual([])
  })

  it('tolerates a response with no candles', async () => {
    vi.spyOn(apiClient, 'getCandles').mockResolvedValue({} as never)
    const { result } = renderHook(() => useComparisonSeries(['A'], 30))
    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.data).toEqual([])
  })

  it('does not refetch when given an equal array of symbols', async () => {
    const spy = vi.spyOn(apiClient, 'getCandles').mockResolvedValue(candles([100]) as never)
    const { rerender, result } = renderHook(({ s }) => useComparisonSeries(s, 30), {
      initialProps: { s: ['A'] },
    })
    await waitFor(() => expect(result.current.loading).toBe(false))
    rerender({ s: ['A'] })
    expect(spy).toHaveBeenCalledTimes(1)
  })
})

describe('unmounting mid-flight', () => {
  afterEach(() => vi.restoreAllMocks())

  it('does not set state after the component is gone', async () => {
    let resolve!: (value: unknown) => void
    vi.spyOn(apiClient, 'getCandles').mockReturnValue(
      new Promise((r) => { resolve = r }) as never,
    )
    const errors = vi.spyOn(console, 'error').mockImplementation(() => {})

    const { unmount } = renderHook(() => useComparisonSeries(['A'], 30))
    unmount()
    resolve(candles([100]))
    await waitFor(() => expect(errors).not.toHaveBeenCalled())
  })

  it('swallows a rejection that arrives after unmount', async () => {
    let reject!: (reason: unknown) => void
    vi.spyOn(apiClient, 'getCandles').mockReturnValue(
      new Promise((_, r) => { reject = r }) as never,
    )
    vi.spyOn(console, 'error').mockImplementation(() => {})

    const { unmount } = renderHook(() => useComparisonSeries(['A'], 30))
    unmount()
    reject(new Error('too late'))
    await new Promise((r) => setTimeout(r, 0))
  })
})

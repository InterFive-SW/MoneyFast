/**
 * The watchlist hook.
 *
 * The star on the Piyasalar table was local component state: it lit up, saved
 * nothing, and reset on navigation. These pin the behaviour that makes it
 * real — and the optimistic update, which is the part most likely to lie to
 * the user if it goes wrong.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, act, waitFor } from '@testing-library/react'
import { useWatchlist, __resetWatchlistStore } from './useWatchlist'
import { apiClient } from '../api/client'

beforeEach(() => {
  // Liste artık modül seviyesinde tek bir depoda (ticker bandının
  // Piyasalar'daki yıldızı duyabilmesi için). Paylaşılan durum, testler
  // arasında sızmaması için her testten önce sıfırlanır.
  __resetWatchlistStore()
  vi.spyOn(console, 'error').mockImplementation(() => {})
  vi.spyOn(apiClient, 'getWatchlist').mockResolvedValue({
    all: [{ symbol: 'THYAO' }, { symbol: 'AAPL' }],
    bist: [{ symbol: 'THYAO' }],
    global: [{ symbol: 'AAPL' }],
  } as never)
  vi.spyOn(apiClient, 'addToWatchlist').mockResolvedValue({} as never)
  vi.spyOn(apiClient, 'removeFromWatchlist').mockResolvedValue({} as never)
})
afterEach(() => vi.restoreAllMocks())

async function mounted() {
  const view = renderHook(() => useWatchlist())
  await waitFor(() => expect(view.result.current.ready).toBe(true))
  return view
}

describe('useWatchlist', () => {
  it('loads the followed symbols', async () => {
    const { result } = await mounted()
    expect([...result.current.symbols].sort()).toEqual(['AAPL', 'THYAO'])
  })

  it('adds a symbol that is not followed yet', async () => {
    const { result } = await mounted()
    await act(async () => { await result.current.toggle('GARAN') })
    expect(apiClient.addToWatchlist).toHaveBeenCalledWith('GARAN')
    expect(result.current.symbols.has('GARAN')).toBe(true)
  })

  it('removes one that is', async () => {
    const { result } = await mounted()
    await act(async () => { await result.current.toggle('THYAO') })
    expect(apiClient.removeFromWatchlist).toHaveBeenCalledWith('THYAO')
    expect(result.current.symbols.has('THYAO')).toBe(false)
  })

  it('reverts an add that the server rejected', async () => {
    // A star that stays lit after a failed save is a lie about what was stored.
    vi.mocked(apiClient.addToWatchlist).mockRejectedValue(new Error('nope'))
    const { result } = await mounted()
    await act(async () => { await result.current.toggle('GARAN') })
    expect(result.current.symbols.has('GARAN')).toBe(false)
  })

  it('reverts a removal that the server rejected', async () => {
    vi.mocked(apiClient.removeFromWatchlist).mockRejectedValue(new Error('nope'))
    const { result } = await mounted()
    await act(async () => { await result.current.toggle('THYAO') })
    expect(result.current.symbols.has('THYAO')).toBe(true)
  })

  it('leaves the stars dark when the list cannot be read', async () => {
    // Guessing would show a filled star for something the server does not have.
    vi.mocked(apiClient.getWatchlist).mockRejectedValue(new Error('offline'))
    const { result } = await mounted()
    expect(result.current.symbols.size).toBe(0)
    expect(result.current.ready).toBe(true)
  })

  it('survives a response with no `all` group', async () => {
    vi.mocked(apiClient.getWatchlist).mockResolvedValue({} as never)
    const { result } = await mounted()
    expect(result.current.symbols.size).toBe(0)
  })

  it('refresh re-reads the server', async () => {
    const { result } = await mounted()
    await act(async () => { await result.current.refresh() })
    expect(apiClient.getWatchlist).toHaveBeenCalledTimes(2)
  })

  it('shares one list across every component that asks for it', async () => {
    /**
     * Ticker bandı, Piyasalar tablosu ve İzleme Listesi widget'ı aynı listeyi
     * gösteriyor. Her biri kendi kopyasını tutarken Piyasalar'da yıldızlanan
     * bir sembol, bandda ancak sayfa yenilenince görünüyordu -- tek bir
     * listenin iki ayrı hâli.
     */
    const first = await mounted()
    const second = await mounted()

    await act(async () => { await first.result.current.toggle('SISE') })

    expect(first.result.current.symbols.has('SISE')).toBe(true)
    expect(second.result.current.symbols.has('SISE')).toBe(true)
  })

  it('reads the list once even when several components mount together', async () => {
    /* Bir sayfada birkaç bileşen aynı anda bağlanıyor; her biri aynı isteği
       ayrı ayrı açmamalı. */
    vi.mocked(apiClient.getWatchlist).mockClear()
    renderHook(() => useWatchlist())
    renderHook(() => useWatchlist())
    await waitFor(() => expect(apiClient.getWatchlist).toHaveBeenCalled())
    expect(apiClient.getWatchlist).toHaveBeenCalledTimes(1)
  })

  it('un-starring the last symbol leaves the list genuinely empty', async () => {
    /* Boş liste boş görünür. Kullanıcının seçmediği hisseleri onun listesiymiş
       gibi göstermek, listenin ne olduğunu anlamsızlaştırır. */
    vi.mocked(apiClient.getWatchlist).mockResolvedValue({
      all: [{ symbol: 'THYAO' }], bist: [{ symbol: 'THYAO' }], global: [],
    } as never)
    const view = await mounted()
    await act(async () => { await view.result.current.toggle('THYAO') })
    expect(view.result.current.symbols.size).toBe(0)
  })
})

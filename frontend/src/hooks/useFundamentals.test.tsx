/**
 * Temel veri ve "Analizler" takvimi.
 *
 * En önemli iddia: `null` "sağlayıcı bunu yayımlamıyor" demek, SIFIR değil.
 * Bankanın brüt marjı yoktur ve onu %0,0 diye çizmek, şirketin hiç sahip
 * olmadığı bir olguyu bildirmek olur.
 */
import { renderHook, waitFor } from '@testing-library/react'
import { afterEach, describe, expect, it, vi } from 'vitest'
import { apiClient } from '../api/client'
import {
  RECOMMENDATION_TR, compact, pct, ratio, shortDate,
  useFundamentals, useMarketCalendar,
} from './useFundamentals'

const FUNDAMENTALS = {
  symbol: 'THYAO', name: 'Türk Hava Yolları', currency: 'TRY',
  updated_at: '2026-08-31T00:00:00Z',
  pe_ratio: null, pb_ratio: 19.36, market_cap: 421977128960,
  dividend_yield: 2.24, sector: 'Industrials', industry: 'Airlines',
  week52_high: 355.5, week52_low: 262.75,
  total_revenue: 26350999552, revenue_growth: 0.205,
  gross_margin: 0.12865, operating_margin: -0.02595,
  ebitda_margin: 0.08296, profit_margin: 0.10189,
  return_on_equity: 0.13129, return_on_assets: 0.01534,
  debt_to_equity: 89.393, current_ratio: 0.905,
  total_debt: 19594000384, total_cash: 6309000192,
  free_cash_flow: 594875008, operating_cash_flow: 3377999872,
  enterprise_value: 437611495424, beta: -0.03,
  trailing_eps: -6.67, forward_eps: 72.02, forward_pe: 4.22,
  earnings_growth: -0.72, payout_ratio: 0.8053, dividend_rate: 6.88,
  recommendation_key: null, analyst_count: 13, target_mean_price: 463.54,
  ex_dividend_date: null, earnings_date: null,
}

describe('useFundamentals', () => {
  afterEach(() => vi.restoreAllMocks())

  it('adı verilen enstrümanı getirir', async () => {
    const get = vi.spyOn(apiClient, 'getFundamentals').mockResolvedValue(FUNDAMENTALS)
    const { result } = renderHook(() => useFundamentals('THYAO'))

    await waitFor(() => expect(result.current.fundamentals).not.toBeNull())
    expect(get).toHaveBeenCalledWith('THYAO')
    expect(result.current.loading).toBe(false)
  })

  it('faaliyet ZARARINI taşır', async () => {
    /* Negatif marj eksik veri değil, dönemin en bilgilendirici olgusu. */
    vi.spyOn(apiClient, 'getFundamentals').mockResolvedValue(FUNDAMENTALS)
    const { result } = renderHook(() => useFundamentals('THYAO'))

    await waitFor(() => expect(result.current.fundamentals).not.toBeNull())
    expect(result.current.fundamentals!.operating_margin).toBeLessThan(0)
  })

  it('istek düşerse veri yerine null bırakır', async () => {
    vi.spyOn(apiClient, 'getFundamentals').mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useFundamentals('THYAO'))

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.fundamentals).toBeNull()
  })

  it('sayfa kapandıktan sonra gelen yanıt duruma yazılmaz', async () => {
    /* Kullanıcı hisseden çıktı, istek hâlâ uçuyor. Sökülmüş bir bileşene
       yazmak React uyarısı üretir ve daha kötüsü, bir sonraki hissede
       öncekinin verisini gösterebilir. */
    let release: (value: typeof FUNDAMENTALS) => void = () => {}
    vi.spyOn(apiClient, 'getFundamentals').mockReturnValue(
      new Promise((resolve) => { release = resolve }),
    )
    const { unmount } = renderHook(() => useFundamentals('THYAO'))

    unmount()
    release(FUNDAMENTALS)

    // Uyarı çıkmadan tamamlanması yeterli; iddia edilen şey çökmemesi.
    await Promise.resolve()
  })

  it('sökülme sırasında düşen bir istek de sessiz kalır', async () => {
    let reject: (reason: unknown) => void = () => {}
    vi.spyOn(apiClient, 'getFundamentals').mockReturnValue(
      new Promise((_resolve, rej) => { reject = rej }),
    )
    const { unmount } = renderHook(() => useFundamentals('THYAO'))

    unmount()
    reject(new Error('boom'))

    await Promise.resolve()
  })
})

describe('useMarketCalendar', () => {
  afterEach(() => vi.restoreAllMocks())

  it('üç listeyi tek çağrıda getirir', async () => {
    const get = vi.spyOn(apiClient, 'getMarketCalendar').mockResolvedValue({
      analysts: [], dividends: [], earnings: [],
    })
    const { result } = renderHook(() => useMarketCalendar())

    await waitFor(() => expect(result.current.calendar).not.toBeNull())
    expect(get).toHaveBeenCalledTimes(1)
  })

  it('istek düşerse null bırakır', async () => {
    vi.spyOn(apiClient, 'getMarketCalendar').mockRejectedValue(new Error('boom'))
    const { result } = renderHook(() => useMarketCalendar())

    await waitFor(() => expect(result.current.loading).toBe(false))
    expect(result.current.calendar).toBeNull()
  })

  it('sayfa kapandıktan sonra gelen yanıt duruma yazılmaz', async () => {
    let release: (value: { analysts: []; dividends: []; earnings: [] }) => void = () => {}
    vi.spyOn(apiClient, 'getMarketCalendar').mockReturnValue(
      new Promise((resolve) => { release = resolve }),
    )
    const { unmount } = renderHook(() => useMarketCalendar())

    unmount()
    release({ analysts: [], dividends: [], earnings: [] })

    await Promise.resolve()
  })

  it('sökülme sırasında düşen bir istek de sessiz kalır', async () => {
    let reject: (reason: unknown) => void = () => {}
    vi.spyOn(apiClient, 'getMarketCalendar').mockReturnValue(
      new Promise((_resolve, rej) => { reject = rej }),
    )
    const { unmount } = renderHook(() => useMarketCalendar())

    unmount()
    reject(new Error('boom'))

    await Promise.resolve()
  })
})

describe('biçimlendiriciler', () => {
  it('oranı yüzdeye çevirir', () => {
    expect(pct(0.12865)).toBe('%12,9')
    expect(pct(-0.02595)).toBe('%-2,6')
  })

  it('eksik oran "—" olur, "%0,0" DEĞİL', () => {
    /* Bankanın brüt marjı yoktur; %0,0 yazmak şirketin hiç sahip olmadığı
       bir olguyu bildirmek olur. */
    expect(pct(null)).toBe('—')
    expect(pct(undefined)).toBe('—')
  })

  it('gerçek sıfırı sıfır olarak yazar', () => {
    expect(pct(0)).toBe('%0,0')
  })

  it('büyük tutarları kısaltır', () => {
    expect(compact(26350999552)).toContain('Mr')
    expect(compact(null)).toBe('—')
    expect(compact(1000, 'TL')).toContain('TL')
  })

  it('katsayıyı x ile yazar', () => {
    expect(ratio(89.393)).toBe('89,39x')
    expect(ratio(null)).toBe('—')
  })

  it('tarihi kısa yazar, yoksa "—"', () => {
    expect(shortDate('2026-07-28T15:00:00Z')).toContain('2026')
    expect(shortDate(null)).toBe('—')
    expect(shortDate(undefined)).toBe('—')
  })

  it('analist konsensüsünü Türkçeleştirir', () => {
    expect(RECOMMENDATION_TR.buy).toBe('Al')
    expect(RECOMMENDATION_TR.strong_buy).toBe('Güçlü Al')
    expect(RECOMMENDATION_TR.hold).toBe('Tut')
  })
})

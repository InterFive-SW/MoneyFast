/**
 * Hisse detay grafiğinin veri katmanı.
 *
 * Korunan iki şey: bir barın para birimi VARSAYILMAZ (AAPL dolar, THYAO
 * lira), ve boş bir seri ile ulaşılamayan bir uç aynı şey değildir.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { CANDLES_ERROR, CANDLE_RANGES, useCandles } from './useCandles'
import { apiClient } from '../api/client'

function bar(day: string, close: number) {
    return {
        timestamp: `${day}T00:00:00Z`,
        open: close - 1,
        high: close + 2,
        low: close - 3,
        close,
        volume: 1000,
    }
}

const SERIES = {
    symbol: 'AAPL',
    currency: 'USD',
    interval: '1d',
    candles: [bar('2026-09-01', 230), bar('2026-09-02', 233)],
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getCandles').mockResolvedValue(SERIES as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useCandles', () => {
    it('barları grafiğin beklediği güne indirger', async () => {
        const { result } = renderHook(() => useCandles('AAPL', 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles).toEqual([
            { time: '2026-09-01', open: 229, high: 232, low: 227, close: 230 },
            { time: '2026-09-02', open: 232, high: 235, low: 230, close: 233 },
        ])
    })

    it('para birimini taşır, varsaymaz', async () => {
        const { result } = renderHook(() => useCandles('AAPL', 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.currency).toBe('USD')
    })

    it('istenen bar sayısını uç noktaya geçirir', async () => {
        renderHook(() => useCandles('THYAO', 252))
        await waitFor(() => expect(apiClient.getCandles).toHaveBeenCalledWith('THYAO', 252))
    })

    it('aynı güne düşen iki bardan sonuncusu kalıyor', async () => {
        /* lightweight-charts aynı güne iki nokta verilirse seriyi sessizce
           reddediyor -- grafik boş çiziliyor ve hiçbir yerde hata görünmüyor. */
        vi.spyOn(apiClient, 'getCandles').mockResolvedValue({
            ...SERIES,
            candles: [bar('2026-09-01', 230), bar('2026-09-01', 231)],
        } as never)
        const { result } = renderHook(() => useCandles('AAPL', 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles).toHaveLength(1)
        expect(result.current.candles[0].close).toBe(231)
    })

    it('seriyi tarihe göre sıralıyor', async () => {
        vi.spyOn(apiClient, 'getCandles').mockResolvedValue({
            ...SERIES,
            candles: [bar('2026-09-03', 235), bar('2026-09-01', 230)],
        } as never)
        const { result } = renderHook(() => useCandles('AAPL', 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles.map((c) => c.time)).toEqual([
            '2026-09-01', '2026-09-03',
        ])
    })

    it('geçmişi olmayan enstrüman boş seri, hata değil', async () => {
        vi.spyOn(apiClient, 'getCandles').mockResolvedValue({
            symbol: 'YOK', currency: 'TRY', interval: '1d', candles: [],
        } as never)
        const { result } = renderHook(() => useCandles('YOK', 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles).toEqual([])
        expect(result.current.error).toBeNull()
    })

    it('`candles` alanı hiç gelmezse boş seri', async () => {
        vi.spyOn(apiClient, 'getCandles').mockResolvedValue({
            symbol: 'YOK', currency: 'TRY', interval: '1d',
        } as never)
        const { result } = renderHook(() => useCandles('YOK', 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles).toEqual([])
    })

    it('para birimi gelmezse null, TRY DEĞİL', async () => {
        /* Eksik bir para birimini liraya sabitlemek, 230 dolarlık bir barı
           "₺230" diye etiketlemek olurdu -- bu deponun bir kez ödediği hata. */
        vi.spyOn(apiClient, 'getCandles').mockResolvedValue({
            symbol: 'AAPL', interval: '1d', candles: [],
        } as never)
        const { result } = renderHook(() => useCandles('AAPL', 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.currency).toBeNull()
    })

    it('ulaşılamayan uç, boş seriden ayrı', async () => {
        vi.spyOn(apiClient, 'getCandles').mockRejectedValue(new Error('down'))
        const { result } = renderHook(() => useCandles('AAPL', 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(CANDLES_ERROR)
        expect(result.current.candles).toEqual([])
        expect(result.current.currency).toBeNull()
    })

    it('sembol yokken istek atmıyor', async () => {
        const { result } = renderHook(() => useCandles(undefined, 66))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getCandles).not.toHaveBeenCalled()
        expect(result.current.candles).toEqual([])
        expect(result.current.currency).toBeNull()
    })

    it('sökülmüş bileşene geç gelen CEVAP yazılmıyor', async () => {
        /* Yarış: yavaş dönen istek, kullanıcı başka bir hisseye geçtikten
           sonra cevaplarsa grafik yanlış enstrümanı çizerdi. */
        let settle: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getCandles').mockReturnValue(
            new Promise((resolve) => {
                settle = resolve
            }) as never,
        )
        const { unmount } = renderHook(() => useCandles('AAPL', 66))
        unmount()
        settle(SERIES)
        await waitFor(() => expect(apiClient.getCandles).toHaveBeenCalled())
    })

    it('sökülmüş bileşene geç gelen HATA da yazılmıyor', async () => {
        /* Aynı yarışın diğer ucu: iptal edilmiş bir istek başarısız olunca
           ekranda kalmayan bir bileşene hata yazmaya çalışırdı. */
        let fail: (reason: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getCandles').mockReturnValue(
            new Promise((_resolve, reject) => {
                fail = reject
            }) as never,
        )
        const { unmount } = renderHook(() => useCandles('AAPL', 66))
        unmount()
        fail(new Error('down'))
        await waitFor(() => expect(apiClient.getCandles).toHaveBeenCalled())
    })

    it('aralıklar uç noktanın 400 bar sınırının altında', async () => {
        for (const range of CANDLE_RANGES) {
            expect(range.bars).toBeLessThanOrEqual(400)
            expect(range.bars).toBeGreaterThanOrEqual(2)
        }
    })
})

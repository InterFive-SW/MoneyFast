/**
 * Haftalık portföy serisi.
 *
 * Korunan asıl iddia: haftalık grafik günlük bar okumuyor. Ölçüldü, aynı
 * portföy ve aynı hafta -- `/analytics/portfolio` 5 nokta, bu uç 266.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { WEEK_SERIES_ERROR, usePortfolioWeekSeries } from './usePortfolioWeekSeries'
import { apiClient } from '../api/client'

/** Uç noktanın gerçek yanıt biçimi: aralık adıyla anahtarlanmış OHLC. */
function payload(points: { time: number; close: number }[]) {
    return {
        hafta: points.map((p) => ({
            time: p.time, open: p.close, high: p.close, low: p.close,
            close: p.close, value: 0, color: '#22c55e',
        })),
    }
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getPortfolioChart').mockResolvedValue(
        payload([
            { time: 1788159300, close: 1106051 },
            { time: 1788159600, close: 1106377.81 },
        ]) as never,
    )
})
afterEach(() => vi.restoreAllMocks())

describe('usePortfolioWeekSeries', () => {
    it('kova kapanışını çizgi değeri yapıyor', async () => {
        const { result } = renderHook(() => usePortfolioWeekSeries(true))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.points).toEqual([
            { at: 1788159300000, value: 1106051 },
            { at: 1788159600000, value: 1106377.81 },
        ])
    })

    it('haftalık aralığı istiyor', async () => {
        renderHook(() => usePortfolioWeekSeries(true))
        await waitFor(() => expect(apiClient.getPortfolioChart).toHaveBeenCalledWith('hafta'))
    })

    it('kapalıyken istek atmıyor', async () => {
        const { result } = renderHook(() => usePortfolioWeekSeries(false))
        await waitFor(() => expect(result.current.points).toEqual([]))
        expect(apiClient.getPortfolioChart).not.toHaveBeenCalled()
    })

    it('bir kez çekiyor, her açılışta değil', async () => {
        const { result, rerender } = renderHook(
            ({ on }) => usePortfolioWeekSeries(on), { initialProps: { on: true } },
        )
        await waitFor(() => expect(result.current.loading).toBe(false))
        rerender({ on: true })
        await waitFor(() => expect(apiClient.getPortfolioChart).toHaveBeenCalledTimes(1))
    })

    it('seriyi zamana göre sıralıyor', async () => {
        vi.spyOn(apiClient, 'getPortfolioChart').mockResolvedValue(
            payload([{ time: 200, close: 2 }, { time: 100, close: 1 }]) as never,
        )
        const { result } = renderHook(() => usePortfolioWeekSeries(true))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.points.map((p) => p.at)).toEqual([100_000, 200_000])
    })

    it('sayı olmayan noktaları atıyor', async () => {
        vi.spyOn(apiClient, 'getPortfolioChart').mockResolvedValue({
            hafta: [
                { time: 100, close: 1 },
                { time: null, close: 2 },
                { time: 300, close: 'abc' },
            ],
        } as never)
        const { result } = renderHook(() => usePortfolioWeekSeries(true))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.points).toEqual([{ at: 100_000, value: 1 }])
    })

    it('aralık anahtarı gelmezse boş seri', async () => {
        vi.spyOn(apiClient, 'getPortfolioChart').mockResolvedValue({} as never)
        const { result } = renderHook(() => usePortfolioWeekSeries(true))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.points).toEqual([])
        expect(result.current.error).toBeNull()
    })

    it('liste olmayan gövde boş seri', async () => {
        vi.spyOn(apiClient, 'getPortfolioChart').mockResolvedValue({ hafta: 'x' } as never)
        const { result } = renderHook(() => usePortfolioWeekSeries(true))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.points).toEqual([])
    })

    it('ulaşılamayan uç, boş haftadan AYRI', async () => {
        /* Biri "bu hafta veri yok" diyor, diğeri hiçbir şey demiyor. */
        vi.spyOn(apiClient, 'getPortfolioChart').mockRejectedValue(new Error('down'))
        const { result } = renderHook(() => usePortfolioWeekSeries(true))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(WEEK_SERIES_ERROR)
        expect(result.current.points).toEqual([])
    })

    it('sökülmüş bileşene geç gelen cevap yazılmıyor', async () => {
        let settle: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getPortfolioChart').mockReturnValue(
            new Promise((resolve) => { settle = resolve }) as never,
        )
        const { unmount } = renderHook(() => usePortfolioWeekSeries(true))
        unmount()
        settle(payload([{ time: 100, close: 1 }]))
        await waitFor(() => expect(apiClient.getPortfolioChart).toHaveBeenCalled())
    })

    it('sökülmüş bileşene geç gelen HATA da yazılmıyor', async () => {
        let fail: (reason: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getPortfolioChart').mockReturnValue(
            new Promise((_r, reject) => { fail = reject }) as never,
        )
        const { unmount } = renderHook(() => usePortfolioWeekSeries(true))
        unmount()
        fail(new Error('down'))
        await waitFor(() => expect(apiClient.getPortfolioChart).toHaveBeenCalled())
    })
})

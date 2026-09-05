/**
 * Fon mum serisi.
 *
 * Korunan iddia: fon gunde TEK fiyat yayimliyor, dolayisiyla kova genisligi
 * bir ayrinti degil -- kullanici baktigi cubugun neyi ozetledigini bilmeli.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import {
    FUND_CANDLES_ERROR, FUND_RANGES, useFundCandles, type FundRange,
} from './useFundCandles'
import { apiClient } from '../api/client'

const PAYLOAD = {
    code: 'AAL',
    currency: 'TRY',
    bucket: 'week',
    candles: [
        { date: '2026-08-31', open: 10, high: 12, low: 9, close: 11 },
        { date: '2026-09-07', open: 11, high: 13, low: 10.5, close: 12.5 },
    ],
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getFundCandles').mockResolvedValue(PAYLOAD as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useFundCandles', () => {
    it('mumlari grafigin bekledigi bicime cevirir', async () => {
        const { result } = renderHook(() => useFundCandles('AAL', '3A'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles[0]).toEqual({
            time: '2026-08-31', open: 10, high: 12, low: 9, close: 11,
        })
    })

    it('kova genisligini tasir', async () => {
        const { result } = renderHook(() => useFundCandles('AAL', '3A'))
        await waitFor(() => expect(result.current.bucket).toBe('week'))
    })

    it('araligi uc noktaya gecirir', async () => {
        renderHook(() => useFundCandles('AAL', '1Y'))
        await waitFor(() => expect(apiClient.getFundCandles).toHaveBeenCalledWith('AAL', '1Y'))
    })

    it('aralik degisince yeniden ceker', async () => {
        const { result, rerender } = renderHook(
            ({ w }: { w: FundRange }) => useFundCandles('AAL', w),
            { initialProps: { w: '3A' as FundRange } },
        )
        await waitFor(() => expect(result.current.loading).toBe(false))
        rerender({ w: '1Y' as FundRange })
        await waitFor(() => expect(apiClient.getFundCandles).toHaveBeenCalledTimes(2))
    })

    it('kodu olmayan cagri istek atmaz', async () => {
        renderHook(() => useFundCandles('', '3A'))
        await waitFor(() => expect(apiClient.getFundCandles).not.toHaveBeenCalled())
    })

    it('eksik fiyatli mum atilir, SIFIRLANMAZ', async () => {
        /* Sifir bir mumu tabana cakardi. */
        vi.spyOn(apiClient, 'getFundCandles').mockResolvedValue({
            ...PAYLOAD,
            candles: [
                { date: '2026-08-31', open: 10, high: 12, low: 9, close: 11 },
                { date: '2026-09-07', open: null, high: 13, low: 10, close: 12 },
                { date: '', open: 1, high: 1, low: 1, close: 1 },
                // `date` anahtarı HİÇ yok: `?? ''` dalı.
                { open: 1, high: 1, low: 1, close: 1 },
            ],
        } as never)
        const { result } = renderHook(() => useFundCandles('AAL', '3A'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles).toHaveLength(1)
    })

    it('seriyi tarihe gore siralar', async () => {
        vi.spyOn(apiClient, 'getFundCandles').mockResolvedValue({
            ...PAYLOAD,
            candles: [
                { date: '2026-09-07', open: 1, high: 1, low: 1, close: 1 },
                { date: '2026-08-31', open: 2, high: 2, low: 2, close: 2 },
            ],
        } as never)
        const { result } = renderHook(() => useFundCandles('AAL', '3A'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles.map((c) => c.time)).toEqual([
            '2026-08-31', '2026-09-07',
        ])
    })

    it('alan hic gelmezse bos seri', async () => {
        vi.spyOn(apiClient, 'getFundCandles').mockResolvedValue({ code: 'AAL' } as never)
        const { result } = renderHook(() => useFundCandles('AAL', '3A'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.candles).toEqual([])
        expect(result.current.bucket).toBeNull()
    })

    it('ulasilamayan uc, bos seriden AYRI', async () => {
        vi.spyOn(apiClient, 'getFundCandles').mockRejectedValue(new Error('down'))
        const { result } = renderHook(() => useFundCandles('AAL', '3A'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(FUND_CANDLES_ERROR)
    })

    it('sokulmus bilesene gec gelen cevap yazilmaz', async () => {
        let settle: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getFundCandles').mockReturnValue(
            new Promise((resolve) => { settle = resolve }) as never,
        )
        const { unmount } = renderHook(() => useFundCandles('AAL', '3A'))
        unmount()
        settle(PAYLOAD)
        await waitFor(() => expect(apiClient.getFundCandles).toHaveBeenCalled())
    })

    it('sokulmus bilesene gec gelen HATA da yazilmaz', async () => {
        let fail: (reason: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getFundCandles').mockReturnValue(
            new Promise((_r, reject) => { fail = reject }) as never,
        )
        const { unmount } = renderHook(() => useFundCandles('AAL', '3A'))
        unmount()
        fail(new Error('down'))
        await waitFor(() => expect(apiClient.getFundCandles).toHaveBeenCalled())
    })

    it('sunulan araliklar sunucununkilerle ayni', () => {
        expect([...FUND_RANGES]).toEqual(['1A', '3A', '1Y', '5Y'])
    })
})

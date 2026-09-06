/**
 * TEFAS fon listesi.
 *
 * Korunan iddialar: suzgecler SUNUCUYA gidiyor (2.602 fonu tarayiciya
 * gondermek yerine), acilir listeler VERIDEN geliyor, ve ulasilamayan bir
 * uc ile bos bir liste ayri seyler.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { FUNDS_ERROR, useFunds } from './useFunds'
import { apiClient } from '../api/client'

const PAYLOAD = {
    items: [{
        code: 'AAL', name: 'ATA PORTFOY PARA PIYASASI (TL) FONU',
        founder: 'ATA PORTFOY YONETIMI A.S.', umbrella: 'Para Piyasasi Semsiye Fonu',
        fundType: 'YAT', price: 3.35, investorCount: 4498, size: 2470539665.41,
        asOf: '2026-09-05',
        returns: { daily: 0.1, monthly: 2.4, threeMonth: 7.1, yearly: null, threeYear: null, fiveYear: null },
    }],
    founders: ['ATA PORTFOY YONETIMI A.S.', 'AK PORTFOY'],
    umbrellas: ['Para Piyasasi Semsiye Fonu'],
    total: 1,
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getFunds').mockResolvedValue(PAYLOAD as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useFunds', () => {
    it('fonlari ve acilir liste iceriklerini tasiyor', async () => {
        const { result } = renderHook(() => useFunds())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.funds[0].code).toBe('AAL')
        expect(result.current.founders).toHaveLength(2)
        expect(result.current.umbrellas).toEqual(['Para Piyasasi Semsiye Fonu'])
    })

    it('suzgecleri sunucuya gonderiyor', async () => {
        renderHook(() => useFunds({ founder: 'AK PORTFOY', q: 'hisse' }))
        await waitFor(() => expect(apiClient.getFunds).toHaveBeenCalledWith({
            founder: 'AK PORTFOY', umbrella: undefined, fundType: undefined, q: 'hisse',
        }))
    })

    it('ayni suzgecle tekrar render bir kez cekiyor', async () => {
        const { result, rerender } = renderHook(
            ({ f }) => useFunds(f), { initialProps: { f: { founder: 'X' } } },
        )
        await waitFor(() => expect(result.current.loading).toBe(false))
        // Yeni bir nesne ama AYNI degerler: sonsuz istek atmamali.
        rerender({ f: { founder: 'X' } })
        await waitFor(() => expect(apiClient.getFunds).toHaveBeenCalledTimes(1))
    })

    it('suzgec degisince yeniden cekiyor', async () => {
        const { result, rerender } = renderHook(
            ({ f }) => useFunds(f), { initialProps: { f: { founder: 'X' } } },
        )
        await waitFor(() => expect(result.current.loading).toBe(false))
        rerender({ f: { founder: 'Y' } })
        await waitFor(() => expect(apiClient.getFunds).toHaveBeenCalledTimes(2))
    })

    it('daralmis bir acilir liste oncekini silmiyor', async () => {
        /* Suzulmus bir sorgu daralmis bir kurucu listesi donduruyor;
           uzerine yazsaydik kullanici sectigi suzgeci geri alamazdi. */
        const { result, rerender } = renderHook(
            ({ f }) => useFunds(f), { initialProps: { f: {} as { founder?: string } } },
        )
        await waitFor(() => expect(result.current.founders).toHaveLength(2))
        vi.spyOn(apiClient, 'getFunds').mockResolvedValue(
            { ...PAYLOAD, founders: [], umbrellas: [] } as never,
        )
        rerender({ f: { founder: 'AK PORTFOY' } })
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.founders).toHaveLength(2)
    })

    it('hic fon yokken bos, ama suzgecliyken degil', async () => {
        vi.spyOn(apiClient, 'getFunds').mockResolvedValue(
            { items: [], founders: [], umbrellas: [], total: 0 } as never,
        )
        const { result } = renderHook(() => useFunds())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.empty).toBe(true)
    })

    it('suzgecli bos sonuc "hic fon yok" demek degil', async () => {
        vi.spyOn(apiClient, 'getFunds').mockResolvedValue(
            { items: [], founders: [], umbrellas: [], total: 0 } as never,
        )
        const { result } = renderHook(() => useFunds({ founder: 'YOK' }))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.empty).toBe(false)
    })

    it('eksik alanlar cokme yaratmiyor', async () => {
        vi.spyOn(apiClient, 'getFunds').mockResolvedValue({} as never)
        const { result } = renderHook(() => useFunds())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.funds).toEqual([])
    })

    it('ulasilamayan uc, bos listeden AYRI', async () => {
        vi.spyOn(apiClient, 'getFunds').mockRejectedValue(new Error('down'))
        const { result } = renderHook(() => useFunds())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(FUNDS_ERROR)
        expect(result.current.empty).toBe(false)
    })

    it('sokulmus bilesene gec gelen cevap yazilmiyor', async () => {
        let settle: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getFunds').mockReturnValue(
            new Promise((resolve) => { settle = resolve }) as never,
        )
        const { unmount } = renderHook(() => useFunds())
        unmount()
        settle(PAYLOAD)
        await waitFor(() => expect(apiClient.getFunds).toHaveBeenCalled())
    })

    it('sokulmus bilesene gec gelen HATA da yazilmiyor', async () => {
        let fail: (reason: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getFunds').mockReturnValue(
            new Promise((_r, reject) => { fail = reject }) as never,
        )
        const { unmount } = renderHook(() => useFunds())
        unmount()
        fail(new Error('down'))
        await waitFor(() => expect(apiClient.getFunds).toHaveBeenCalled())
    })
})

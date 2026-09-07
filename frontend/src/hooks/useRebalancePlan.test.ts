/**
 * Dengeleme planı ve satır satır emir akışı.
 *
 * Korunan iki özellik: bir satırın hatası diğerlerini DURDURMUYOR, ve
 * onaylanan bir satırdan sonra plan ZORUNLU yeniden yükleniyor -- portföy
 * değişti, eski planı ekranda bırakmak artık doğru olmayan bir farkı doğruymuş
 * gibi göstermek olurdu.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'

import { PLAN_ERROR, rowKey, useRebalancePlan } from './useRebalancePlan'
import { apiClient } from '../api/client'

const ROW = {
    symbol: 'THYAO',
    name: 'THYAO',
    bucket: 'bist_equity',
    label: 'BIST Hisse',
    side: 'SELL' as const,
    quantity: 12,
    price: 300,
    currency: 'TRY',
    amount_base: 3600,
    residual_base: 42,
    statement: 'THYAO için 12 adet satışın karşılığı 3.600,00 TRY.',
}

const PLAN = {
    hasTarget: true,
    totalValue: 24607.54,
    statement: 'Sapma ölçüldü.',
    disclaimer: 'Bu liste yatırım tavsiyesi değildir.',
    rows: [ROW],
    unresolved: [],
    rounding_residual_base: 42,
    buy_total_base: 0,
    usable_cash_base: 1000,
    blocked_cash_base: 0,
    warning: null,
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getRebalancePlan').mockResolvedValue(PLAN as never)
    vi.spyOn(apiClient, 'getCurrentUser').mockResolvedValue({ id: 'u-1' } as never)
    vi.spyOn(apiClient, 'stageTransaction').mockResolvedValue({
        status: 'PENDING_USER_CONFIRMATION',
        proposal_id: 'p-1',
    } as never)
    vi.spyOn(apiClient, 'confirmProposal').mockResolvedValue({} as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useRebalancePlan', () => {
    it('planı yükler', async () => {
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.plan?.rows).toHaveLength(1)
        expect(result.current.error).toBeNull()
    })

    it('yükleme düşerse tek satırlık hata verir', async () => {
        vi.spyOn(apiClient, 'getRebalancePlan').mockRejectedValue(new Error('x'))
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(PLAN_ERROR)
        expect(result.current.plan).toBeNull()
    })

    it('satır anahtarı kova, sembol ve yönü birlikte taşır', () => {
        expect(rowKey(ROW)).toBe('bist_equity:THYAO:SELL')
        expect(rowKey({ ...ROW, side: 'BUY' })).not.toBe(rowKey(ROW))
    })

    it('bir satırı onaylamak stage ve confirm çağırır', async () => {
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => {
            await result.current.confirmRow(ROW as never)
        })
        expect(apiClient.stageTransaction).toHaveBeenCalled()
        expect(apiClient.confirmProposal).toHaveBeenCalledWith('p-1')
    })

    it('onaydan sonra plan zorunlu yeniden yüklenir', async () => {
        // Portföy değişti: eski planı bırakmak, artık doğru olmayan bir farkı
        // doğruymuş gibi göstermek olurdu.
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => {
            await result.current.confirmRow(ROW as never)
        })
        await waitFor(() =>
            expect(apiClient.getRebalancePlan).toHaveBeenCalledTimes(2),
        )
    })

    it('hazırlanamayan bir öneri satırın hatası olur, tur düşmez', async () => {
        vi.spyOn(apiClient, 'stageTransaction').mockResolvedValue({
            status: 'REJECTED',
            blockers: ['Bakiye yetersiz.'],
        } as never)
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => {
            await result.current.confirmRow(ROW as never)
        })
        expect(result.current.rowState[rowKey(ROW)].status).toBe('error')
        expect(result.current.rowState[rowKey(ROW)].error).toContain('Bakiye')
        expect(result.current.failed).toBe(1)
    })

    it('blokersiz bir ret de anlaşılır bir mesaj verir', async () => {
        vi.spyOn(apiClient, 'stageTransaction').mockResolvedValue({
            status: 'REJECTED',
        } as never)
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => {
            await result.current.confirmRow(ROW as never)
        })
        expect(result.current.rowState[rowKey(ROW)].error).toBe('Öneri hazırlanamadı.')
    })

    it('mesajsız bir hata da satırda görünür', async () => {
        vi.spyOn(apiClient, 'confirmProposal').mockRejectedValue({})
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => {
            await result.current.confirmRow(ROW as never)
        })
        expect(result.current.rowState[rowKey(ROW)].error).toBe('Emir gönderilemedi.')
    })

    it('bir satırın hatası diğerlerini durdurmaz', async () => {
        const other = { ...ROW, symbol: 'ASELS' }
        let call = 0
        vi.spyOn(apiClient, 'stageTransaction').mockImplementation((() => {
            call += 1
            return call === 1
                ? Promise.resolve({ status: 'REJECTED', blockers: ['olmaz'] })
                : Promise.resolve({
                      status: 'PENDING_USER_CONFIRMATION',
                      proposal_id: 'p-2',
                  })
        }) as never)

        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => {
            await result.current.confirmRow(ROW as never)
        })
        await act(async () => {
            await result.current.confirmRow(other as never)
        })
        expect(result.current.failed).toBe(1)
        expect(result.current.confirmed).toBe(1)
    })

    it('plan yenilendiğinde başarı işareti düşer, sayaç kalır', async () => {
        // "Onaylandı" etiketini artık var olmayan bir satırın üzerinde
        // bırakmak yanıltırdı; ama sayaç satır durumundan sayılsaydı her
        // onaydan sonra sıfıra dönerdi.
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => {
            await result.current.confirmRow(ROW as never)
        })
        await waitFor(() =>
            expect(result.current.rowState[rowKey(ROW)]).toBeUndefined(),
        )
        expect(result.current.confirmed).toBe(1)
    })

    it('hatalı satır plan yenilense de durur', async () => {
        // Kullanıcı hangi satırın tutmadığını görüp yeniden deneyebilmeli.
        vi.spyOn(apiClient, 'stageTransaction').mockResolvedValue({
            status: 'REJECTED', blockers: ['olmaz'],
        } as never)
        const { result } = renderHook(() => useRebalancePlan())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await act(async () => {
            await result.current.confirmRow(ROW as never)
        })
        act(() => result.current.reload())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.rowState[rowKey(ROW)].status).toBe('error')
        expect(result.current.failed).toBe(1)
    })

    it('sökülen bileşende hata da yazılmaz', async () => {
        // İptal edilmiş bir istekten sonra durum güncellemek, React'in
        // uyarısını üretir ve düşen bileşene ait bir hatayı ekranda bırakır.
        let reject: (reason?: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getRebalancePlan').mockReturnValue(
            new Promise((_resolve, r) => {
                reject = r
            }) as never,
        )
        const { unmount } = renderHook(() => useRebalancePlan())
        unmount()
        await act(async () => {
            reject(new Error('x'))
        })
    })

    it('sökülen bileşen durumu güncellemez', async () => {
        let resolve: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getRebalancePlan').mockReturnValue(
            new Promise((r) => {
                resolve = r
            }) as never,
        )
        const { unmount } = renderHook(() => useRebalancePlan())
        unmount()
        await act(async () => {
            resolve(PLAN)
        })
    })
})

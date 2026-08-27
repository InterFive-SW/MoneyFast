/**
 * Gösterge panelindeki risk kartının veri katmanı.
 *
 * Korunan asıl özellik: panel ile risk sayfası aynı uç noktayı okur. İki
 * yüzeyin aynı portföy için farklı bir puan göstermesi, kullanıcının
 * hangisine güveneceğini bilememesi demekti.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { SUMMARY_ERROR, useRiskSummary } from './useRiskSummary'
import { apiClient } from '../api/client'

const PROFILE = {
    as_of: '2026-08-27T09:15:00Z',
    score: 83.4,
    level: 'Düşük',
    position_count: 14,
    suitability: {
        measured_level: 'Düşük',
        declared_tolerance: 'Orta',
        alignment: 'PORTFOLIO_CALMER',
        statement: 'Ölçülen portföy riskiniz "Düşük" seviyesinde.',
    },
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getRiskProfile').mockResolvedValue(PROFILE as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useRiskSummary', () => {
    it('puanı, seviyeyi ve karşılaştırmayı taşır', async () => {
        const { result } = renderHook(() => useRiskSummary())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.score).toBe(83.4)
        expect(result.current.level).toBe('Düşük')
        expect(result.current.suitability?.alignment).toBe('PORTFOLIO_CALMER')
        expect(result.current.hasPositions).toBe(true)
    })

    it('sayfayla aynı pencereyi ister', async () => {
        const { result } = renderHook(() => useRiskSummary('3M'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getRiskProfile).toHaveBeenCalledWith('3M')
    })

    it('varsayılan pencere sayfanınkiyle aynı', async () => {
        const { result } = renderHook(() => useRiskSummary())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getRiskProfile).toHaveBeenCalledWith('1Y')
    })

    it('ölçülemeyen puanı sıfıra çevirmez', async () => {
        /* 0, "en sakin" değil "en oynak" ucudur; boş bir portföyü oraya
           yazmak en riskli portföyle aynı sayıyı gösterirdi. */
        vi.mocked(apiClient.getRiskProfile).mockResolvedValue({
            ...PROFILE, score: null, level: null, position_count: 0,
        } as never)
        const { result } = renderHook(() => useRiskSummary())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.score).toBeNull()
        expect(result.current.level).toBeNull()
        expect(result.current.hasPositions).toBe(false)
    })

    it('anket doldurulmamışken karşılaştırma boş kalır', async () => {
        vi.mocked(apiClient.getRiskProfile).mockResolvedValue({
            ...PROFILE, suitability: null,
        } as never)
        const { result } = renderHook(() => useRiskSummary())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.suitability).toBeNull()
    })

    it('yüklenemezse söyler ve eski puanı bırakmaz', async () => {
        /* Donmuş bir puan, yanlış bir puandır. */
        vi.mocked(apiClient.getRiskProfile).mockRejectedValue(new Error('boom'))
        const { result } = renderHook(() => useRiskSummary())
        await waitFor(() => expect(result.current.error).toBe(SUMMARY_ERROR))
        expect(result.current.profile).toBeNull()
        expect(result.current.score).toBeNull()
    })

    it('şekli bozuk bir yanıt kartı çökertmez', async () => {
        vi.mocked(apiClient.getRiskProfile).mockResolvedValue({} as never)
        const { result } = renderHook(() => useRiskSummary())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.score).toBeNull()
        expect(result.current.hasPositions).toBe(false)
    })

    it('yeniden yüklenebilir', async () => {
        const { result } = renderHook(() => useRiskSummary())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await result.current.reload()
        expect(apiClient.getRiskProfile).toHaveBeenCalledTimes(2)
    })
})

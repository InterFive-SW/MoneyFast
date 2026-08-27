/**
 * Risk geçmişi.
 *
 * Korunan asıl özellik: tek noktadan eğilim üretilmez. Bir noktalı çizgi
 * "değişim yok" gibi okunur, oysa daha ölçülecek ikinci gün gelmemiştir —
 * ikisi farklı iddialar.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { HISTORY_ERROR, trendOf, useRiskHistory } from './useRiskHistory'
import { apiClient } from '../api/client'

function point(day: string, score: number | null) {
    return {
        captured_on: day, score, level: 'Düşük', volatility: 0.18,
        hhi: 0.16, max_drawdown: -0.11, position_count: 14,
    }
}

const SERIES = [point('2026-08-25', 80.0), point('2026-08-27', 83.4)]

beforeEach(() => {
    vi.spyOn(apiClient, 'getRiskHistory').mockResolvedValue({
        lookback: '1Y', days: 90, points: SERIES,
    })
})
afterEach(() => vi.restoreAllMocks())

describe('trendOf', () => {
    it('ilk ve son ölçüm arasındaki farkı verir', () => {
        expect(trendOf(SERIES).change).toBe(3.4)
        expect(trendOf(SERIES).first?.captured_on).toBe('2026-08-25')
        expect(trendOf(SERIES).last?.captured_on).toBe('2026-08-27')
    })

    it('tek ölçümden eğilim üretmez', () => {
        /* Bir noktadan eğilim çıkarmak, olmayan bir hareketi raporlamaktır. */
        const single = trendOf([point('2026-08-27', 83.4)])
        expect(single.change).toBeNull()
        expect(single.last?.score).toBe(83.4)
    })

    it('hiç ölçüm yoksa her şey boş kalır', () => {
        expect(trendOf([])).toEqual({ change: null, first: null, last: null })
    })

    it('ölçülemeyen günleri atlar', () => {
        /* Puanı null olan gün sıfır değil, yok. */
        const withGap = [point('2026-08-25', null), point('2026-08-26', 80.0),
                         point('2026-08-27', 83.4)]
        expect(trendOf(withGap).change).toBe(3.4)
        expect(trendOf(withGap).first?.captured_on).toBe('2026-08-26')
    })

    it('yalnızca ölçülemeyen günler varsa eğilim yoktur', () => {
        expect(trendOf([point('2026-08-25', null)]).change).toBeNull()
    })

    it('düşen puanı negatif farkla verir', () => {
        expect(trendOf([point('a', 90.0), point('b', 72.5)]).change).toBe(-17.5)
    })
})

describe('useRiskHistory', () => {
    it('seriyi yükler ve penceresini taşır', async () => {
        const { result } = renderHook(() => useRiskHistory())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.points).toHaveLength(2)
        expect(result.current.lookback).toBe('1Y')
        expect(result.current.hasSeries).toBe(true)
    })

    it('istenen gün sayısını geçirir', async () => {
        const { result } = renderHook(() => useRiskHistory(30))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getRiskHistory).toHaveBeenCalledWith(30)
    })

    it('tek noktalı seriyi çizilebilir saymaz', async () => {
        vi.mocked(apiClient.getRiskHistory).mockResolvedValue({
            lookback: '1Y', days: 90, points: [point('2026-08-27', 83.4)],
        })
        const { result } = renderHook(() => useRiskHistory())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.hasSeries).toBe(false)
        expect(result.current.trend.change).toBeNull()
    })

    it('henüz geçmiş yokken hata değil boş seri döner', async () => {
        vi.mocked(apiClient.getRiskHistory).mockResolvedValue({
            lookback: '1Y', days: 90, points: [],
        })
        const { result } = renderHook(() => useRiskHistory())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.points).toEqual([])
        expect(result.current.error).toBeNull()
    })

    it('yüklenemezse söyler', async () => {
        vi.mocked(apiClient.getRiskHistory).mockRejectedValue(new Error('boom'))
        const { result } = renderHook(() => useRiskHistory())
        await waitFor(() => expect(result.current.error).toBe(HISTORY_ERROR))
        expect(result.current.points).toEqual([])
    })

    it('şekli bozuk bir yanıt sayfayı çökertmez', async () => {
        vi.mocked(apiClient.getRiskHistory).mockResolvedValue({} as never)
        const { result } = renderHook(() => useRiskHistory())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.points).toEqual([])
        expect(result.current.lookback).toBe('')
    })

    it('yeniden yüklenebilir', async () => {
        const { result } = renderHook(() => useRiskHistory())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await result.current.reload()
        expect(apiClient.getRiskHistory).toHaveBeenCalledTimes(2)
    })
})

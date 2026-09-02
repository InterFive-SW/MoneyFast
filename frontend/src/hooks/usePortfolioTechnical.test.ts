/**
 * Portföy geneli teknik görünüm panelinin veri katmanı.
 *
 * Korunan asıl şey: cümle burada ÜRETİLMİYOR, okunuyor. `statement` ve satır
 * başına `narrative` backend'de kuruluyor ve sohbet de aynı uç noktadan aynı
 * cümleyi alıyor; istemcide ikinci bir üretici, iki yüzeyin aynı ölçümü
 * farklı anlatması demekti.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { TECHNICAL_ERROR, TREND_LABEL, usePortfolioTechnical } from './usePortfolioTechnical'
import { apiClient } from '../api/client'

const STATEMENT =
    "3 pozisyonunuzun 2'si 50 günlük ortalamasının altında (portföy değerinin %95,1'i)."

const DATA = {
    base_currency: 'TRY',
    positions: [
        { symbol: 'AKBNK', name: 'Akbank', currency: 'TRY', value: 1000,
          signals: { trend: 'UPTREND', pct_from_sma_50: 1.3 }, narrative: 'AKBNK, ...' },
        { symbol: 'AEFES', name: 'Anadolu Efes', currency: 'TRY', value: 9000,
          signals: { trend: 'DOWNTREND', pct_from_sma_50: -9.1 }, narrative: 'AEFES, ...' },
    ],
    summary: {
        position_count: 3, measured_count: 3, unmeasured_symbols: [],
        by_trend: { UPTREND: 1, DOWNTREND: 2, SIDEWAYS: 0 },
        below_sma_50: 2, above_sma_50: 1, weight_below_sma_50: 0.951,
        statement: STATEMENT,
    },
    unconvertible: [],
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getPortfolioTechnical').mockResolvedValue(DATA as never)
})
afterEach(() => vi.restoreAllMocks())

describe('usePortfolioTechnical', () => {
    it('cümleyi backendden okur, yeniden yazmaz', async () => {
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.data?.summary.statement).toBe(STATEMENT)
    })

    it('sayı ile değer payını ayrı taşır', async () => {
        // İkisi zıt yönü gösteriyor: iki pozisyon altta ama değerin %95'i.
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.data?.summary.below_sma_50).toBe(2)
        expect(result.current.data?.summary.weight_below_sma_50).toBe(0.951)
    })

    it('satırları değere göre sıralar, büyük pozisyon üstte', async () => {
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.rows.map((r) => r.symbol)).toEqual(['AEFES', 'AKBNK'])
    })

    it('değeri bilinmeyen pozisyonu sona atar ama düşürmez', async () => {
        // Listeden çıkarmak onu portföyde yokmuş gibi gösterirdi.
        // Değeri bilinmeyen iki pozisyon, listenin iki ucunda: sıralayıcı
        // eksik değeri hem soldaki hem sağdaki taraf olarak görmeli.
        vi.spyOn(apiClient, 'getPortfolioTechnical').mockResolvedValue({
            ...DATA,
            positions: [
                { ...DATA.positions[0], symbol: 'AAPL', value: null },
                DATA.positions[1],
                { ...DATA.positions[0], symbol: 'MSFT', value: null },
            ],
        } as never)
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.rows[0].symbol).toBe('AEFES')
        expect(result.current.rows.map((r) => r.symbol).slice(1).sort())
            .toEqual(['AAPL', 'MSFT'])
    })

    it('kuru olmayan pozisyon varsa yüzdenin neyi kapsadığını yazar', async () => {
        vi.spyOn(apiClient, 'getPortfolioTechnical').mockResolvedValue({
            ...DATA, unconvertible: ['AAPL', 'MSFT'],
        } as never)
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.coverageNote).toContain('AAPL, MSFT')
        expect(result.current.coverageNote).toContain('kur bulunamadı')
    })

    it('her pozisyon çevrilebiliyorsa uyarı yazmaz', async () => {
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.coverageNote).toBeNull()
    })

    it('özet bloğu hiç gelmediyse panel çökmez', async () => {
        // Ölçüm gösterememek, sayfayı kaybetmekten iyidir.
        vi.spyOn(apiClient, 'getPortfolioTechnical').mockResolvedValue({} as never)
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.summary).toBeNull()
        expect(result.current.rows).toEqual([])
    })

    it('boş portföyde satır yok ama hata da yok', async () => {
        vi.spyOn(apiClient, 'getPortfolioTechnical').mockResolvedValue({
            base_currency: 'TRY', positions: [], unconvertible: [],
            summary: { ...DATA.summary, position_count: 0, statement: null },
        } as never)
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.rows).toEqual([])
        expect(result.current.error).toBeNull()
    })

    it('uç düşerse hata söyler ve eski ölçümü göstermez', async () => {
        vi.spyOn(apiClient, 'getPortfolioTechnical').mockRejectedValue(new Error('500'))
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(TECHNICAL_ERROR)
        expect(result.current.data).toBeNull()
        expect(result.current.rows).toEqual([])
        expect(result.current.coverageNote).toBeNull()
    })

    it('yeniden yükleme aynı ucu tekrar okur', async () => {
        const read = vi.spyOn(apiClient, 'getPortfolioTechnical')
            .mockResolvedValue(DATA as never)
        const { result } = renderHook(() => usePortfolioTechnical())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await result.current.reload()
        expect(read).toHaveBeenCalledTimes(2)
    })

    it('ölçülemeyen eğilim için de bir etiketi vardır', async () => {
        // "Ölçülemedi", boş bir rozet ya da "Yatay" değil: ikincisi ölçülmüş
        // bir yön iddiası olurdu.
        expect(TREND_LABEL.UNKNOWN).toBe('Ölçülemedi')
        expect(Object.keys(TREND_LABEL)).toHaveLength(4)
    })
})

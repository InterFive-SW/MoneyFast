/**
 * "Portföyünüze dokunan haberler" panelinin veri katmanı.
 *
 * Korunan asıl ayrım: HATA ile BOŞ SONUÇ aynı şey değil. "Bu pencerede
 * hisselerinize dair haber eşleşmedi" ölçülmüş bir cevap; ulaşılamayan bir uç
 * ise ölçüm değil. İkisini aynı boş listeye indirmek, kullanıcıya olmayan bir
 * sessizlik bildirmek olurdu.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, waitFor } from '@testing-library/react'
import { NEWS_ERROR, usePortfolioNews } from './usePortfolioNews'
import { apiClient } from '../api/client'

const NEWS = {
    windowDays: 90,
    symbols: [
        { symbol: 'AKBNK', name: 'Akbank T.A.Ş.', count: 2 },
        { symbol: 'DOAS', name: 'Doğuş Otomotiv', count: 0 },
        { symbol: 'AEFES', name: 'Anadolu Efes', count: 0 },
    ],
    items: [
        {
            id: 'n1',
            source: 'Patronlar Dünyası - Borsa',
            title: "BIST 100 değer kaybetti",
            url: 'https://example.invalid/n1',
            time: '2 gün önce',
            publishedAt: '2026-08-30T09:00:00Z',
            sentiment: 'neutral',
            relatedSymbols: ['AKBNK', 'THYAO', 'SASA'],
            heldSymbols: ['AKBNK'],
        },
    ],
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getPortfolioNews').mockResolvedValue(NEWS as never)
})
afterEach(() => vi.restoreAllMocks())

describe('usePortfolioNews', () => {
    it('haberleri ve pencereyi taşır', async () => {
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.news?.windowDays).toBe(90)
        expect(result.current.news?.items).toHaveLength(1)
        expect(result.current.error).toBeNull()
    })

    it('haberi olmayan pozisyonları ayrıca sayar', async () => {
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.quietSymbols).toEqual(['DOAS', 'AEFES'])
    })

    it('bir haberin YALNIZCA sahip olunan hisselerini yazar', async () => {
        // Haber üç şirketi anıyor; kullanıcı birine sahip. Üçünü de yazmak,
        // sahip olunmayan hisseleri portföydeymiş gibi gösterirdi.
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.heldLabel(result.current.news!.items[0])).toBe('AKBNK')
    })

    it('birden çok pozisyona dokunan haberi hepsiyle etiketler', async () => {
        vi.spyOn(apiClient, 'getPortfolioNews').mockResolvedValue({
            ...NEWS,
            items: [{ ...NEWS.items[0], heldSymbols: ['AKBNK', 'DOAS'] }],
        } as never)
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.heldLabel(result.current.news!.items[0])).toBe('AKBNK, DOAS')
    })

    it('etiketi olmayan bir satırda boş bir metin döner, çökmez', async () => {
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.heldLabel({ heldSymbols: undefined } as never)).toBe('')
    })

    it('portföy boşsa hisse yok der, haber yok demez', async () => {
        // Panel bu durumda haberden değil, portföyden bahsetmeli: hiç
        // pozisyonu olmayan birine "haber eşleşmedi" demek, bakılacak bir şey
        // varmış izlenimi verir.
        vi.spyOn(apiClient, 'getPortfolioNews').mockResolvedValue({
            windowDays: 90, symbols: [], items: [],
        } as never)
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.hasHoldings).toBe(false)
        expect(result.current.quietSymbols).toEqual([])
    })

    it('hiçbir haber eşleşmediğinde bu bir hata değildir', async () => {
        vi.spyOn(apiClient, 'getPortfolioNews').mockResolvedValue({
            windowDays: 90,
            symbols: [{ symbol: 'DOAS', name: 'Doğuş Otomotiv', count: 0 }],
            items: [],
        } as never)
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBeNull()
        expect(result.current.hasHoldings).toBe(true)
        expect(result.current.news?.items).toEqual([])
    })

    it('uç düşerse hata söyler ve eski listeyi göstermez', async () => {
        vi.spyOn(apiClient, 'getPortfolioNews').mockRejectedValue(new Error('500'))
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(NEWS_ERROR)
        expect(result.current.news).toBeNull()
        expect(result.current.quietSymbols).toEqual([])
        expect(result.current.hasHoldings).toBe(false)
    })

    it('yeniden yükleme aynı ucu tekrar okur', async () => {
        const read = vi.spyOn(apiClient, 'getPortfolioNews').mockResolvedValue(NEWS as never)
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        await result.current.reload()
        expect(read).toHaveBeenCalledTimes(2)
    })
})

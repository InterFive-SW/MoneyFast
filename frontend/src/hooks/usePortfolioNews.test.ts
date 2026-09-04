/**
 * "Portföyünüze dokunan haberler" panelinin veri katmanı.
 *
 * Korunan asıl ayrım: HATA ile BOŞ SONUÇ aynı şey değil. "Bu pencerede
 * hisselerinize dair haber eşleşmedi" ölçülmüş bir cevap; ulaşılamayan bir uç
 * ise ölçüm değil. İkisini aynı boş listeye indirmek, kullanıcıya olmayan bir
 * sessizlik bildirmek olurdu.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'
import { NEWS_ERROR, usePortfolioNews } from './usePortfolioNews'
import { apiClient } from '../api/client'

const NEWS = {
    windowDays: 90,
    symbols: [
        { symbol: 'AKBNK', name: 'Akbank T.A.Ş.', count: 2 },
        { symbol: 'GARAN', name: 'Garanti BBVA', count: 1 },
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
        {
            id: 'n2',
            source: 'KAP',
            title: 'GARAN — Kredi Komitesi Üye Değişikliği',
            url: 'https://example.invalid/n2',
            time: '16 saat önce',
            publishedAt: '2026-09-03T06:00:00Z',
            sentiment: 'neutral',
            relatedSymbols: ['GARAN'],
            heldSymbols: ['GARAN'],
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
        expect(result.current.news?.items).toHaveLength(2)
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

describe('sembol süzgeci', () => {
    it('seçim yokken liste olduğu gibi', async () => {
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.selected).toEqual([])
        expect(result.current.visibleItems).toHaveLength(2)
    })

    it('bir rozete basınca liste o hisseye iniyor', async () => {
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggleSymbol('GARAN'))
        expect(result.current.selected).toEqual(['GARAN'])
        expect(result.current.visibleItems.map((item) => item.id)).toEqual(['n2'])
    })

    it('ikinci rozet listeyi DARALTMIYOR, genişletiyor', async () => {
        /* Seçim birleşim, kesişim değil: "GARAN ve AKBNK" diyen kullanıcı
           ikisine birden dokunan haberi değil, ikisinden herhangi birine
           dokunanları soruyor. */
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggleSymbol('GARAN'))
        act(() => result.current.toggleSymbol('AKBNK'))
        expect(result.current.visibleItems).toHaveLength(2)
    })

    it('aynı rozete tekrar basmak seçimi kaldırıyor', async () => {
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggleSymbol('GARAN'))
        act(() => result.current.toggleSymbol('GARAN'))
        expect(result.current.selected).toEqual([])
        expect(result.current.visibleItems).toHaveLength(2)
    })

    it('"Tümü" süzgeci sıfırlıyor', async () => {
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggleSymbol('GARAN'))
        act(() => result.current.clearSelection())
        expect(result.current.selected).toEqual([])
        expect(result.current.visibleItems).toHaveLength(2)
    })

    it('haberi olmayan bir hisse seçilince liste boşalıyor', async () => {
        /* Bu doğru cevap: "DOAS için bu pencerede haber yok" ölçülmüş bir
           sessizlik ve rozetteki 0 zaten onu söylüyor. */
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggleSymbol('DOAS'))
        expect(result.current.visibleItems).toEqual([])
    })

    it('etiketi olmayan haber hiçbir süzgeçten geçmiyor', async () => {
        vi.spyOn(apiClient, 'getPortfolioNews').mockResolvedValue({
            ...NEWS,
            items: [{ ...NEWS.items[0], heldSymbols: undefined }],
        } as never)
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggleSymbol('AKBNK'))
        expect(result.current.visibleItems).toEqual([])
    })

    it('veri yokken süzgeç boş liste veriyor', async () => {
        vi.spyOn(apiClient, 'getPortfolioNews').mockRejectedValue(new Error('down'))
        const { result } = renderHook(() => usePortfolioNews())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(NEWS_ERROR)
        expect(result.current.visibleItems).toEqual([])
    })
})

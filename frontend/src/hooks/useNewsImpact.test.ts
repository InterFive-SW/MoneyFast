/**
 * Haber okumasının ölçülen zemini.
 *
 * Korunan üç özellik: **panel yorum taşımıyor** (yorum sohbet turunda,
 * uygunluk kapısından geçmiş hâliyle), **bir hareket ancak kendi aralığına
 * karşı okunuyor** (tipik hareket ölçülemediğinde büyüklük hakkında hiçbir
 * şey denmiyor), ve **kapsama saklanmıyor** (listelenenlerin portföyün
 * tamamı olduğunu sanan bir okuyucu, dar bir kapsamı geniş sanır).
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'

import {
    IMPACT_ERROR,
    IMPACT_WINDOWS,
    coverageStatement,
    moveStatement,
    useNewsImpact,
} from './useNewsImpact'
import { apiClient } from '../api/client'

const ROW = {
    symbol: 'AKBNK',
    name: 'Akbank',
    sector: 'Financial Services',
    news_count: 114,
    filing_count: 25,
    price: { recent_move_pct: 1.11, typical_move_pct: 4.42, window_days: 5 },
    fundamentals: { pe_ratio: 4.2 },
    articles: [
        {
            id: 'n1', title: 'AK PORTFÖY — Genel Bilgi Formu', source: 'KAP',
            published_at: '2026-09-07T10:00:00Z', is_filing: true,
        },
    ],
}

const PACKAGE = {
    window_days: 90,
    symbols: [ROW],
    coverage: {
        articles: 200, filings: 148, feed_articles: 52,
        symbols: 16, symbols_with_news: 15, symbols_omitted: 11,
    },
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getNewsImpact').mockResolvedValue(PACKAGE as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useNewsImpact', () => {
    it('paketi yükler', async () => {
        const { result } = renderHook(() => useNewsImpact())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.rows).toHaveLength(1)
        expect(result.current.error).toBeNull()
    })

    it('varsayılan pencere doksan gün', async () => {
        // Daha kısası "daha güncel" DEĞİL, daha boş.
        const { result } = renderHook(() => useNewsImpact())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getNewsImpact).toHaveBeenCalledWith(90, 5)
    })

    it('pencere değiştirmek yeniden ölçer', async () => {
        const { result } = renderHook(() => useNewsImpact())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.setDays(30))
        await waitFor(() => expect(apiClient.getNewsImpact).toHaveBeenCalledWith(30, 5))
    })

    it('kapsama saklanmıyor', async () => {
        const { result } = renderHook(() => useNewsImpact())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.coverage?.symbols_omitted).toBe(11)
    })

    it('aynı anda tek satırın başlıkları açık', async () => {
        const { result } = renderHook(() => useNewsImpact())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggle('AKBNK'))
        expect(result.current.expanded).toBe('AKBNK')
        act(() => result.current.toggle('GARAN'))
        expect(result.current.expanded).toBe('GARAN')
    })

    it('açık satıra ikinci kez basmak kapatır', async () => {
        const { result } = renderHook(() => useNewsImpact())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggle('AKBNK'))
        act(() => result.current.toggle('AKBNK'))
        expect(result.current.expanded).toBeNull()
    })

    it('boş gövde çökmez', async () => {
        vi.spyOn(apiClient, 'getNewsImpact').mockResolvedValue({} as never)
        const { result } = renderHook(() => useNewsImpact())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.rows).toEqual([])
        expect(result.current.coverage).toBeNull()
    })

    it('hata tek satırlık bir mesaj olur', async () => {
        vi.spyOn(apiClient, 'getNewsImpact').mockRejectedValue(new Error('x'))
        const { result } = renderHook(() => useNewsImpact())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(IMPACT_ERROR)
    })

    it('sökülen bileşen durumu güncellemez', async () => {
        let resolve: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getNewsImpact').mockReturnValue(
            new Promise((r) => {
                resolve = r
            }) as never,
        )
        const { unmount } = renderHook(() => useNewsImpact())
        unmount()
        await act(async () => {
            resolve(PACKAGE)
        })
    })

    it('sökülen bileşende hata da yazılmaz', async () => {
        let reject: (reason?: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getNewsImpact').mockReturnValue(
            new Promise((_resolve, r) => {
                reject = r
            }) as never,
        )
        const { unmount } = renderHook(() => useNewsImpact())
        unmount()
        await act(async () => {
            reject(new Error('x'))
        })
    })
})

describe('moveStatement', () => {
    it('hareketi kendi aralığına karşı yazar', () => {
        // "%5 düştü" tek başına hiçbir şey söylemiyor.
        const text = moveStatement(ROW as never)
        expect(text).toContain('%1,11 yükseldi')
        expect(text).toContain('tipik olarak %4,42')
    })

    it('düşüşü düşüş diye yazar', () => {
        const text = moveStatement({
            ...ROW, price: { ...ROW.price, recent_move_pct: -2.4 },
        } as never)
        expect(text).toContain('%2,40 geriledi')
    })

    it('tipik hareket ölçülemediğinde hiçbir şey yazmaz', () => {
        // Büyüklük hakkında söylenecek bir şey yok.
        expect(moveStatement({
            ...ROW, price: { ...ROW.price, typical_move_pct: null },
        } as never)).toBeNull()
    })

    it('gerçekleşen hareket ölçülemediğinde hiçbir şey yazmaz', () => {
        expect(moveStatement({
            ...ROW, price: { ...ROW.price, recent_move_pct: null },
        } as never)).toBeNull()
    })
})

describe('coverageStatement', () => {
    it('kaynak kırılımını yazar', () => {
        // Bildirimin ihraççısı makine okunur bir alanda; besleme haberi
        // metinden eşleştirildi.
        const text = coverageStatement(PACKAGE.coverage as never)
        expect(text).toContain('148 bildirim ve 52 haber okundu')
    })

    it('dışarıda kalan pozisyonları söyler', () => {
        expect(coverageStatement(PACKAGE.coverage as never)).toContain(
            '16 pozisyonun 11 tanesi bu listede yok',
        )
    })

    it('hiçbiri dışarıda kalmadıysa o cümleyi kurmaz', () => {
        const text = coverageStatement({
            ...PACKAGE.coverage, symbols_omitted: 0,
        } as never)
        expect(text).not.toContain('listede yok')
    })

    it('kapsama yoksa cümle de yok', () => {
        expect(coverageStatement(null)).toBeNull()
    })
})

describe('IMPACT_WINDOWS', () => {
    it('seçenekler arasında bir yargı sözcüğü yok', () => {
        for (const window of IMPACT_WINDOWS) {
            const lowered = window.label.toLowerCase()
            for (const banned of ['en iyi', 'öneri', 'fırsat', 'olumlu']) {
                expect(lowered).not.toContain(banned)
            }
        }
    })
})

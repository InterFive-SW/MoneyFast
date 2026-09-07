/**
 * Haber yorumu beslemeleri.
 *
 * Korunan üç özellik: cümle SUNUCUDAN gelir ve burada yeniden kurulmaz,
 * çekincenin arayüzde YEDEĞİ YOKTUR (yazılı bir kopya sunucudaki metin
 * değiştiğinde sessizce eskir), ve aynı anda yalnızca TEK satırın gerekçeleri
 * açıktır.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'

import { DIGEST_ERROR, DIGEST_WINDOWS, useNewsDigest, useNewsImpactSummary } from './useNewsDigest'
import { apiClient } from '../api/client'

const ENTRY = {
    symbol: 'ASELS',
    sentence: 'ASELS: 2 haber yorumu, yükseliş yönünde okundu.',
    counts: { UP: 2, DOWN: 0, NEUTRAL: 0 },
    directCount: 2,
    spilloverCount: 0,
    measured: { typicalMovePct: 3.1, recentMovePct: 1.2 },
    reasons: [
        { newsId: 'n1', direction: 'UP', scope: 'DIRECT', magnitude: 'HIGH',
          mechanism: 'Sözleşme tutarı yıllık ihracata ekleniyor.',
          publishedAt: '2026-09-07T10:00:00Z' },
    ],
}

const DIGEST = {
    headline: 'Son 24 saatte portföyünüzdeki 1 enstrüman haberlere konu oldu.',
    entries: [ENTRY],
    windowHours: 24,
    disclaimer: 'Bu özet yapay zeka yorumudur.',
}

const SUMMARY = { entries: [ENTRY], windowHours: 24, disclaimer: DIGEST.disclaimer }

beforeEach(() => {
    vi.spyOn(apiClient, 'getNewsDigest').mockResolvedValue(DIGEST as never)
    vi.spyOn(apiClient, 'getNewsImpactSummary').mockResolvedValue(SUMMARY as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useNewsDigest', () => {
    it('özeti yükler', async () => {
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.entries).toHaveLength(1)
        expect(result.current.headline).toContain('1 enstrüman')
        expect(result.current.error).toBeNull()
    })

    it('cümle sunucudan gelir, burada kurulmaz', async () => {
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.entries[0].sentence).toBe(ENTRY.sentence)
    })

    it('çekincenin arayüzde yedeği yoktur', async () => {
        // Yazılı bir kopya, sunucudaki metin değiştiğinde sessizce eskirdi.
        vi.spyOn(apiClient, 'getNewsDigest').mockResolvedValue({
            ...DIGEST, disclaimer: undefined,
        } as never)
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.disclaimer).toBe('')
    })

    it('varsayılan pencere 24 saattir', async () => {
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getNewsDigest).toHaveBeenCalledWith(24)
    })

    it('pencere değiştirmek yeniden okur', async () => {
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.setHours(168))
        await waitFor(() => expect(apiClient.getNewsDigest).toHaveBeenCalledWith(168))
    })

    it('aynı anda tek satırın gerekçeleri açıktır', async () => {
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggle('ASELS'))
        expect(result.current.expanded).toBe('ASELS')
        act(() => result.current.toggle('THYAO'))
        expect(result.current.expanded).toBe('THYAO')
    })

    it('açık satıra ikinci kez basmak kapatır', async () => {
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.toggle('ASELS'))
        act(() => result.current.toggle('ASELS'))
        expect(result.current.expanded).toBeNull()
    })

    it('boş gövde çökmez', async () => {
        vi.spyOn(apiClient, 'getNewsDigest').mockResolvedValue({} as never)
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.entries).toEqual([])
        expect(result.current.headline).toBe('')
    })

    it('başlığı null gelen bir gövde boş başlık olur', async () => {
        vi.spyOn(apiClient, 'getNewsDigest').mockResolvedValue({
            ...DIGEST, headline: null,
        } as never)
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.headline).toBe('')
    })

    it('hata tek satırlık bir mesaj olur', async () => {
        vi.spyOn(apiClient, 'getNewsDigest').mockRejectedValue(new Error('x'))
        const { result } = renderHook(() => useNewsDigest())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(DIGEST_ERROR)
    })

    it('sökülen bileşen durumu güncellemez', async () => {
        let resolve: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getNewsDigest').mockReturnValue(
            new Promise((r) => {
                resolve = r
            }) as never,
        )
        const { unmount } = renderHook(() => useNewsDigest())
        unmount()
        await act(async () => {
            resolve(DIGEST)
        })
    })

    it('sökülen bileşende hata da yazılmaz', async () => {
        let reject: (reason?: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getNewsDigest').mockReturnValue(
            new Promise((_resolve, r) => {
                reject = r
            }) as never,
        )
        const { unmount } = renderHook(() => useNewsDigest())
        unmount()
        await act(async () => {
            reject(new Error('x'))
        })
    })
})

describe('useNewsImpactSummary', () => {
    it('piyasa genelini yükler ve limit taşır', async () => {
        const { result } = renderHook(() => useNewsImpactSummary(24, 8))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getNewsImpactSummary).toHaveBeenCalledWith(24, 8)
        expect(result.current.entries).toHaveLength(1)
    })

    it('portföy başlığı yoktur: özetlenecek bir portföy yok', async () => {
        const { result } = renderHook(() => useNewsImpactSummary())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.headline).toBe('')
    })
})

describe('DIGEST_WINDOWS', () => {
    it('seçenekler arasında bir yargı sözcüğü yok', () => {
        for (const window of DIGEST_WINDOWS) {
            const lowered = window.label.toLowerCase()
            for (const banned of ['en iyi', 'öneri', 'fırsat', 'cazip']) {
                expect(lowered).not.toContain(banned)
            }
        }
    })
})

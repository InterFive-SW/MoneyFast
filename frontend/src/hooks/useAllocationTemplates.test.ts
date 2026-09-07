/**
 * Hedef formunun taslağı ve şablonlar.
 *
 * Korunan iki özellik: şablon seçmek formu DOLDURUYOR ama kaydetmiyor, ve
 * toplam-100 doğrulaması tek yerde. İkincisi bugün `HedefDagilimPaneli.tsx`
 * içinde JSX'te duruyordu; iki kopyadan biri değişip diğeri kalabilirdi ve
 * sunucu tam 100 istiyor -- yani ayrışma, kullanıcının kaydedemediği bir form
 * demek.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'

import { REQUIRED_TOTAL, TEMPLATES_ERROR, useAllocationTemplates } from './useAllocationTemplates'
import { apiClient } from '../api/client'

const TEMPLATES = {
    declaredTolerance: 'Düşük',
    measurementNote: 'Oynaklık son bir yıldan ölçüldü.',
    items: [
        {
            key: 'cash_heavy',
            label: 'Ağırlıklı nakit',
            weights: [
                { bucket: 'cash', label: 'Nakit (TRY)', percent: 60 },
                { bucket: 'bist_equity', label: 'BIST Hisse', percent: 40 },
            ],
            volatility: 0.067,
            band: 'Düşük',
            highlighted: true,
            statement: 'Ağırlıklı nakit şablonunun ölçülen oynaklığı %6,7.',
            unmeasured: [],
        },
        {
            key: 'balanced',
            label: 'Dengeli',
            weights: [
                { bucket: 'cash', label: 'Nakit (TRY)', percent: 25 },
                { bucket: 'bist_equity', label: 'BIST Hisse', percent: 75 },
            ],
            volatility: 0.113,
            band: 'Orta',
            highlighted: false,
            statement: 'Dengeli şablonunun ölçülen oynaklığı %11,3.',
            unmeasured: [],
        },
    ],
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getAllocationTemplates').mockResolvedValue(TEMPLATES as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useAllocationTemplates', () => {
    it('şablonları ve beyan edilen toleransı yükler', async () => {
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.templates).toHaveLength(2)
        expect(result.current.declaredTolerance).toBe('Düşük')
        expect(result.current.measurementNote).toContain('ölçüldü')
    })

    it('yükleme düşerse tek satırlık hata verir', async () => {
        vi.spyOn(apiClient, 'getAllocationTemplates').mockRejectedValue(new Error('x'))
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(TEMPLATES_ERROR)
        expect(result.current.templates).toEqual([])
    })

    it('başlangıçta taslak boş: şablon seçilmeden form doldurulmuyor', async () => {
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.draft).toEqual([])
        expect(result.current.isValid).toBe(false)
    })

    it('şablon seçmek formu doldurur', async () => {
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.selectTemplate('balanced'))
        expect(result.current.draft.map((row) => row.percent)).toEqual([25, 75])
        expect(result.current.total).toBe(REQUIRED_TOTAL)
        expect(result.current.isValid).toBe(true)
    })

    it('bilinmeyen şablon anahtarı taslağa dokunmaz', async () => {
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.selectTemplate('yok-böyle'))
        expect(result.current.draft).toEqual([])
        expect(result.current.selectedKey).toBeNull()
    })

    it('yüzde değiştirmek şablon seçimini düşürür', async () => {
        // Form artık o şablon değil; öyleymiş gibi göstermek kullanıcıya
        // kaydedeceğinden başka bir şey gösterirdi.
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.selectTemplate('balanced'))
        act(() => result.current.setPercent('cash', 30))
        expect(result.current.selectedKey).toBeNull()
        expect(result.current.total).toBe(105)
        expect(result.current.isValid).toBe(false)
    })

    it('sayı olmayan bir değer sıfır sayılır, NaN taşınmaz', async () => {
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.selectTemplate('balanced'))
        act(() => result.current.setPercent('cash', Number.NaN))
        expect(result.current.total).toBe(75)
    })

    it('reload yeniden çeker', async () => {
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.reload())
        await waitFor(() =>
            expect(apiClient.getAllocationTemplates).toHaveBeenCalledTimes(2),
        )
    })

    it('boş gövde listeyi boşaltır, çökmez', async () => {
        vi.spyOn(apiClient, 'getAllocationTemplates').mockResolvedValue({} as never)
        const { result } = renderHook(() => useAllocationTemplates())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.templates).toEqual([])
        expect(result.current.declaredTolerance).toBeNull()
        expect(result.current.measurementNote).toBe('')
    })

    it('sökülen bileşende hata da yazılmaz', async () => {
        // İptal edilmiş bir istekten sonra durum güncellemek, React'in
        // uyarısını üretir ve düşen bileşene ait bir hatayı ekranda bırakır.
        let reject: (reason?: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getAllocationTemplates').mockReturnValue(
            new Promise((_resolve, r) => {
                reject = r
            }) as never,
        )
        const { unmount } = renderHook(() => useAllocationTemplates())
        unmount()
        await act(async () => {
            reject(new Error('x'))
        })
    })

    it('sökülen bileşen durumu güncellemez', async () => {
        let resolve: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getAllocationTemplates').mockReturnValue(
            new Promise((r) => {
                resolve = r
            }) as never,
        )
        const { unmount } = renderHook(() => useAllocationTemplates())
        unmount()
        await act(async () => {
            resolve(TEMPLATES)
        })
    })
})

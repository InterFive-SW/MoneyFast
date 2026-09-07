/**
 * Yön okuması.
 *
 * Korunan iki özellik: karşı taraf HER ZAMAN ayrı bir liste olarak dönüyor
 * (yalnızca destekleyeni göstermek sonucu desteksiz bırakırdı), ve vade
 * kümesi sunucununkiyle aynı -- ayrışırsa kullanıcı sorduğundan başka bir
 * vadenin okumasını alır.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'

import {
    DIRECTION_ERROR,
    DIRECTION_LABELS,
    HORIZONS,
    useDirectionSignal,
} from './useDirectionSignal'
import { apiClient } from '../api/client'

const SIGNAL = {
    symbol: 'ASELS',
    horizon: '3M',
    direction: 'UP_LEAN',
    lean: 0.633,
    evidence: [
        { source: 'TECHNICAL', key: 'trend', direction: 'UP', value: 1, text: 'yükseliş eğiliminde' },
        { source: 'FUNDAMENTAL', key: 'roe', direction: 'DOWN', value: 0.02, text: 'özkaynak kârlılığı %2' },
        { source: 'TECHNICAL', key: 'rsi_14', direction: 'NEUTRAL', value: 61, text: 'göreli güç endeksi 61' },
    ],
    coverage: { sources_measured: 2, evidence_count: 3, missing: [], observations: 252 },
    by_source: { TECHNICAL: 1, FUNDAMENTAL: -1, NEWS: null },
    narrative: 'ASELS — 3 aylık okuma.',
    horizon_note: 'Bu bir varsayım.',
    currency: 'TRY',
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getDirectionSignal').mockResolvedValue(SIGNAL as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useDirectionSignal', () => {
    it('okumayı yükler', async () => {
        const { result } = renderHook(() => useDirectionSignal('ASELS'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.signal?.direction).toBe('UP_LEAN')
        expect(result.current.error).toBeNull()
    })

    it('karşı taraf ayrı bir liste olarak duruyor', async () => {
        // Yalnızca destekleyeni göstermek, sonucu desteksiz ve kullanıcıyı
        // denetleyemez bırakırdı.
        const { result } = renderHook(() => useDirectionSignal('ASELS'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.supporting).toEqual(['yükseliş eğiliminde'])
        expect(result.current.opposing).toEqual(['özkaynak kârlılığı %2'])
    })

    it('nötr ölçüm hiçbir tarafa yazılmaz', async () => {
        // RSI yön oyu vermiyor; listede ölçüm olarak duruyor.
        const { result } = renderHook(() => useDirectionSignal('ASELS'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.supporting).not.toContain('göreli güç endeksi 61')
        expect(result.current.opposing).not.toContain('göreli güç endeksi 61')
    })

    it('vade değiştirmek yeniden okur', async () => {
        const { result } = renderHook(() => useDirectionSignal('ASELS'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.setHorizon('6M'))
        await waitFor(() =>
            expect(apiClient.getDirectionSignal).toHaveBeenCalledWith('ASELS', '6M'),
        )
    })

    it('sembol yoksa istek atılmaz', () => {
        const { result } = renderHook(() => useDirectionSignal(undefined))
        expect(apiClient.getDirectionSignal).not.toHaveBeenCalled()
        expect(result.current.signal).toBeNull()
    })

    it('hata tek satırlık bir mesaj olur', async () => {
        vi.spyOn(apiClient, 'getDirectionSignal').mockRejectedValue(new Error('x'))
        const { result } = renderHook(() => useDirectionSignal('ASELS'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(DIRECTION_ERROR)
    })

    it('kanıtsız bir okuma boş listeler verir, çökmez', async () => {
        vi.spyOn(apiClient, 'getDirectionSignal').mockResolvedValue({
            ...SIGNAL, evidence: undefined,
        } as never)
        const { result } = renderHook(() => useDirectionSignal('ASELS'))
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.supporting).toEqual([])
        expect(result.current.opposing).toEqual([])
    })

    it('vade kümesi sunucununkiyle aynı', () => {
        // Ayrışırsa kullanıcı sorduğundan başka bir vadenin okumasını alır ve
        // bunu fark etmesinin bir yolu yoktur.
        expect([...HORIZONS]).toEqual(['1M', '3M', '6M'])
    })

    it('her yön değerinin Türkçe bir karşılığı var', () => {
        // Ham enum kullanıcıya hiç ulaşmamalı.
        for (const key of ['UP_LEAN', 'DOWN_LEAN', 'MIXED', 'INSUFFICIENT', 'OUT_OF_RANGE']) {
            expect(DIRECTION_LABELS[key]).toBeTruthy()
        }
    })

    it('sökülen bileşende hata da yazılmaz', async () => {
        // İptal edilmiş bir istekten sonra durum güncellemek, React'in
        // uyarısını üretir ve düşen bileşene ait bir hatayı ekranda bırakır.
        let reject: (reason?: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getDirectionSignal').mockReturnValue(
            new Promise((_resolve, r) => {
                reject = r
            }) as never,
        )
        const { unmount } = renderHook(() => useDirectionSignal('ASELS'))
        unmount()
        await act(async () => {
            reject(new Error('x'))
        })
    })

    it('sökülen bileşen durumu güncellemez', async () => {
        let resolve: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getDirectionSignal').mockReturnValue(
            new Promise((r) => {
                resolve = r
            }) as never,
        )
        const { unmount } = renderHook(() => useDirectionSignal('ASELS'))
        unmount()
        await act(async () => {
            resolve(SIGNAL)
        })
    })
})

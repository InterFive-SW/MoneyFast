/**
 * Piyasalar ekranının yön taraması.
 *
 * Korunan iki özellik: ölçüm değeri satırda DURUYOR (sıralamanın neye göre
 * yapıldığı okunabilmeli), ve "Tümü" bir yön değil süzgecin YOKLUĞU --
 * sunucuya boş bir `direction` göndermek "hiçbiri" gibi okunabilirdi.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { act, renderHook, waitFor } from '@testing-library/react'

import { SCREEN_ERROR, SCREEN_FILTERS, useDirectionScreen } from './useDirectionScreen'
import { apiClient } from '../api/client'

const SCREEN = {
    horizon: '3M',
    computedAt: '2026-09-07T22:30:00Z',
    note: null,
    items: [
        { symbol: 'ASELS', direction: 'UP_LEAN', lean: 0.63, observations: 252,
          narrative: 'okuma', evidence: [] },
        { symbol: 'THYAO', direction: 'UP_LEAN', lean: null, observations: 252,
          narrative: null, evidence: [] },
    ],
}

beforeEach(() => {
    vi.spyOn(apiClient, 'getDirectionScreen').mockResolvedValue(SCREEN as never)
})
afterEach(() => vi.restoreAllMocks())

describe('useDirectionScreen', () => {
    it('taramayı yükler', async () => {
        const { result } = renderHook(() => useDirectionScreen())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.rows).toHaveLength(2)
        expect(result.current.error).toBeNull()
    })

    it('hesaplama zamanı taşınır', async () => {
        // Bir okumanın ne zaman yapıldığını söylemeden göstermek, dünkü
        // ölçümü bugünün ölçümü gibi göstermek olurdu.
        const { result } = renderHook(() => useDirectionScreen())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.computedAt).toBe('2026-09-07T22:30:00Z')
    })

    it('varsayılan olarak yükseliş yönü sorulur', async () => {
        const { result } = renderHook(() => useDirectionScreen())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(apiClient.getDirectionScreen).toHaveBeenCalledWith('3M', 'UP_LEAN', 10)
    })

    it('"Tümü" seçilince yön süzgeci hiç gönderilmez', async () => {
        // Boş bir dize "hiçbiri" gibi okunabilirdi; göndermemek "süzgeç yok".
        const { result } = renderHook(() => useDirectionScreen())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.setDirection(''))
        await waitFor(() =>
            expect(apiClient.getDirectionScreen).toHaveBeenCalledWith('3M', undefined, 10),
        )
    })

    it('vade değiştirmek yeniden okur', async () => {
        const { result } = renderHook(() => useDirectionScreen())
        await waitFor(() => expect(result.current.loading).toBe(false))
        act(() => result.current.setHorizon('6M'))
        await waitFor(() =>
            expect(apiClient.getDirectionScreen).toHaveBeenCalledWith('6M', 'UP_LEAN', 10),
        )
    })

    it('vade dışı bir istekte sunucunun açıklaması taşınır', async () => {
        vi.spyOn(apiClient, 'getDirectionScreen').mockResolvedValue({
            horizon: '2Y', computedAt: null, items: [],
            note: 'Elimizdeki ölçümler bu vadeye konuşamaz.',
        } as never)
        const { result } = renderHook(() => useDirectionScreen())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.note).toContain('konuşamaz')
        expect(result.current.rows).toEqual([])
    })

    it('boş gövde çökmez', async () => {
        vi.spyOn(apiClient, 'getDirectionScreen').mockResolvedValue({} as never)
        const { result } = renderHook(() => useDirectionScreen())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.rows).toEqual([])
        expect(result.current.computedAt).toBeNull()
    })

    it('hata tek satırlık bir mesaj olur', async () => {
        vi.spyOn(apiClient, 'getDirectionScreen').mockRejectedValue(new Error('x'))
        const { result } = renderHook(() => useDirectionScreen())
        await waitFor(() => expect(result.current.loading).toBe(false))
        expect(result.current.error).toBe(SCREEN_ERROR)
    })

    it('süzgeç seçenekleri arasında bir yargı sözcüğü yok', () => {
        // "En iyi" değil: sıralanan şey ölçülen kanıtların meyli.
        for (const filter of SCREEN_FILTERS) {
            const lowered = filter.label.toLowerCase()
            for (const banned of ['en iyi', 'öneri', 'cazip', 'fırsat']) {
                expect(lowered).not.toContain(banned)
            }
        }
    })

    it('sökülen bileşen durumu güncellemez', async () => {
        let resolve: (value: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getDirectionScreen').mockReturnValue(
            new Promise((r) => {
                resolve = r
            }) as never,
        )
        const { unmount } = renderHook(() => useDirectionScreen())
        unmount()
        await act(async () => {
            resolve(SCREEN)
        })
    })

    it('sökülen bileşende hata da yazılmaz', async () => {
        let reject: (reason?: unknown) => void = () => {}
        vi.spyOn(apiClient, 'getDirectionScreen').mockReturnValue(
            new Promise((_resolve, r) => {
                reject = r
            }) as never,
        )
        const { unmount } = renderHook(() => useDirectionScreen())
        unmount()
        await act(async () => {
            reject(new Error('x'))
        })
    })
})

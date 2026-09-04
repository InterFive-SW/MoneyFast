/**
 * "Ne olur?" simülasyonu.
 *
 * Korunan asıl özellik: hook hiçbir yerde "daha iyi/daha kötü" hesaplamaz.
 * Değişikliği kullanıcı yazar, sunucu iki ölçümü döndürür, yorumu okuyan
 * yapar — bu, özelliği hesap makinesi olarak tutan ve öneri motoruna
 * dönüşmesini engelleyen sınır.
 */
import { afterEach, beforeEach, describe, expect, it, vi } from 'vitest'
import { renderHook, act } from '@testing-library/react'
import {
    SIMULATION_ERROR,
    SIMULATION_NO_PORTFOLIO,
    useRiskSimulation,
} from './useRiskSimulation'
import { apiClient } from '../api/client'

const RESULT = {
    as_of: '2026-08-27T10:00:00Z',
    current: {
        score: 83.4, level: 'Düşük', volatility: 0.18, hhi: 0.16,
        effective_n: 6.1, max_drawdown: -0.11, position_count: 14,
    },
    hypothetical: {
        score: 78.2, level: 'Düşük', volatility: 0.21, hhi: 0.22,
        effective_n: 4.5, max_drawdown: -0.13, position_count: 15,
    },
    deltas: { score: -5.2, volatility: 0.03, hhi: 0.06, effective_n: -1.6, max_drawdown: -0.02 },
    changes: [{ symbol: 'NVDA', quantity_delta: 10, applied: true, note: null }],
    warnings: [],
}

beforeEach(() => {
    vi.spyOn(apiClient, 'simulateRisk').mockResolvedValue(RESULT)
})
afterEach(() => vi.restoreAllMocks())

describe('girdi', () => {
    it('sembol ve adet olmadan çalıştırılamaz', () => {
        const { result } = renderHook(() => useRiskSimulation())
        expect(result.current.ready).toBe(false)
    })

    it('yalnızca sembol yetmez', () => {
        const { result } = renderHook(() => useRiskSimulation())
        act(() => result.current.setSymbol('NVDA'))
        expect(result.current.ready).toBe(false)
    })

    it('sayı olmayan adet kabul edilmez', () => {
        const { result } = renderHook(() => useRiskSimulation())
        act(() => result.current.setSymbol('NVDA'))
        act(() => result.current.setQuantity('birkaç'))
        expect(result.current.ready).toBe(false)
    })

    it('sembol ve sayı verilince hazır olur', () => {
        const { result } = renderHook(() => useRiskSimulation())
        act(() => result.current.setSymbol('NVDA'))
        act(() => result.current.setQuantity('10'))
        expect(result.current.ready).toBe(true)
    })

    it('negatif adet satışı ifade eder ve geçerlidir', () => {
        const { result } = renderHook(() => useRiskSimulation())
        act(() => result.current.setSymbol('THYAO'))
        act(() => result.current.setQuantity('-5'))
        expect(result.current.ready).toBe(true)
    })
})

describe('çalıştırma', () => {
    async function armed(lookback?: undefined | '3M') {
        const view = renderHook(() => useRiskSimulation(lookback))
        act(() => view.result.current.setSymbol('nvda'))
        act(() => view.result.current.setQuantity('10'))
        return view
    }

    it('sembolü büyük harfe çevirip gönderir', async () => {
        const { result } = await armed()
        await act(async () => { await result.current.run() })
        expect(apiClient.simulateRisk).toHaveBeenCalledWith(
            [{ symbol: 'NVDA', quantity_delta: 10 }],
            undefined,
        )
    })

    it('pencereyi geçirir', async () => {
        const { result } = await armed('3M')
        await act(async () => { await result.current.run() })
        expect(apiClient.simulateRisk).toHaveBeenCalledWith(
            [{ symbol: 'NVDA', quantity_delta: 10 }],
            '3M',
        )
    })

    it('iki ölçümü olduğu gibi taşır', async () => {
        const { result } = await armed()
        await act(async () => { await result.current.run() })
        expect(result.current.result?.current.hhi).toBe(0.16)
        expect(result.current.result?.hypothetical.hhi).toBe(0.22)
        expect(result.current.result?.deltas.effective_n).toBe(-1.6)
    })

    it('hazır değilken sunucuya gitmez', async () => {
        const { result } = renderHook(() => useRiskSimulation())
        let outcome: boolean | undefined
        await act(async () => { outcome = await result.current.run() })
        expect(outcome).toBe(false)
        expect(apiClient.simulateRisk).not.toHaveBeenCalled()
    })

    it('boş portföy hatasını kendi cümlesiyle gösterir', async () => {
        /* Sunucu 400 ile sebebini söylüyor; jenerik bir hataya çevirmek
           kullanıcıya hiçbir şey anlatmaz. */
        vi.mocked(apiClient.simulateRisk).mockRejectedValue(
            new Error('Karşılaştırma için önce değerlenebilir bir pozisyon gerekiyor.'),
        )
        const { result } = await armed()
        await act(async () => { await result.current.run() })
        expect(result.current.error).toBe(SIMULATION_NO_PORTFOLIO)
    })

    it('diğer hatalarda jenerik mesaj gösterir', async () => {
        vi.mocked(apiClient.simulateRisk).mockRejectedValue(new Error('boom'))
        const { result } = await armed()
        await act(async () => { await result.current.run() })
        expect(result.current.error).toBe(SIMULATION_ERROR)
        expect(result.current.result).toBeNull()
    })

    it('Error olmayan bir fırlatmada da çökmez', async () => {
        vi.mocked(apiClient.simulateRisk).mockRejectedValue('kablo koptu')
        const { result } = await armed()
        await act(async () => { await result.current.run() })
        expect(result.current.error).toBe(SIMULATION_ERROR)
    })

    it('başarısız bir denemeden sonra eski sonucu göstermez', async () => {
        /* Ekranda kalan eski bir karşılaştırma, yeni girdinin sonucu sanılır. */
        const { result } = await armed()
        await act(async () => { await result.current.run() })
        expect(result.current.result).not.toBeNull()
        vi.mocked(apiClient.simulateRisk).mockRejectedValue(new Error('boom'))
        await act(async () => { await result.current.run() })
        expect(result.current.result).toBeNull()
    })

    it('bittiğinde bekleme durumu kalkar', async () => {
        const { result } = await armed()
        await act(async () => { await result.current.run() })
        expect(result.current.running).toBe(false)
    })

    it('sıfırlama girdiyi ve sonucu temizler', async () => {
        const { result } = await armed()
        await act(async () => { await result.current.run() })
        act(() => result.current.reset())
        expect(result.current.result).toBeNull()
        expect(result.current.symbol).toBe('')
        expect(result.current.quantity).toBe('')
        expect(result.current.error).toBeNull()
    })
})

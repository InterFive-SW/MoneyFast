import { useCallback, useState } from 'react'
import { apiClient } from '../api/client'
import type { RiskLookback, RiskSimulation } from '../api/client'

/**
 * "Ne olur?" simülasyonunun durum makinesi.
 *
 * Değişikliği kullanıcı yazar, sunucu asla önermez — bu, özelliği bir hesap
 * makinesi olarak tutan ve bir öneri motoruna dönüşmesini engelleyen kural.
 * Hook da aynı çizgide durur: hiçbir yerde "daha iyi/daha kötü" hesaplamaz,
 * yalnızca sunucunun döndürdüğü iki ölçümü taşır.
 *
 * Durum burada, bileşende değil: kapsama kapısı `src/hooks/**`'ı sayıyor.
 */
export const SIMULATION_ERROR = 'Simülasyon çalıştırılamadı. Lütfen tekrar deneyin.'
export const SIMULATION_NO_PORTFOLIO =
    'Karşılaştırma için önce değerlenebilir bir pozisyon gerekiyor.'

export function useRiskSimulation(lookback?: RiskLookback) {
    const [symbol, setSymbol] = useState('')
    const [quantity, setQuantity] = useState('')
    const [result, setResult] = useState<RiskSimulation | null>(null)
    const [running, setRunning] = useState(false)
    const [error, setError] = useState<string | null>(null)

    const parsedQuantity = Number(quantity)
    /** Sembol boşsa ya da adet sayı değilse çalıştıracak bir şey yok. */
    const ready =
        symbol.trim().length > 0 && quantity.trim().length > 0 && !Number.isNaN(parsedQuantity)

    const run = useCallback(async () => {
        if (!ready) return false
        setRunning(true)
        setError(null)
        try {
            const simulation = await apiClient.simulateRisk(
                [{ symbol: symbol.trim().toUpperCase(), quantity_delta: parsedQuantity }],
                lookback,
            )
            setResult(simulation)
            return true
        } catch (caught) {
            // Sunucu boş portföyü 400 ile ve kendi cümlesiyle reddediyor;
            // onu jenerik bir hataya çevirmek kullanıcıya hiçbir şey anlatmaz.
            const message = caught instanceof Error ? caught.message : ''
            setError(message.includes('pozisyon') ? SIMULATION_NO_PORTFOLIO : SIMULATION_ERROR)
            setResult(null)
            return false
        } finally {
            setRunning(false)
        }
    }, [ready, symbol, parsedQuantity, lookback])

    const reset = useCallback(() => {
        setResult(null)
        setError(null)
        setSymbol('')
        setQuantity('')
    }, [])

    return {
        symbol,
        setSymbol,
        quantity,
        setQuantity,
        ready,
        running,
        error,
        result,
        run,
        reset,
    }
}

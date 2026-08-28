import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import type { PortfolioAnalysis, RiskLookback, RiskProfile } from '../api/client'

/**
 * Analiz ekranının tek veri kaynağı.
 *
 * Portföy Analizi ve Risk Analizi ayrı ekranlarken her biri kendi isteğini
 * atıyordu ve sekme değiştikçe ikisi yeniden çekilirdi. Tek çatı altında
 * ikisi bir kez çekilip sekmelere dağıtılıyor.
 *
 * **Dönem tek yerde.** İki uç da aynı `lookback` değerini alıyor; ayrı
 * bıraksaydık kullanıcı 3 aya geçtiğinde risk metrikleri değişir, yanındaki
 * trend grafiği bir yılı göstermeye devam ederdi — tek ekranda iki farklı
 * pencere, ki bu değişikliğin bütün amacı buydu.
 *
 * Mantık burada, bileşende değil: kapsama kapısı (`vitest.config.ts`)
 * `src/hooks/**` altını sayıyor, JSX'i saymıyor.
 */
export const ANALYSIS_ERROR = 'Analiz verileri yüklenemedi.'

export interface AnalysisData {
    analysis: PortfolioAnalysis | null
    risk: RiskProfile | null
    lookback: RiskLookback
    setLookback: (value: RiskLookback) => void
    loading: boolean
    /** Yalnızca iki uçtan biri bile dönmediyse dolu. */
    error: string | null
    reload: () => Promise<void>
}

export function useAnalysisData(initial: RiskLookback = '1Y'): AnalysisData {
    const [analysis, setAnalysis] = useState<PortfolioAnalysis | null>(null)
    const [risk, setRisk] = useState<RiskProfile | null>(null)
    const [lookback, setLookback] = useState<RiskLookback>(initial)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        // Paralel, çünkü aralarında bağımlılık yok ve User Story'deki 2
        // saniyelik bütçe sıraya dizmeyi kaldırmıyor.
        const [analysisResult, riskResult] = await Promise.allSettled([
            apiClient.getPortfolioAnalysis(lookback),
            apiClient.getRiskProfile(lookback),
        ])

        // Biri düşerse diğeri gösterilmeye devam eder: elde olan veriyi,
        // yanındaki istek başarısız oldu diye saklamak kullanıcıya olmayan
        // bir kesinti bildirmek olurdu.
        setAnalysis(analysisResult.status === 'fulfilled' ? analysisResult.value : null)
        setRisk(riskResult.status === 'fulfilled' ? riskResult.value : null)
        setError(
            analysisResult.status === 'rejected' || riskResult.status === 'rejected'
                ? ANALYSIS_ERROR
                : null,
        )
        setLoading(false)
    }, [lookback])

    useEffect(() => {
        void load()
    }, [load])

    return { analysis, risk, lookback, setLookback, loading, error, reload: load }
}

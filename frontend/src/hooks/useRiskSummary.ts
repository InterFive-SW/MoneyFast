import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import type { RiskLookback, RiskProfile } from '../api/client'

/**
 * Gösterge panelindeki risk kartının okuduğu özet.
 *
 * Risk sayfasının kendi `useState`/`useEffect` bloğunu kopyalamak yerine ayrı
 * bir hook, çünkü panelin ihtiyacı daha dar (puan, seviye, uyum) ve
 * kapsama kapısı `src/hooks/**` altını sayıyor — mantık burada olursa
 * ölçülüyor, widget'ın içinde olursa ölçülmüyor.
 *
 * Aynı uç noktayı okur: panel ile sayfanın farklı bir puan göstermesi
 * mümkün değil.
 */
export const SUMMARY_ERROR = 'Risk özeti yüklenemedi.'

export function useRiskSummary(lookback: RiskLookback = '1Y') {
    const [profile, setProfile] = useState<RiskProfile | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            setProfile(await apiClient.getRiskProfile(lookback))
        } catch {
            setError(SUMMARY_ERROR)
            setProfile(null)
        } finally {
            setLoading(false)
        }
    }, [lookback])

    useEffect(() => {
        void load()
    }, [load])

    return {
        profile,
        loading,
        error,
        score: typeof profile?.score === 'number' ? profile.score : null,
        level: profile?.level ?? null,
        suitability: profile?.suitability ?? null,
        /** Ölçülecek pozisyon yoksa kart bir puan değil bir çağrı gösterir. */
        hasPositions: (profile?.position_count ?? 0) > 0,
        reload: load,
    }
}

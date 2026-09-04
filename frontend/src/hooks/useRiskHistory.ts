import { useCallback, useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import type { RiskSnapshot } from '../api/client'

/**
 * Risk puanının zaman içindeki seyri.
 *
 * Noktalar risk sayfası okundukça birikiyor, geriye dönük üretilmiyor — bu
 * yüzden yeni bir hesapta seri boş, ikinci günde iki noktalı. Hook bu üç
 * durumu (boş / tek nokta / gerçek seri) ayırıyor, çünkü tek noktalı bir
 * çizgi grafiği "değişim yok" gibi okunur, oysa daha ölçülecek ikinci gün
 * gelmemiştir.
 */
export const HISTORY_ERROR = 'Risk geçmişi yüklenemedi.'

export interface RiskTrend {
    /** İlk ve son ölçüm arasındaki puan farkı; iki ölçüm yoksa `null`. */
    change: number | null
    first: RiskSnapshot | null
    last: RiskSnapshot | null
}

/**
 * Seriden bir eğilim çıkarır.
 *
 * Puanı `null` olan günler atlanır: ölçülemeyen bir gün sıfır değil, yok.
 * İki ölçülmüş gün yoksa `change` de yok — bir noktadan eğilim üretmek,
 * olmayan bir hareketi rapor etmektir.
 */
export function trendOf(points: RiskSnapshot[]): RiskTrend {
    const measured = points.filter((point) => typeof point.score === 'number')
    if (measured.length < 2) {
        return {
            change: null,
            first: measured[0] ?? null,
            last: measured[measured.length - 1] ?? null,
        }
    }
    const first = measured[0]
    const last = measured[measured.length - 1]
    return {
        change: Math.round(((last.score as number) - (first.score as number)) * 10) / 10,
        first,
        last,
    }
}

export function useRiskHistory(days = 90) {
    const [points, setPoints] = useState<RiskSnapshot[]>([])
    const [lookback, setLookback] = useState<string>('')
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            const history = await apiClient.getRiskHistory(days)
            setPoints(Array.isArray(history?.points) ? history.points : [])
            setLookback(history?.lookback ?? '')
        } catch {
            setError(HISTORY_ERROR)
            setPoints([])
        } finally {
            setLoading(false)
        }
    }, [days])

    useEffect(() => {
        void load()
    }, [load])

    return {
        points,
        lookback,
        loading,
        error,
        trend: trendOf(points),
        /** İki ölçülmüş gün yoksa çizecek bir seri yok. */
        hasSeries: points.filter((point) => typeof point.score === 'number').length >= 2,
        reload: load,
    }
}

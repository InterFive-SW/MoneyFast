import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiClient } from '../api/client'
import type { ScenarioFactor, ScenarioResult, StressResult } from '../api/client'

/**
 * Analiz > Senaryo — "dolar %10 çıksa ne olurdu" ve "gerçekte ne oldu".
 *
 * Cümleyi ÜRETMİYOR, okuyor. `statement` backend'de kuruluyor ve sohbet de
 * aynı uç noktadan aynı cümleyi alıyor; istemcide ikinci bir üretici, aynı
 * ölçümün iki yüzeyde farklı anlatılması demekti. Uygunluk sınırı da orada
 * test ediliyor -- burada kurulan bir cümle o testten geçmezdi.
 *
 * Senaryo İSTEK ÜZERİNE çalışıyor, stres testi sayfa açılışında: ilki
 * kullanıcının seçtiği bir faktör ve şok gerektiriyor, ikincisi hiçbir girdi
 * istemiyor ve zaten olanı gösteriyor.
 */
export const SCENARIO_ERROR = 'Senaryo hesaplanamadı.'
export const STRESS_ERROR = 'Stres testi yüklenemedi.'

/** Ekranda gösterilecek faktör adları. Backend de aynı adı döndürüyor;
 *  buradaki liste yalnızca seçicinin sırası ve etiketleri için. */
export const FACTOR_LABELS: Record<ScenarioFactor, string> = {
    USDTRY: 'Dolar/TL',
    EURTRY: 'Euro/TL',
    XU100: 'BIST 100',
    XAUUSD: 'Ons altın',
}

/** Şoku bu eşiğin altında açıklayan bir faktör "zayıf" sayılıyor; backend'in
 *  `scenario.WEAK_FIT_R2` değeriyle aynı. Rozet için, cümle için değil --
 *  cümleyi backend zaten kuruyor. */
export const WEAK_FIT_R2 = 0.2

export interface ScenarioData {
    result: ScenarioResult | null
    stress: StressResult | null
    loading: boolean
    stressLoading: boolean
    error: string | null
    stressError: string | null
    /** Ölçülen ilişki zayıf mı — rozet bunu okuyor. */
    isWeakFit: boolean
    /** Duyarlılık bloğu, gelmediyse null. Eksik bir gövde paneli
     *  çökertmemeli: ölçüm gösterememek, sayfayı kaybetmekten iyidir. */
    sensitivity: NonNullable<ScenarioResult['sensitivity']> | null
    /** Portföyün en kötü günleri. Gövde eksik gelirse boş -- ölçüm
     *  gösterememek, sayfayı kaybetmekten iyidir. */
    worstDays: NonNullable<StressResult['worst_days']>
    /** Faktörün en sert pencereleri, adlarıyla ve okunabilir sırada. */
    replayRows: { symbol: string; name: string; factor: number; portfolio: number;
                  start: string; end: string; days: number }[]
    run: (factor: ScenarioFactor, shockPct: number) => Promise<void>
    reloadStress: () => Promise<void>
}

export function useScenario(lookback: string): ScenarioData {
    const [result, setResult] = useState<ScenarioResult | null>(null)
    const [stress, setStress] = useState<StressResult | null>(null)
    const [loading, setLoading] = useState(false)
    const [stressLoading, setStressLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [stressError, setStressError] = useState<string | null>(null)

    const run = useCallback(
        async (factor: ScenarioFactor, shockPct: number) => {
            setLoading(true)
            setError(null)
            try {
                setResult(await apiClient.runScenario(factor, shockPct, lookback))
            } catch {
                // Eski sonucu ekranda bırakmak, kullanıcının SORDUĞU soruya
                // başka bir sorunun cevabını göstermek olurdu.
                setError(SCENARIO_ERROR)
                setResult(null)
            } finally {
                setLoading(false)
            }
        },
        [lookback],
    )

    const loadStress = useCallback(async () => {
        setStressLoading(true)
        setStressError(null)
        try {
            setStress(await apiClient.getStressTest(lookback))
        } catch {
            setStressError(STRESS_ERROR)
            setStress(null)
        } finally {
            setStressLoading(false)
        }
    }, [lookback])

    useEffect(() => {
        void loadStress()
    }, [loadStress])

    const replayRows = useMemo(() => {
        const replays = stress?.replays ?? {}
        return Object.entries(replays)
            .map(([symbol, row]) => ({
                symbol,
                // Ad backend'den; sembol kullanıcıya sızmasın diye.
                name: stress?.factor_names?.[symbol] ?? symbol,
                factor: row.factor_move_pct,
                portfolio: row.portfolio_move_pct,
                start: row.start_date,
                end: row.end_date,
                days: row.trading_days,
            }))
            // En sert hareket üstte; yön değil BÜYÜKLÜK sıralıyor, çünkü bir
            // çöküş bir sıçrama kadar ilgi çekici.
            .sort((a, b) => Math.abs(b.factor) - Math.abs(a.factor))
    }, [stress])

    const r2 = result?.sensitivity?.r_squared
    return {
        result,
        stress,
        loading,
        stressLoading,
        error,
        stressError,
        // Ölçülemeyen r² zayıf SAYILMIYOR: bilinmeyen bir uyum, zayıf bir
        // uyumdan farklı bir şey.
        isWeakFit: r2 != null && r2 < WEAK_FIT_R2,
        sensitivity: result?.sensitivity ?? null,
        worstDays: stress?.worst_days ?? [],
        replayRows,
        run,
        reloadStress: loadStress,
    }
}

import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../api/client'
import { toNumber } from '../lib/chartFormat'

/**
 * Haftalık portföy serisi — 15 dakikalık kovalardan.
 *
 * Gösterge panelindeki "Portföy Performansı" grafiği haftalık aralıkta
 * yalnızca BEŞ nokta çiziyordu: `/analytics/portfolio` günlük bar okuyor
 * (`interval="1d"`) ve sunucu tarafındaki `_trend` her zaman damgasını
 * `stamp.date()`'e indirgiyor, yani haftada ne kadar veri olursa olsun
 * sonuç işlem günü sayısı kadar nokta.
 *
 * Gereken hesap ZATEN vardı ve ZATEN bir uca bağlıydı:
 * `GET /api/investment/portfolio/chart?range=hafta`, `CANDLE_RANGES` içinde
 * `("5m", 900, 7, 1200)` ile tanımlı. Ölçüldü: **266 nokta**. Yeni bir tablo,
 * yeni bir migration ya da ikinci bir hesap yazmak, var olan doğru cevabı
 * ikinci kez yazmak olurdu.
 *
 * Yalnızca HAFTA için. Diğer aralıklar günlük seride kalıyor: bir yıllık
 * pencereyi 15 dakikalık kovalarla çizmek okunmayan bir grafik üretirdi.
 */

export const WEEK_SERIES_ERROR = 'Haftalık seri yüklenemedi.'

/** Grafiğin çizdiği tek nokta. */
export interface SeriesPoint {
    /** Milisaniye cinsinden an. */
    at: number
    value: number
}

export interface WeekSeries {
    points: SeriesPoint[]
    loading: boolean
    error: string | null
}

/**
 * Kova kapanışı çizgi değeri oluyor: bir aralığın "sonunda ne kadardı".
 *
 * `toNumber` kullanılıyor, `Number()` DEĞİL: `Number(null)` sıfır veriyor ve
 * sıfır sonlu bir sayı, dolayısıyla zaman damgası `null` gelen bir kova
 * süzgeci geçip grafiğin en soluna 1 Ocak 1970'e çizilirdi. `toNumber` bu
 * ayrımı zaten yapıyor ve zaten test edilmiş -- ikinci bir kopya, ikinci bir
 * kalibrasyon demek olurdu.
 */
function toPoints(rows: unknown): SeriesPoint[] {
    if (!Array.isArray(rows)) return []
    const points: SeriesPoint[] = []
    for (const row of rows) {
        const raw = row as { time?: unknown; close?: unknown }
        const at = toNumber(raw.time)
        const value = toNumber(raw.close)
        if (at === null || value === null) continue
        // Uç nokta saniye veriyor, `Date` milisaniye bekliyor.
        points.push({ at: at * 1000, value })
    }
    return points.sort((a, b) => a.at - b.at)
}

export function usePortfolioWeekSeries(enabled: boolean): WeekSeries {
    const [rows, setRows] = useState<unknown>(null)
    const [loading, setLoading] = useState(false)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        // Kullanıcı haftaya hiç geçmezse istek de atılmıyor; geçtiğinde bir
        // kez atılıyor ve sonuç saklanıyor.
        if (!enabled || rows !== null) return
        let cancelled = false
        setLoading(true)
        setError(null)
        apiClient
            .getPortfolioChart('hafta')
            .then((response) => {
                if (cancelled) return
                // Yanıt aralık adıyla anahtarlanmış geliyor: `{"hafta": [...]}`.
                setRows((response as Record<string, unknown>)?.hafta ?? [])
            })
            .catch(() => {
                if (cancelled) return
                // Boş seri ile ulaşılamayan uç ayrı şeyler: biri "bu hafta
                // veri yok" diyor, diğeri hiçbir şey demiyor.
                setError(WEEK_SERIES_ERROR)
                setRows([])
            })
            .finally(() => {
                if (!cancelled) setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [enabled, rows])

    const points = useMemo(() => toPoints(rows), [rows])
    return { points, loading, error }
}

import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../api/client'
import type { Candle } from '../api/client'

/**
 * Bir enstrümanın günlük mum serisi, grafiğin istediği biçimde.
 *
 * Veri zaten vardı: `GET /api/market/candles` tam OHLCV döndürüyor ve
 * `useComparisonSeries` onu okuyor -- ama yalnızca kapanışları alıp yüzdeye
 * çeviriyor, açılış/yüksek/düşük'ü atıyordu. Hisse detay sayfasında hiç
 * grafik yoktu, dolayısıyla kullanıcı tıkladığı satırın nasıl davrandığını
 * yalnızca tek bir günlük yüzdeden okuyabiliyordu.
 *
 * Mantık bileşende değil burada: kapsama kapısı `src/hooks/**` altını sayıyor.
 */

/** Grafiğin sunduğu aralıklar; değer = istenecek bar sayısı. */
export const CANDLE_RANGES = [
    { key: '1A', label: '1A', bars: 22 },
    { key: '3A', label: '3A', bars: 66 },
    { key: '6A', label: '6A', bars: 130 },
    // Uç nokta 400 barda kesiyor (`limit` <= 400), yani "5Y" sunulamaz.
    // Sunulmayan bir aralık, boş dönen bir aralıktan iyidir.
    { key: '1Y', label: '1Y', bars: 252 },
] as const

export type CandleRangeKey = (typeof CANDLE_RANGES)[number]['key']

export const CANDLES_ERROR = 'Grafik verisi yüklenemedi.'

/** lightweight-charts'ın günlük seride beklediği nokta. */
export interface ChartCandle {
    time: string
    open: number
    high: number
    low: number
    close: number
}

export interface CandleData {
    candles: ChartCandle[]
    /** Barların para birimi. Varsayılmaz: AAPL dolar, THYAO lira. */
    currency: string | null
    loading: boolean
    error: string | null
}

/**
 * Zaman damgasını takvim gününe indirger.
 *
 * lightweight-charts günlük seride `YYYY-MM-DD` bekliyor ve AYNI güne iki
 * nokta verilirse seriyi sessizce reddediyor. Dilim UTC üzerinden alınıyor,
 * çünkü barın kendisi bir takvim günü -- yerel saate çevirmek, İstanbul'da
 * gece yarısından sonra bakan birine barı bir gün kaydırırdı.
 */
function dayOf(timestamp: unknown): string {
    return String(timestamp).slice(0, 10)
}

export function useCandles(symbol: string | undefined, bars: number): CandleData {
    const [raw, setRaw] = useState<Candle[]>([])
    const [currency, setCurrency] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (!symbol) {
            setRaw([])
            setCurrency(null)
            setLoading(false)
            return
        }
        let cancelled = false
        setLoading(true)
        setError(null)
        apiClient
            .getCandles(symbol, bars)
            .then((response) => {
                if (cancelled) return
                setRaw(response.candles ?? [])
                setCurrency(response.currency ?? null)
            })
            .catch(() => {
                if (cancelled) return
                // Boş seri ile ulaşılamayan uç ayrı şeyler: biri "bu
                // enstrümanın geçmişi yok" diyor, diğeri hiçbir şey demiyor.
                setError(CANDLES_ERROR)
                setRaw([])
                setCurrency(null)
            })
            .finally(() => {
                if (!cancelled) setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [symbol, bars])

    const candles = useMemo(() => {
        const byDay = new Map<string, ChartCandle>()
        for (const candle of raw) {
            // Aynı güne düşen ikinci bar SONUNCUSU kazanıyor; seri zaten
            // eskiden yeniye geliyor, dolayısıyla bu en güncel olan.
            byDay.set(dayOf(candle.timestamp), {
                time: dayOf(candle.timestamp),
                open: candle.open,
                high: candle.high,
                low: candle.low,
                close: candle.close,
            })
        }
        return [...byDay.values()].sort((a, b) => a.time.localeCompare(b.time))
    }, [raw])

    return { candles, currency, loading, error }
}

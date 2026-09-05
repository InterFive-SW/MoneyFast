import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../api/client'
import { toNumber } from '../lib/chartFormat'

/**
 * Fonun mum serisi.
 *
 * Fon gunde TEK fiyat yayimliyor, dolayisiyla GUNLUK mum diye bir sey yok:
 * acilis/yuksek/dusuk/kapanis ayni sayi olurdu. Sunucu birkac gunu kovaliyor
 * (haftalik ya da aylik) ve kova genisligini yanitta tasiyor -- kullanici
 * baktigi cubugun bir haftayi mi bir ayi mi ozetledigini bilmeli.
 */

export const FUND_CANDLES_ERROR = 'Fon grafigi yuklenemedi.'

/** Sunulan araliklar; sunucunun `CANDLE_RANGES` anahtarlariyla ayni. */
export const FUND_RANGES = ['1A', '3A', '1Y', '5Y'] as const
export type FundRange = (typeof FUND_RANGES)[number]

export interface FundCandle {
    time: string
    open: number
    high: number
    low: number
    close: number
}

export interface FundCandleData {
    candles: FundCandle[]
    /** `week` | `month` -- basliga yaziliyor. */
    bucket: string | null
    loading: boolean
    error: string | null
}

export function useFundCandles(code: string, window: FundRange): FundCandleData {
    const [raw, setRaw] = useState<unknown[]>([])
    const [bucket, setBucket] = useState<string | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    useEffect(() => {
        if (!code) return
        let cancelled = false
        setLoading(true)
        setError(null)
        apiClient
            .getFundCandles(code, window)
            .then((response) => {
                if (cancelled) return
                setRaw(response.candles ?? [])
                setBucket(response.bucket ?? null)
            })
            .catch(() => {
                if (cancelled) return
                // Bos seri ile ulasilamayan uc ayri seyler.
                setError(FUND_CANDLES_ERROR)
                setRaw([])
            })
            .finally(() => {
                if (!cancelled) setLoading(false)
            })
        return () => {
            cancelled = true
        }
    }, [code, window])

    const candles = useMemo(() => {
        const out: FundCandle[] = []
        for (const row of raw) {
            const point = row as Record<string, unknown>
            const day = String(point.date ?? '').slice(0, 10)
            const open = toNumber(point.open)
            const high = toNumber(point.high)
            const low = toNumber(point.low)
            const close = toNumber(point.close)
            // Eksik bir fiyat SIFIR degil: sifir bir mumu tabana cakardi.
            if (!day || open === null || high === null || low === null || close === null) {
                continue
            }
            out.push({ time: day, open, high, low, close })
        }
        return out.sort((a, b) => a.time.localeCompare(b.time))
    }, [raw])

    return { candles, bucket, loading, error }
}

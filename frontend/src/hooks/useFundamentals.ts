import { useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import { formatDate } from '../lib/datetime'
import type { FundamentalsOut, MarketCalendar } from '../api/client'

/**
 * Bir enstrümanın temel verisi — sohbetin okuduğu uç noktanın aynısı.
 *
 * Her alan null olabilir ve null "sağlayıcı bunu yayımlamıyor" demek,
 * sıfır DEĞİL. Bankanın brüt marjı yoktur; onu %0,0 diye çizmek, şirketin
 * hiç sahip olmadığı bir olguyu bildirmek olur.
 */
export function useFundamentals(symbol: string) {
    const [data, setData] = useState<FundamentalsOut | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        let cancelled = false
        setLoading(true)
        apiClient
            .getFundamentals(symbol)
            .then((body) => { if (!cancelled) setData(body) })
            .catch(() => { if (!cancelled) setData(null) })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [symbol])

    return { fundamentals: data, loading }
}

/** Bir oranı yüzde olarak yazar. `null` "—" olur, "%0,0" DEĞİL. */
export function pct(value: number | null | undefined, digits = 1): string {
    if (value === null || value === undefined) return '—'
    return `%${(value * 100).toLocaleString('tr-TR', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    })}`
}

/** Büyük tutarları kısaltır: 26.350.999.552 -> 26,4 Mr. */
export function compact(value: number | null | undefined, unit = ''): string {
    if (value === null || value === undefined) return '—'
    const text = new Intl.NumberFormat('tr-TR', {
        notation: 'compact',
        maximumFractionDigits: 1,
    }).format(value)
    return unit ? `${text} ${unit}` : text
}

/** Bir katsayıyı yazar: 89,393 -> 89,39x */
export function ratio(value: number | null | undefined, digits = 2): string {
    if (value === null || value === undefined) return '—'
    return `${value.toLocaleString('tr-TR', {
        minimumFractionDigits: digits,
        maximumFractionDigits: digits,
    })}x`
}

/** Analist konsensüsünün Türkçesi. BAŞKASININ görüşü; ürünün kendi görüşü
 *  değil ve öyle sunulmuyor. */
export const RECOMMENDATION_TR: Record<string, string> = {
    strong_buy: 'Güçlü Al',
    buy: 'Al',
    hold: 'Tut',
    underperform: 'Endeksin Altında',
    sell: 'Sat',
}

/** "Analizler" ekranının üç listesi. Tek çağrı: ekran otuz satır gösteriyor
 *  ve enstrüman başına istek atmak, göstereceği şeyden pahalı olurdu. */
export function useMarketCalendar() {
    const [calendar, setCalendar] = useState<MarketCalendar | null>(null)
    const [loading, setLoading] = useState(true)

    useEffect(() => {
        let cancelled = false
        apiClient
            .getMarketCalendar(40)
            .then((body) => { if (!cancelled) setCalendar(body) })
            .catch(() => { if (!cancelled) setCalendar(null) })
            .finally(() => { if (!cancelled) setLoading(false) })
        return () => { cancelled = true }
    }, [])

    return { calendar, loading }
}

/** Bir tarihi gün-ay-yıl olarak yazar. Yoksa "—". */
export function shortDate(value: string | null | undefined): string {
    if (!value) return '—'
    return formatDate(value)
}

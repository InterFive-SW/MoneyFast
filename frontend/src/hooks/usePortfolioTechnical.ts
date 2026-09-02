import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiClient } from '../api/client'
import type { PortfolioTechnical, PortfolioTechnicalRow } from '../api/client'

/**
 * Analiz > Risk sekmesindeki "Teknik Görünüm" panelinin verisi.
 *
 * Cümleyi ÜRETMİYOR, okuyor. `summary.statement` ve satır başına `narrative`
 * backend'de kuruluyor; sohbet de aynı uç noktadan aynı cümleyi alıyor. İki
 * yüzeyin aynı ölçümü farklı anlatması, kullanıcının hangisine güveneceğini
 * bilememesi demekti.
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**` altını
 * sayıyor, JSX'i saymıyor.
 */
export const TECHNICAL_ERROR = 'Teknik görünüm yüklenemedi.'

/** Rozet rengi ve etiketi. Eğilim bir ÖLÇÜMDÜR, bir tavsiye değil. */
export const TREND_LABEL: Record<string, string> = {
    UPTREND: 'Yükseliş',
    DOWNTREND: 'Düşüş',
    SIDEWAYS: 'Yatay',
    UNKNOWN: 'Ölçülemedi',
}

export interface PortfolioTechnicalData {
    data: PortfolioTechnical | null
    loading: boolean
    error: string | null
    /** Değere göre azalan; büyük pozisyon üstte, çünkü tabloyu o taşıyor. */
    rows: PortfolioTechnicalRow[]
    /** Toplulaştırma bloğu, gelmediyse null. Eksik bir gövde paneli
     *  çökertmemeli: ölçüm gösterememek, sayfayı kaybetmekten iyidir. */
    summary: PortfolioTechnical['summary'] | null
    /** Ağırlık hesabına giremeyen pozisyonlar için tek satırlık uyarı. */
    coverageNote: string | null
    reload: () => Promise<void>
}

export function usePortfolioTechnical(): PortfolioTechnicalData {
    const [data, setData] = useState<PortfolioTechnical | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            setData(await apiClient.getPortfolioTechnical())
        } catch {
            setError(TECHNICAL_ERROR)
            setData(null)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void load()
    }, [load])

    const rows = useMemo(() => {
        // Değeri bilinmeyen pozisyon en sona: sıralama ölçütü onda yok,
        // ama listeden düşmesi onu portföyde yokmuş gibi gösterirdi.
        return [...(data?.positions ?? [])].sort(
            (a, b) => (b.value ?? -1) - (a.value ?? -1),
        )
    }, [data])

    const unconvertible = data?.unconvertible ?? []
    return {
        data,
        summary: data?.summary ?? null,
        loading,
        error,
        rows,
        // Ağırlık, portföyün TAMAMI üzerinden hesaplanmış gibi sunulmamalı.
        // Kuru olmayan pozisyon hesaba girmiyor ve bunun yazılı olması,
        // yüzdenin neyi kapsadığını okunabilir kılıyor.
        coverageNote: unconvertible.length
            ? `Değer payı ${unconvertible.join(', ')} hariç hesaplandı: kur bulunamadı.`
            : null,
        reload: load,
    }
}

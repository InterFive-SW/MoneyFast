import { useCallback, useEffect, useMemo, useState } from 'react'
import { apiClient } from '../api/client'
import type { PortfolioNews, PortfolioNewsItem } from '../api/client'

/**
 * Analiz > Genel Bakış'taki "Portföyünüze dokunan haberler" panelinin verisi.
 *
 * `useAnalysisData`'ya eklenmedi, ayrı duruyor: o hook'un her isteği
 * `lookback`'e bağlı ve kullanıcı dönemi 3 aya çevirdiğinde yeniden çekiliyor.
 * Haber penceresi ise dönemden bağımsız — backend'in kendi penceresi, ve onu
 * `lookback`'e bağlamak "1 aylık getiri" seçen kullanıcının haber listesini de
 * bir aya kırpardı. İki farklı soru, iki farklı pencere.
 *
 * Mantık burada, bileşende değil: kapsama kapısı `src/hooks/**` altını
 * sayıyor, JSX'i saymıyor.
 */
export const NEWS_ERROR = 'Haberler yüklenemedi.'

export interface PortfolioNewsData {
    news: PortfolioNews | null
    loading: boolean
    error: string | null
    /** Pozisyonu olan ama bu pencerede hiç haberi olmayan semboller. */
    quietSymbols: string[]
    /** Portföyde hisse var mı — hiç yoksa panel haber değil, portföy sorunu anlatır. */
    hasHoldings: boolean
    /** Bir haberin kullanıcının hangi hisselerine dokunduğu, okunabilir hâlde. */
    heldLabel: (item: PortfolioNewsItem) => string
    reload: () => Promise<void>
}

export function usePortfolioNews(): PortfolioNewsData {
    const [news, setNews] = useState<PortfolioNews | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)

    const load = useCallback(async () => {
        setLoading(true)
        setError(null)
        try {
            setNews(await apiClient.getPortfolioNews())
        } catch {
            // Hata, boş sonuçtan AYRI tutuluyor. "Haber yok" ölçülmüş bir
            // cevap; ulaşılamayan bir uç ise ölçüm değil, ve ikisini aynı
            // boş listeye indirmek kullanıcıya olmayan bir sessizlik
            // bildirmek olurdu.
            setError(NEWS_ERROR)
            setNews(null)
        } finally {
            setLoading(false)
        }
    }, [])

    useEffect(() => {
        void load()
    }, [load])

    const quietSymbols = useMemo(
        () => (news?.symbols ?? []).filter((row) => row.count === 0).map((row) => row.symbol),
        [news],
    )

    return {
        news,
        loading,
        error,
        quietSymbols,
        hasHoldings: (news?.symbols ?? []).length > 0,
        // Haber birden çok şirketi anabiliyor ("BIST 100 değer kaybetti" dört
        // hisseyi etiketliyor) ve kullanıcı bunlardan yalnızca birine sahip
        // olabiliyor. Listede DURMA SEBEBİ okunabilir olmalı; tüm etiketleri
        // yazmak, sahip olunmayan hisseleri portföydeymiş gibi gösterirdi.
        heldLabel: (item: PortfolioNewsItem) => (item.heldSymbols ?? []).join(', '),
        reload: load,
    }
}

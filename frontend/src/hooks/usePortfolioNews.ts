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
    /** Seçili semboller. Boşken süzgeç yok, yani liste olduğu gibi. */
    selected: string[]
    /** Süzgece bir sembol ekler ya da çıkarır. */
    toggleSymbol: (symbol: string) => void
    /** Süzgeci kaldırır. */
    clearSelection: () => void
    /** Süzgeçten geçmiş haberler; seçim yokken `news.items`'ın aynısı. */
    visibleItems: PortfolioNewsItem[]
    reload: () => Promise<void>
}

export function usePortfolioNews(): PortfolioNewsData {
    const [news, setNews] = useState<PortfolioNews | null>(null)
    const [loading, setLoading] = useState(true)
    const [error, setError] = useState<string | null>(null)
    const [selected, setSelected] = useState<string[]>([])

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

    /**
     * Süzgeç, sunucuya değil listeye uygulanıyor.
     *
     * Uç nokta zaten HABER BAŞINA `heldSymbols` döndürüyor, dolayısıyla
     * "yalnızca GARAN" sorusunun cevabı elde: yeni bir istek atmak, kullanıcı
     * rozete her dokunduğunda bir gidiş-dönüş beklemesi demek olurdu.
     *
     * Aynı sebeple pencere DEĞİŞMİYOR: rozetteki sayı da, liste de aynı 90
     * günün içinden geliyor, yani "GARAN · 78" yazan rozete basınca 78 haber
     * çıkıyor. Süzgeç sunucuya taşınsaydı iki sayı ayrışabilirdi.
     */
    const toggleSymbol = useCallback((symbol: string) => {
        setSelected((current) =>
            current.includes(symbol)
                ? current.filter((entry) => entry !== symbol)
                : [...current, symbol],
        )
    }, [])

    const clearSelection = useCallback(() => setSelected([]), [])

    const visibleItems = useMemo(() => {
        const items = news?.items ?? []
        if (selected.length === 0) return items
        return items.filter((item) =>
            (item.heldSymbols ?? []).some((symbol) => selected.includes(symbol)),
        )
    }, [news, selected])

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
        selected,
        toggleSymbol,
        clearSelection,
        visibleItems,
        reload: load,
    }
}

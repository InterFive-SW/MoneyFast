import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { NewsItem } from '../../api/client'

/**
 * Haberler Bileşeni — canlı RSS akışından.
 *
 * Kategori süzgeci (Piyasa / KAP) kaldırıldı: beslemelerde böyle bir alan yok
 * ve başlıkları kaynağına bakarak "KAP bildirimi" diye etiketlemek uydurma
 * olurdu. Aynı gerekçeyle `sentiment` de backend'de nötr sabit — bir başlığı
 * olumlu/olumsuz saymak piyasa görüşü bildirmektir.
 *
 * `symbols` verilirse yalnızca o enstrümanlarla ilişkilendirilmiş haberler
 * gösterilir; ilişkisi olmayan haber gizlenmez, çünkü listeyi daraltmak
 * "bu hisseyle ilgili haber yok" demek değildir.
 */
export default function NewsWidget({ symbols }: { symbols?: string[] } = {}) {
  const [news, setNews] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    apiClient
      .getMarketNews()
      .then(setNews)
      .catch((error) => console.error('Failed to load news', error))
      .finally(() => setLoading(false))
  }, [])

  const visible = symbols?.length
    ? news.filter((item) => item.relatedSymbols.some((symbol) => symbols.includes(symbol)))
    : news

  if (loading) {
    return (
      <div className="flex flex-col h-full items-center justify-center bg-transparent rounded-2xl border border-transparent shadow-sm">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  return (
    <div className="flex flex-col h-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Piyasa Haberleri</h3>
      </div>

      <div className="flex-1 overflow-y-auto pr-2 -mr-2 space-y-4">
        {visible.map((item) => (
          <a
            key={item.id}
            href={item.url}
            target="_blank"
            rel="noopener noreferrer"
            className="group block cursor-pointer"
          >
            <div className="flex items-start justify-between">
              <h4 className="text-sm font-semibold text-white group-hover:text-emerald-600 transition-colors line-clamp-2 pr-4">
                {item.title}
              </h4>
              <span className="text-[10px] font-medium text-slate-400 whitespace-nowrap mt-0.5">{item.time}</span>
            </div>
            <div className="flex items-center mt-1.5 space-x-2">
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">{item.source}</span>
              {item.relatedSymbols.slice(0, 3).map((symbol) => (
                <span
                  key={symbol}
                  className="text-[10px] font-semibold text-slate-300 bg-white/10 px-1.5 py-0.5 rounded"
                >
                  {symbol}
                </span>
              ))}
            </div>
          </a>
        ))}
        {visible.length === 0 && (
          <div className="text-sm text-slate-400 py-4 text-center">Şu an gösterilecek haber yok.</div>
        )}
      </div>
    </div>
  )
}

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
 *
 * Satırdaki hisse rozetleri TIKLANABİLİR: birine dokununca liste o hisseye
 * iniyor. Rozet artık bağlantının İÇİNDE değil -- bir `<button>`'ı bir
 * `<a>`'nın içine koymak geçersiz HTML ve tıklama hedefi belirsiz kalırdı.
 * Bu yüzden başlık bağlantı, alt satır ayrı.
 */
export default function NewsWidget({ symbols }: { symbols?: string[] } = {}) {
  const [news, setNews] = useState<NewsItem[]>([])
  const [loading, setLoading] = useState(true)
  /** Rozetle seçilen hisse. Dışarıdan gelen `symbols` kapsamı daraltıyor,
   *  bu ise onun içinde tek bir hisseye odaklanıyor. */
  const [focused, setFocused] = useState<string | null>(null)

  // `symbols` verildiğinde süzgeç SUNUCUYA gidiyor: en yeni 20 haberi çekip
  // içinden bir hisseyi ayıklamak, o yirmide hisse yoksa "haber yok" cevabı
  // üretiyordu -- oysa soru hiç sorulmamış oluyordu.
  const scope = symbols?.length ? symbols.join(',') : ''
  useEffect(() => {
    let cancelled = false
    setLoading(true)
    apiClient
      .getMarketNews(scope ? { symbols: scope.split(',') } : undefined)
      .then((rows) => {
        if (!cancelled) setNews(rows)
      })
      .catch((error) => console.error('Failed to load news', error))
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [scope])

  const visible = focused
    ? news.filter((item) => item.relatedSymbols.includes(focused))
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
        {focused && (
          <button
            type="button"
            onClick={() => setFocused(null)}
            className="rounded-full border border-white/10 px-2 py-0.5 text-[10px] font-semibold text-slate-300 transition hover:border-white/25 hover:text-white focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60"
          >
            {focused} ✕
          </button>
        )}
      </div>

      <div className="flex-1 overflow-y-auto pr-2 -mr-2 space-y-4">
        {visible.map((item) => (
          <div key={item.id} className="group">
            <a
              href={item.url}
              target="_blank"
              rel="noopener noreferrer"
              className="block cursor-pointer"
            >
              <div className="flex items-start justify-between">
                <h4 className="text-sm font-semibold text-white group-hover:text-emerald-600 transition-colors line-clamp-2 pr-4">
                  {item.title}
                </h4>
                <span className="text-[10px] font-medium text-slate-400 whitespace-nowrap mt-0.5">{item.time}</span>
              </div>
            </a>
            <div className="flex flex-wrap items-center mt-1.5 gap-2">
              <span className="text-[10px] uppercase tracking-wider font-bold text-slate-400">{item.source}</span>
              {item.relatedSymbols.slice(0, 3).map((symbol) => (
                <button
                  key={symbol}
                  type="button"
                  onClick={() => setFocused((current) => (current === symbol ? null : symbol))}
                  aria-pressed={focused === symbol}
                  className={`text-[10px] font-semibold px-1.5 py-0.5 rounded transition focus:outline-none focus-visible:ring-2 focus-visible:ring-emerald-400/60 ${
                    focused === symbol
                      ? 'bg-emerald-400/25 text-white'
                      : 'bg-white/10 text-slate-300 hover:bg-white/20'
                  }`}
                >
                  {symbol}
                </button>
              ))}
            </div>
          </div>
        ))}
        {visible.length === 0 && (
          <div className="text-sm text-slate-400 py-4 text-center">
            {focused
              ? `${focused} ile ilişkilendirilmiş haber yok.`
              : 'Şu an gösterilecek haber yok.'}
          </div>
        )}
      </div>
    </div>
  )
}

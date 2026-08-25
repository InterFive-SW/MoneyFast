import { useCallback, useEffect, useState } from 'react'
import { Link } from 'react-router-dom'
import { apiClient } from '../../api/client'
import type { WatchlistItem } from '../../api/client'
import { useLiveRows } from '../../hooks/useLiveRows'
import { formatMoney } from '../../lib/money'

/** API'nin döndürdüğü grup anahtarları. */
type Tab = 'all' | 'bist' | 'global'

const TABS: { key: Tab; label: string }[] = [
  { key: 'all', label: 'Tümü' },
  { key: 'bist', label: 'BIST' },
  { key: 'global', label: 'ABD' },
]

/**
 * Kullanıcının izleme listesi. Hem Gösterge Paneli hem Portföy sayfası bu
 * bileşeni kullanır, dolayısıyla ikisi asla farklı bir liste gösteremez.
 *
 * Liste `investment.watchlist_items`'tan gelir — kullanıcının Piyasalar
 * ekranından seçtikleri. Önceden uç nokta evrenin ilk sekiz hissesini
 * alfabetik döndürüyordu: herkese aynı, kimsenin seçmediği bir liste. Üstelik
 * sekmeler API'de olmayan anahtarları (`us`, `crypto`) okuduğu için ABD ve
 * Kripto sekmeleri her zaman boştu; "Kripto" ise sistemde hiç bulunmayan bir
 * varlık sınıfıydı.
 *
 * Fiyatlar açılışta bir kez çekilir, sonra canlı akışla tazelenir.
 */
export default function WatchlistWidget() {
  const [data, setData] = useState<Record<string, WatchlistItem[]>>({})
  const [loading, setLoading] = useState(true)
  const [activeTab, setActiveTab] = useState<Tab>('all')
  const [busy, setBusy] = useState<string | null>(null)

  const load = useCallback(async () => {
    try {
      setData(await apiClient.getWatchlist())
    } catch (error) {
      console.error('Failed to load watchlist', error)
    } finally {
      setLoading(false)
    }
  }, [])

  useEffect(() => { load() }, [load])

  // Hook'lar erken return'den önce çağrılmalı — React'in hook sırası kuralı.
  const currentItems = useLiveRows(data[activeTab] || [])

  async function handleRemove(symbol: string) {
    setBusy(symbol)
    try {
      await apiClient.removeFromWatchlist(symbol)
      await load()
    } catch (error) {
      console.error('Failed to remove from watchlist', error)
    } finally {
      setBusy(null)
    }
  }

  if (loading) {
    return (
      <div className="flex flex-col h-full items-center justify-center bg-transparent rounded-2xl border border-transparent shadow-sm">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const isEmpty = (data.all ?? []).length === 0

  return (
    <div className="flex flex-col h-full bg-transparent p-1">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">İzleme Listesi</h3>
        {!isEmpty && (
          <div className="flex rounded-lg bg-white/5 p-1 backdrop-blur-sm">
            {TABS.map(({ key, label }) => (
              <button
                key={key}
                onClick={() => setActiveTab(key)}
                className={`rounded-md px-3 py-1 text-xs font-semibold transition-all ${
                  activeTab === key
                    ? 'bg-white/10 text-white shadow-sm'
                    : 'text-slate-400 hover:text-slate-300'
                }`}
              >
                {label}
                <span className="ml-1.5 tabular-nums text-[10px] text-slate-500">
                  {(data[key] ?? []).length}
                </span>
              </button>
            ))}
          </div>
        )}
      </div>

      {/* Boşsa boş görünür. Kullanıcının seçmediği hisseleri onun listesiymiş
          gibi göstermek, listenin ne olduğunu anlamsızlaştırır. */}
      {isEmpty ? (
        <div className="flex flex-1 flex-col items-center justify-center gap-3 text-center">
          <p className="text-sm text-slate-400">Henüz izleme listeniz boş.</p>
          <Link
            to="/investment/hisseler"
            className="rounded-lg border border-white/10 bg-white/5 px-3 py-1.5 text-xs font-semibold text-slate-200 transition-colors hover:border-white/20 hover:bg-white/10"
          >
            Piyasalar'dan hisse ekleyin
          </Link>
        </div>
      ) : (
        <div className="flex-1 overflow-y-auto pr-2 -mr-2">
          <div className="flex flex-col gap-2">
            {currentItems.map((item) => (
              <div
                key={item.symbol}
                className="group flex items-center justify-between rounded-xl border border-white/10 bg-white/5 p-3 transition-colors hover:bg-white/10"
              >
                <div className="text-sm font-semibold text-white">{item.symbol}</div>
                <div className="flex items-center gap-3">
                  <div className="text-right">
                    <div className="tabular-nums text-sm font-medium text-slate-300">
                      {formatMoney(item.price, item.currency)}
                    </div>
                    <div className={`tabular-nums text-xs font-semibold ${item.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                      {item.changePercent > 0 ? '+' : ''}{item.changePercent}%
                    </div>
                  </div>
                  <button
                    onClick={() => handleRemove(item.symbol)}
                    disabled={busy === item.symbol}
                    aria-label={`${item.symbol} izlemeden çıkar`}
                    title="İzlemeden çıkar"
                    className="opacity-0 transition-opacity group-hover:opacity-100 text-slate-500 hover:text-rose-400 disabled:opacity-40"
                  >
                    <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
                      <path strokeLinecap="round" strokeLinejoin="round" d="M6 18L18 6M6 6l12 12" />
                    </svg>
                  </button>
                </div>
              </div>
            ))}
          </div>
        </div>
      )}
    </div>
  )
}

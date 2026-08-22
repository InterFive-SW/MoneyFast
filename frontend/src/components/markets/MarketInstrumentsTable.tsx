import { useEffect, useMemo, useRef, useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { MarketInstrument } from '../../data/mockData'
import { COLUMN_SETS, formatMetricValue, type ColumnSetKey } from '../../data/columnSets'
import { useWatchlist } from '../../hooks/useWatchlist'

type MarketTab = 'BIST' | 'ABD' | 'Kripto'
type SortKey = 'symbol' | 'price' | 'changePercent' | 'volume'
type SortDir = 'asc' | 'desc'

interface Props {
  instruments: MarketInstrument[]
  columnSet?: ColumnSetKey
  activeTab?: MarketTab
  onTabChange?: (tab: MarketTab) => void
}

function formatCompact(value: number): string {
  return new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function formatPrice(value: number): string {
  return value.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })
}

/** 52 haftalık düşük/yüksek aralığında fiyatın konumunu gösteren mini bar */
function Week52RangeBar({ low, high, price }: { low: number; high: number; price: number }) {
  const range = high - low
  const position = range > 0 ? Math.min(100, Math.max(0, ((price - low) / range) * 100)) : 50

  return (
    <div className="flex flex-col items-end gap-1 w-24">
      <div className="relative h-1.5 w-full rounded-full bg-slate-800/5">
        <div
          className="absolute top-1/2 h-2.5 w-2.5 -translate-y-1/2 -translate-x-1/2 rounded-full bg-emerald-500 border-2 border-white shadow-sm"
          style={{ left: `${position}%` }}
        />
      </div>
      <div className="flex w-full justify-between text-[9px] text-slate-400 tabular-nums">
        <span>{formatPrice(low)}</span>
        <span>{formatPrice(high)}</span>
      </div>
    </div>
  )
}

/**
 * Piyasalar ekranının ana tablosu (Fintables tarzı)
 * Pazar sekmesi + arama + sütun sıralama + favoriye ekleme + kolon seti — tamamen mock veri üzerinde, client-side.
 * `columnSet` verilmezse 'Getiri' seti (Hacim/Piyasa Değeri/52 Hafta) gösterilir.
 */
export default function MarketInstrumentsTable({ instruments, columnSet = 'getiri', activeTab: controlledTab, onTabChange }: Props) {
  const navigate = useNavigate()
  const [internalTab, setInternalTab] = useState<MarketTab>('BIST')
  const activeTab = controlledTab ?? internalTab
  const setActiveTab = onTabChange ?? setInternalTab

  const [query, setQuery] = useState('')
  const [sortKey, setSortKey] = useState<SortKey>('symbol')
  const [sortDir, setSortDir] = useState<SortDir>('asc')
  // Backed by the real watchlist now. This was local state: the star lit up,
  // saved nothing, and reset on navigation.
  const { symbols: favorites, toggle: toggleFavorite } = useWatchlist()
  const searchInputRef = useRef<HTMLInputElement>(null)

  const activeColumnSet = COLUMN_SETS.find((set) => set.key === columnSet) ?? COLUMN_SETS[0]

  // Ctrl/Cmd+K ile arama kutusuna hızlı odaklanma
  useEffect(() => {
    function handleKeyDown(e: KeyboardEvent) {
      if ((e.ctrlKey || e.metaKey) && e.key.toLowerCase() === 'k') {
        e.preventDefault()
        searchInputRef.current?.focus()
      }
    }
    window.addEventListener('keydown', handleKeyDown)
    return () => window.removeEventListener('keydown', handleKeyDown)
  }, [])

  function handleSort(key: SortKey) {
    if (key === sortKey) {
      setSortDir((prev) => (prev === 'asc' ? 'desc' : 'asc'))
    } else {
      setSortKey(key)
      setSortDir('asc')
    }
  }

  const rows = useMemo(() => {
    const filtered = instruments.filter((item) => {
      if (item.market !== activeTab) return false
      if (!query.trim()) return true
      const q = query.trim().toLowerCase()
      return item.symbol.toLowerCase().includes(q) || item.name.toLowerCase().includes(q)
    })

    const sorted = [...filtered].sort((a, b) => {
      const dir = sortDir === 'asc' ? 1 : -1
      if (sortKey === 'symbol') return a.symbol.localeCompare(b.symbol) * dir
      return (a[sortKey] - b[sortKey]) * dir
    })

    return sorted
  }, [instruments, activeTab, query, sortKey, sortDir])

  const columns: { key: SortKey; label: string; align: 'left' | 'right' }[] = [
    { key: 'symbol', label: 'Enstrüman', align: 'left' },
    { key: 'price', label: 'Fiyat', align: 'right' },
    { key: 'changePercent', label: 'Değişim', align: 'right' },
  ]

  return (
    <div className="flex flex-col h-full bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
      <div className="flex flex-col gap-4 sm:flex-row sm:items-center sm:justify-between mb-4">
        <div className="flex items-center gap-3">
          <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Enstrümanlar</h3>
          <div className="flex bg-slate-800/5 p-1 rounded-lg backdrop-blur-sm">
            {(['BIST', 'ABD', 'Kripto'] as MarketTab[]).map((tab) => (
              <button
                key={tab}
                onClick={() => setActiveTab(tab)}
                className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${
                  activeTab === tab ? 'bg-slate-800 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
                }`}
              >
                {tab}
              </button>
            ))}
          </div>
        </div>

        <div className="relative">
          <svg className="absolute left-3 top-1/2 -translate-y-1/2 h-4 w-4 text-slate-400" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
            <circle cx="11" cy="11" r="8" />
            <line x1="21" y1="21" x2="16.65" y2="16.65" />
          </svg>
          <input
            ref={searchInputRef}
            type="text"
            value={query}
            onChange={(e) => setQuery(e.target.value)}
            placeholder="Sembol veya şirket ara..."
            className="w-full sm:w-72 rounded-xl border border-white/10 bg-slate-800 pl-9 pr-16 py-2 text-sm text-slate-200 outline-none transition focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400"
          />
          <kbd className="hidden sm:inline-flex absolute right-2.5 top-1/2 -translate-y-1/2 items-center gap-0.5 rounded-md border border-white/10 bg-slate-800/5 px-1.5 py-0.5 text-[10px] font-semibold text-slate-400">
            Ctrl K
          </kbd>
        </div>
      </div>

      <div className="flex-1 overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[780px]">
          <thead>
            <tr className="border-b border-white/10/50">
              <th className="py-2 w-8" />
              {columns.map((col) => (
                <th
                  key={col.key}
                  onClick={() => handleSort(col.key)}
                  className={`py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 cursor-pointer select-none hover:text-slate-300 transition-colors ${
                    col.align === 'right' ? 'text-right' : 'text-left'
                  }`}
                >
                  <span className="inline-flex items-center gap-1">
                    {col.label}
                    {sortKey === col.key && (
                      <span className="text-emerald-500">{sortDir === 'asc' ? '▲' : '▼'}</span>
                    )}
                  </span>
                </th>
              ))}
              {activeColumnSet.key === 'getiri' ? (
                <>
                  <th onClick={() => handleSort('volume')} className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right cursor-pointer select-none hover:text-slate-300">
                    <span className="inline-flex items-center gap-1">
                      Hacim
                      {sortKey === 'volume' && <span className="text-emerald-500">{sortDir === 'asc' ? '▲' : '▼'}</span>}
                    </span>
                  </th>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Piyasa Değeri</th>
                  <th className="py-2 pl-6 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">52 Hafta</th>
                </>
              ) : (
                activeColumnSet.metrics.map((metric) => (
                  <th key={String(metric.key)} className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">
                    {metric.label}
                  </th>
                ))
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100/50">
            {rows.map((item) => (
              <tr
                key={item.symbol}
                onClick={() => navigate(`/investment/hisseler/${item.symbol}`)}
                className="hover:bg-slate-800/5/50 transition-colors group cursor-pointer"
              >
                <td className="py-3">
                  <button
                    onClick={(e) => { e.stopPropagation(); toggleFavorite(item.symbol) }}
                    aria-label={favorites.has(item.symbol) ? `${item.symbol} izlemeden çıkar` : `${item.symbol} izleme listesine ekle`}
                    title={favorites.has(item.symbol) ? 'İzleme listesinden çıkar' : 'İzleme listesine ekle'}
                    className={`transition-colors ${favorites.has(item.symbol) ? 'text-amber-400' : 'text-slate-300 hover:text-amber-300'}`}
                  >
                    <svg className="h-4 w-4" viewBox="0 0 24 24" fill={favorites.has(item.symbol) ? 'currentColor' : 'none'} stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                      <polygon points="12 2 15.09 8.26 22 9.27 17 14.14 18.18 21.02 12 17.77 5.82 21.02 7 14.14 2 9.27 8.91 8.26 12 2" />
                    </svg>
                  </button>
                </td>
                <td className="py-3">
                  <div className="font-semibold text-white text-sm hover:text-emerald-500 transition-colors">{item.symbol}</div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-xs text-slate-400">{item.name}</span>
                    <span className="text-[10px] font-medium text-slate-400 bg-slate-800/5 px-1.5 py-0.5 rounded">{item.sector}</span>
                  </div>
                </td>
                <td className="py-3 pl-4 text-right tabular-nums text-sm font-medium text-slate-200">
                  {formatPrice(item.price)} {item.unit}
                </td>
                <td className={`py-3 pl-4 text-right tabular-nums text-sm font-semibold ${item.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                  {item.changePercent > 0 ? '+' : ''}{item.changePercent.toFixed(2)}%
                </td>
                {activeColumnSet.key === 'getiri' ? (
                  <>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">{formatCompact(item.volume)}</td>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">{formatCompact(item.marketCap)} {item.unit}</td>
                    <td className="py-3 pl-6">
                      <Week52RangeBar low={item.week52Low} high={item.week52High} price={item.price} />
                    </td>
                  </>
                ) : (
                  activeColumnSet.metrics.map((metric) => (
                    <td key={String(metric.key)} className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">
                      {formatMetricValue(item, metric)}
                    </td>
                  ))
                )}
              </tr>
            ))}
            {rows.length === 0 && (
              <tr>
                <td colSpan={3 + (activeColumnSet.key === 'getiri' ? 3 : activeColumnSet.metrics.length)} className="py-8 text-center text-sm text-slate-400">
                  Aramanızla eşleşen enstrüman bulunamadı.
                </td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

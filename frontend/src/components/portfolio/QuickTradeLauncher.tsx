import { useCallback, useEffect, useMemo, useRef, useState } from 'react'
import { apiClient } from '../../api/client'
import type { InstrumentSuggestion, Position, WatchlistItem } from '../../api/client'
import TradeModal from './TradeModal'

interface QuickTradeLauncherProps {
  positions: Position[]
}

/** Kullanıcı yazmayı bırakana kadar beklenen süre. */
const DEBOUNCE_MS = 220

/**
 * Hızlı işlem: yazarak enstrüman arama.
 *
 * Önceden bir `<select>` idi ve yalnızca kullanıcının pozisyonlarını ve takip
 * listesini içeriyordu -- evren 190 enstrümanken bile dar, binin üzerine
 * çıkınca kullanılamaz. Arama sunucuda (`GET /api/market/search`), çünkü
 * Türkçe katlama orada: `sise` yazan `ŞİŞE`yi bulmalı ve bu kural
 * `market_service._fold`'da tek bir yerde duruyor.
 *
 * Kutu boşken kullanıcının kendi enstrümanları gösteriliyor: en sık işlem
 * yapacağı şeyler onlar ve boş bir liste, arama kutusunun ne beklediğini
 * söylemez.
 */
export default function QuickTradeLauncher({ positions }: QuickTradeLauncherProps) {
  const [watchlist, setWatchlist] = useState<Record<string, WatchlistItem[]>>({})
  const [query, setQuery] = useState('')
  const [remote, setRemote] = useState<InstrumentSuggestion[]>([])
  const [open, setOpen] = useState(false)
  const [highlighted, setHighlighted] = useState(0)
  const [selected, setSelected] = useState<
    { symbol: string; price: number; currency?: string } | null
  >(null)
  const [modalOpen, setModalOpen] = useState(false)
  const containerRef = useRef<HTMLDivElement>(null)

  useEffect(() => {
    apiClient
      .getWatchlist()
      .then(setWatchlist)
      .catch((error) => console.error('Failed to load watchlist for quick trade', error))
  }, [])

  /** Kutu boşken gösterilen liste: kullanıcının kendi enstrümanları. */
  const mine = useMemo(() => {
    const bySymbol = new Map<
      string, { symbol: string; price: number; currency?: string }
    >()
    for (const position of positions) {
      bySymbol.set(position.symbol, {
        symbol: position.symbol, price: position.price,
        currency: position.currency,
      })
    }
    for (const item of Object.values(watchlist).flat()) {
      if (!bySymbol.has(item.symbol)) {
        bySymbol.set(item.symbol, {
          symbol: item.symbol, price: item.price, currency: item.currency,
        })
      }
    }
    return [...bySymbol.values()]
  }, [positions, watchlist])

  // Her tuşta değil: yazmayı bırakınca aranır.
  useEffect(() => {
    const term = query.trim()
    if (!term) {
      setRemote([])
      return
    }
    let cancelled = false
    const timer = setTimeout(() => {
      apiClient
        .searchInstruments(term, 8)
        .then((rows) => {
          if (!cancelled) setRemote(rows)
        })
        // Arama başarısızsa liste boş kalır; kullanıcı yazmaya devam edebilir.
        .catch(() => undefined)
    }, DEBOUNCE_MS)
    return () => {
      cancelled = true
      clearTimeout(timer)
    }
  }, [query])

  const suggestions = useMemo(() => {
    if (!query.trim()) {
      return mine.map((row) => ({ symbol: row.symbol, name: null as string | null }))
    }
    return remote.map((row) => ({ symbol: row.symbol, name: row.name ?? null }))
  }, [query, mine, remote])

  useEffect(() => setHighlighted(0), [suggestions.length])

  // Dışarı tıklayınca kapanır.
  useEffect(() => {
    function onClick(event: MouseEvent) {
      if (!containerRef.current?.contains(event.target as Node)) setOpen(false)
    }
    document.addEventListener('mousedown', onClick)
    return () => document.removeEventListener('mousedown', onClick)
  }, [])

  const choose = useCallback(
    (symbol: string) => {
      // Fiyat, kullanıcının kendi satırından biliniyorsa oradan; bilinmiyorsa
      // 0 geçilmez -- TradeModal fiyatı kendisi çeker ve sıfır, gerçek bir
      // fiyat gibi okunurdu.
      const known = mine.find((row) => row.symbol === symbol)
      // Para birimi de kendi satırından: bilinmiyorsa GEÇİLMİYOR ve
      // `TradeModal` kendi varsayılanına düşüyor. Buradan "TRY" uydurmak,
      // bir dolar hissesini liraya fiyatlamak olurdu.
      setSelected({ symbol, price: known?.price ?? NaN, currency: known?.currency })
      setQuery(symbol)
      setOpen(false)
      setModalOpen(true)
    },
    [mine],
  )

  function onKeyDown(event: React.KeyboardEvent<HTMLInputElement>) {
    if (!open || suggestions.length === 0) return
    if (event.key === 'ArrowDown') {
      event.preventDefault()
      setHighlighted((index) => (index + 1) % suggestions.length)
    } else if (event.key === 'ArrowUp') {
      event.preventDefault()
      setHighlighted((index) => (index - 1 + suggestions.length) % suggestions.length)
    } else if (event.key === 'Enter') {
      event.preventDefault()
      choose(suggestions[highlighted].symbol)
    } else if (event.key === 'Escape') {
      setOpen(false)
    }
  }

  return (
    <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] p-5 border border-white/10 shadow-2xl">
      <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-4">
        Hızlı İşlem
      </h3>

      <div className="flex flex-col sm:flex-row gap-3">
        <div ref={containerRef} className="relative flex-1">
          <input
            type="text"
            value={query}
            onChange={(event) => {
              setQuery(event.target.value)
              setOpen(true)
            }}
            onFocus={() => setOpen(true)}
            onKeyDown={onKeyDown}
            placeholder="Hisse ara — sembol ya da şirket adı"
            aria-label="Enstrüman ara"
            aria-autocomplete="list"
            aria-expanded={open}
            role="combobox"
            className="w-full rounded-xl border border-white/10 bg-slate-800 px-3 py-2.5 text-sm font-medium text-slate-200 placeholder:text-slate-500 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
          />

          {open && suggestions.length > 0 && (
            <ul
              role="listbox"
              className="absolute z-20 mt-1 max-h-64 w-full overflow-y-auto rounded-xl border border-white/10 bg-slate-900 py-1 shadow-2xl"
            >
              {!query.trim() && (
                <li className="px-3 py-1 text-[10px] uppercase tracking-wide text-slate-500">
                  Portföyünüz ve takip listeniz
                </li>
              )}
              {suggestions.map((row, index) => (
                <li key={row.symbol} role="option" aria-selected={index === highlighted}>
                  <button
                    onMouseEnter={() => setHighlighted(index)}
                    onClick={() => choose(row.symbol)}
                    className={`flex w-full items-baseline gap-2 px-3 py-2 text-left text-sm transition ${
                      index === highlighted ? 'bg-white/10 text-white' : 'text-slate-300'
                    }`}
                  >
                    <span className="font-semibold">{row.symbol}</span>
                    {row.name && row.name !== row.symbol && (
                      <span className="truncate text-xs text-slate-500">{row.name}</span>
                    )}
                  </button>
                </li>
              ))}
            </ul>
          )}
        </div>

        <button
          onClick={() => selected && setModalOpen(true)}
          disabled={!selected}
          className="rounded-xl bg-emerald-500 text-white px-5 py-2.5 text-sm font-semibold shadow-sm shadow-emerald-500/30 hover:bg-emerald-600 transition-colors disabled:opacity-50"
        >
          Al / Sat
        </button>
      </div>

      {modalOpen && selected && (
        <TradeModal
          symbol={selected.symbol}
          price={selected.price}
          // Para birimi TAŞINMIYORDU: `TradeModal` varsayılan olarak TRY
          // kullanıyor ve bir ABD hissesinin dolar fiyatı liraya
          // fiyatlanmış görünüyordu.
          currency={selected.currency}
          onClose={() => setModalOpen(false)}
        />
      )}
    </div>
  )
}

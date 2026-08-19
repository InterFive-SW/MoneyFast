import { useEffect, useMemo, useState } from 'react'
import { apiClient } from '../../api/client'
import type { Position, WatchlistItem } from '../../api/client'
import TradeModal from './TradeModal'

interface QuickTradeLauncherProps {
  positions: Position[]
}

interface SymbolOption {
  symbol: string
  price: number
  group: 'Pozisyonlarım' | 'Takip Listesi'
}

export default function QuickTradeLauncher({ positions }: QuickTradeLauncherProps) {
  const [watchlist, setWatchlist] = useState<Record<string, WatchlistItem[]>>({})
  const [selectedSymbol, setSelectedSymbol] = useState<string>('')
  const [modalOpen, setModalOpen] = useState(false)

  useEffect(() => {
    async function loadWatchlist() {
      try {
        const data = await apiClient.getWatchlist()
        setWatchlist(data)
      } catch (error) {
        console.error('Failed to load watchlist for quick trade', error)
      }
    }
    loadWatchlist()
  }, [])

  const options = useMemo<SymbolOption[]>(() => {
    const fromPositions: SymbolOption[] = positions.map((pos) => ({
      symbol: pos.symbol,
      price: pos.price,
      group: 'Pozisyonlarım',
    }))
    const watchlistFlat = Object.values(watchlist).flat()
    const knownSymbols = new Set(fromPositions.map((o) => o.symbol))
    const fromWatchlist: SymbolOption[] = watchlistFlat
      .filter((item) => !knownSymbols.has(item.symbol))
      .map((item) => ({ symbol: item.symbol, price: item.price, group: 'Takip Listesi' }))
    return [...fromPositions, ...fromWatchlist]
  }, [positions, watchlist])

  useEffect(() => {
    if (!selectedSymbol && options.length > 0) {
      setSelectedSymbol(options[0].symbol)
    }
  }, [options, selectedSymbol])

  const selectedOption = options.find((o) => o.symbol === selectedSymbol)

  return (
    <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] p-5 border border-white/10 shadow-2xl">
      <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-4">Hızlı İşlem</h3>

      <div className="flex flex-col sm:flex-row gap-3">
        <select
          value={selectedSymbol}
          onChange={(e) => setSelectedSymbol(e.target.value)}
          className="flex-1 rounded-xl border border-white/10 bg-slate-800 px-3 py-2.5 text-sm font-medium text-slate-200 focus:outline-none focus:ring-2 focus:ring-emerald-500/40"
        >
          {['Pozisyonlarım', 'Takip Listesi'].map((group) => {
            const groupOptions = options.filter((o) => o.group === group)
            if (groupOptions.length === 0) return null
            return (
              <optgroup key={group} label={group}>
                {groupOptions.map((o) => (
                  <option key={o.symbol} value={o.symbol}>
                    {o.symbol}
                  </option>
                ))}
              </optgroup>
            )
          })}
        </select>

        <button
          onClick={() => setModalOpen(true)}
          disabled={!selectedOption}
          className="rounded-xl bg-emerald-500 text-white px-5 py-2.5 text-sm font-semibold shadow-sm shadow-emerald-500/30 hover:bg-emerald-600 transition-colors disabled:opacity-50"
        >
          Al / Sat
        </button>
      </div>

      {modalOpen && selectedOption && (
        <TradeModal symbol={selectedOption.symbol} price={selectedOption.price} onClose={() => setModalOpen(false)} />
      )}
    </div>
  )
}

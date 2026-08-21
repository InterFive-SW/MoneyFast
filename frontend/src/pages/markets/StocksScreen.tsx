import { useMemo, useState } from 'react'
import type { ColumnSetKey } from '../../data/columnSets'
import { useInstruments } from '../../hooks/useInstruments'
import NewsWidget from '../../components/widgets/NewsWidget'
import MarketInstrumentsTable from '../../components/markets/MarketInstrumentsTable'
import MarketMoversWidget from '../../components/markets/MarketMoversWidget'
import MarketComparisonChart from '../../components/markets/MarketComparisonChart'
import ColumnSetSwitcher from '../../components/markets/ColumnSetSwitcher'
import StockFilterPanel, { EMPTY_STOCK_FILTERS, applyStockFilters, type StockFilters } from '../../components/markets/StockFilterPanel'

/** Hangi piyasanın gösterileceği. Evren artık iki borsayı kapsıyor. */
type MarketChoice = 'Tümü' | 'BIST' | 'ABD'
const MARKET_CHOICES: MarketChoice[] = ['Tümü', 'BIST', 'ABD']

export default function StocksScreen() {
  const [columnSet, setColumnSet] = useState<ColumnSetKey>('getiri')
  const [filters, setFilters] = useState<StockFilters>(EMPTY_STOCK_FILTERS)
  const [market, setMarket] = useState<MarketChoice>('Tümü')

  // Canlı evren: açılışta bir kez çekilir, fiyatlar SSE ile güncellenir.
  // Sektör listesi de buradan gelir — sabit bir listeyle canlı veride
  // karşılığı olmayan sektörler süzgeçte görünürdü.
  const { instruments, loading, sectors } = useInstruments()

  // Piyasa süzgeci diğer süzgeçlerden ÖNCE uygulanır: sektör listesi ve
  // karşılaştırmalar da seçilen piyasaya göre daralsın.
  const inMarket = useMemo(
    () => (market === 'Tümü' ? instruments : instruments.filter((i) => i.market === market)),
    [instruments, market]
  )

  const filteredInstruments = useMemo(
    () => applyStockFilters(inMarket, filters),
    [inMarket, filters]
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  return (
    <div>
      <div className="mb-6 flex flex-wrap items-center gap-3">
        <div className="flex rounded-lg border border-white/10 bg-slate-900/50 p-1">
          {MARKET_CHOICES.map((choice) => (
            <button
              key={choice}
              onClick={() => setMarket(choice)}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
                market === choice
                  ? 'bg-white/10 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {choice}
              {choice !== 'Tümü' && (
                <span className="ml-1.5 tabular-nums text-[10px] text-slate-500">
                  {instruments.filter((i) => i.market === choice).length}
                </span>
              )}
            </button>
          ))}
        </div>
        <ColumnSetSwitcher value={columnSet} onChange={setColumnSet} />
      </div>

      <StockFilterPanel filters={filters} onChange={setFilters} sectors={sectors} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2">
          <MarketInstrumentsTable instruments={filteredInstruments} columnSet={columnSet} />
        </div>

        <div className="flex flex-col gap-6">
          <div className="h-[320px]">
            <MarketMoversWidget instruments={filteredInstruments} />
          </div>
          <div className="h-[420px]">
            <NewsWidget />
          </div>
        </div>
      </div>

      <MarketComparisonChart instruments={filteredInstruments} />
    </div>
  )
}

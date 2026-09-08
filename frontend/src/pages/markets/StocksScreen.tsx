import { useMemo, useState } from 'react'
import type { ColumnSetKey } from '../../data/columnSets'
import { useInstruments } from '../../hooks/useInstruments'
import NewsWidget from '../../components/widgets/NewsWidget'
import MarketInstrumentsTable from '../../components/markets/MarketInstrumentsTable'
import MarketMoversWidget from '../../components/markets/MarketMoversWidget'
import YonTaramasi from '../../components/markets/YonTaramasi'
import MarketComparisonChart from '../../components/markets/MarketComparisonChart'
import ColumnSetSwitcher from '../../components/markets/ColumnSetSwitcher'
import StockFilterPanel, { EMPTY_STOCK_FILTERS, applyStockFilters, type StockFilters } from '../../components/markets/StockFilterPanel'

/**
 * Hangi piyasa gösterilecek.
 *
 * `value` sunucuya gider ve bir BORSA (BIST, NASDAQ) ya da bir ENDEKS
 * (SP500) olabilir. İkisi aynı alanda taşınıyor çünkü ayrım gerçek: AAPL
 * Nasdaq'ta işlem görür VE S&P 500 üyesidir, dolayısıyla her iki sekmede de
 * görünmesi doğru. `market` sütunu tek başına bunu ifade edemezdi.
 */
type MarketChoice = { label: string; value?: string }
const MARKET_CHOICES: MarketChoice[] = [
  { label: 'Tümü' },
  { label: 'BIST', value: 'BIST' },
  { label: 'Nasdaq', value: 'NASDAQ' },
  { label: 'S&P 500', value: 'SP500' },
]

export default function StocksScreen() {
  const [columnSet, setColumnSet] = useState<ColumnSetKey>('getiri')
  const [filters, setFilters] = useState<StockFilters>(EMPTY_STOCK_FILTERS)
  const [market, setMarket] = useState<MarketChoice>(MARKET_CHOICES[0])

  // Canlı evren: açılışta bir kez çekilir, fiyatlar SSE ile güncellenir.
  // Sektör listesi de buradan gelir — sabit bir listeyle canlı veride
  // karşılığı olmayan sektörler süzgeçte görünürdü.
  // Süzgeç sunucuda: evren binin üzerinde enstrüman, istemcide ilk sayfayı
  // süzmek seçilen piyasanın yalnızca bir kısmını göstermek olurdu.
  const { instruments, loading, sectors } = useInstruments(1200, market.value)

  const filteredInstruments = useMemo(
    () => applyStockFilters(instruments, filters),
    [instruments, filters]
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
              key={choice.label}
              onClick={() => setMarket(choice)}
              className={`rounded-md px-3 py-1 text-xs font-semibold transition-colors ${
                market.label === choice.label
                  ? 'bg-white/10 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {choice.label}
            </button>
          ))}
        </div>
        <ColumnSetSwitcher value={columnSet} onChange={setColumnSet} />
      </div>

      <StockFilterPanel filters={filters} onChange={setFilters} sectors={sectors} />

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6 mb-6">
        <div className="lg:col-span-2">
          <MarketInstrumentsTable instruments={filteredInstruments} columnSet={columnSet} showMarketTabs={false} />
        </div>

        <div className="flex flex-col gap-6">
          <div className="h-[320px]">
            <MarketMoversWidget instruments={filteredInstruments} />
          </div>
          {/* Gecelik hesaplanmış yön okumaları. "En iyi hisseler" değil:
              sıralanan şey ölçülen kanıtların meyli. */}
          <div className="h-[360px]">
            <YonTaramasi />
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

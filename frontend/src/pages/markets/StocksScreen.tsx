import { useMemo, useState } from 'react'
import type { ColumnSetKey } from '../../data/columnSets'
import { useInstruments } from '../../hooks/useInstruments'
import NewsWidget from '../../components/widgets/NewsWidget'
import MarketInstrumentsTable from '../../components/markets/MarketInstrumentsTable'
import MarketMoversWidget from '../../components/markets/MarketMoversWidget'
import MarketComparisonChart from '../../components/markets/MarketComparisonChart'
import ColumnSetSwitcher from '../../components/markets/ColumnSetSwitcher'
import StockFilterPanel, { EMPTY_STOCK_FILTERS, applyStockFilters, type StockFilters } from '../../components/markets/StockFilterPanel'

export default function StocksScreen() {
  const [columnSet, setColumnSet] = useState<ColumnSetKey>('getiri')
  const [filters, setFilters] = useState<StockFilters>(EMPTY_STOCK_FILTERS)

  // Canlı evren: açılışta bir kez çekilir, fiyatlar SSE ile güncellenir.
  // Sektör listesi de buradan gelir — sabit bir listeyle canlı veride
  // karşılığı olmayan sektörler süzgeçte görünürdü.
  const { instruments, loading, sectors } = useInstruments()

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
      <div className="mb-6">
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

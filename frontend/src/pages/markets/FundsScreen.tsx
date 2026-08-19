import { useMemo, useState } from 'react'
import { MOCK_FUNDS } from '../../data/mockData'
import FundsTable from '../../components/markets/FundsTable'
import FundFilterPanel, { EMPTY_FUND_FILTERS, applyFundFilters, type FundFilters } from '../../components/markets/FundFilterPanel'
import FundComparisonChart from '../../components/markets/FundComparisonChart'

export default function FundsScreen() {
  const [filters, setFilters] = useState<FundFilters>(EMPTY_FUND_FILTERS)

  const founders = useMemo(() => Array.from(new Set(MOCK_FUNDS.map((f) => f.founder))).sort(), [])
  const umbrellas = useMemo(() => Array.from(new Set(MOCK_FUNDS.map((f) => f.umbrella))).sort(), [])

  const filteredFunds = useMemo(() => applyFundFilters(MOCK_FUNDS, filters), [filters])

  return (
    <div>
      <FundFilterPanel filters={filters} onChange={setFilters} founders={founders} umbrellas={umbrellas} />

      <div className="mb-6">
        <FundsTable funds={filteredFunds} />
      </div>

      <FundComparisonChart funds={filteredFunds} />
    </div>
  )
}

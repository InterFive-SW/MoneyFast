import { useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import type { Position } from '../api/client'
import PortfolioSummaryBar from '../components/portfolio/PortfolioSummaryBar'
import PortfolioHighlights from '../components/portfolio/PortfolioHighlights'
import QuickTradeLauncher from '../components/portfolio/QuickTradeLauncher'
import PositionsWidget from '../components/widgets/PositionsWidget'
import PortfolioChartWidget from '../components/widgets/PortfolioChartWidget'
import AssetAllocationWidget from '../components/widgets/AssetAllocationWidget'
import WatchlistWidget from '../components/widgets/WatchlistWidget'

export default function Portfolio() {
  const [positions, setPositions] = useState<Position[]>([])
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    async function loadData() {
      try {
        const data = await apiClient.getPositions()
        setPositions(data)
      } catch (error) {
        console.error('Failed to load positions for portfolio summary', error)
      } finally {
        setLoading(false)
      }
    }
    loadData()
  }, [])

  return (
    <div className="p-6 sm:p-8 min-h-screen">
      <div className="mb-6">
        <h1 className="text-2xl font-bold tracking-tight text-slate-900">Portföyüm</h1>
        <p className="text-sm text-slate-500 mt-1">
          Hisse senedi, altın ve döviz varlıklarınızın dağılımını ve performansını tek bir ekranda görüntüleyin.
        </p>
      </div>

      <div className="mb-6">
        <PortfolioSummaryBar positions={positions} loading={loading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="h-[420px]">
            <PortfolioChartWidget />
          </div>
          <PositionsWidget />
        </div>

        <div className="flex flex-col gap-6">
          <div className="h-[280px]">
            <AssetAllocationWidget />
          </div>
          <PortfolioHighlights positions={positions} loading={loading} />
          <div className="h-[360px]">
            <WatchlistWidget />
          </div>
        </div>
      </div>

      <div className="mt-6">
        <QuickTradeLauncher positions={positions} />
      </div>
    </div>
  )
}

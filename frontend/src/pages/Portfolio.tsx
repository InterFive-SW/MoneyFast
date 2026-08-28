import { useEffect, useState } from 'react'
import { apiClient } from '../api/client'
import type { Position } from '../api/client'
import PortfolioSummaryBar from '../components/portfolio/PortfolioSummaryBar'
import PortfolioHighlights from '../components/portfolio/PortfolioHighlights'
import QuickTradeLauncher from '../components/portfolio/QuickTradeLauncher'
import PortfolioPerformanceChart from '../components/portfolio/PortfolioPerformanceChart'
import PositionsWidget from '../components/widgets/PositionsWidget'
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
        <h1 className="text-2xl font-bold tracking-tight text-white">Portföyüm</h1>
        <p className="text-sm text-slate-400 mt-1">
          Hisse senedi, altın ve döviz varlıklarınızın dağılımını ve performansını tek bir ekranda görüntüleyin.
        </p>
      </div>

      <div className="mb-6">
        <PortfolioSummaryBar positions={positions} loading={loading} />
      </div>

      <div className="grid grid-cols-1 lg:grid-cols-3 gap-6">
        <div className="lg:col-span-2 flex flex-col gap-6">
          <div className="h-[420px]">
            <PortfolioPerformanceChart />
          </div>
          <PositionsWidget />
        </div>

        {/* Varlık dağılımı buradan çıktı: Analiz ekranında da vardı ve aynı
            bilgiyi iki ekranda göstermenin bir sebebi yok. Portföyüm artık
            operasyonel ekran — ne tutuyorum, ne izliyorum; dağılım ve
            performans yorumu Analiz'in işi. */}
        <div className="flex flex-col gap-6">
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

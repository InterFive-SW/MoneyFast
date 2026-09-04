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

  const [isBriefingLoading, setIsBriefingLoading] = useState(false)
  const [status, setStatus] = useState<{type: 'success' | 'error', message: string} | null>(null)

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

  const handleSendBriefing = async () => {
    setIsBriefingLoading(true)
    setStatus(null)
    try {
      const res = await apiClient.sendMarketBriefingNow()
      setStatus({ type: 'success', message: res.message || 'Bülten hazırlanıp e-posta adresinize gönderiliyor.' })
      setTimeout(() => setStatus(null), 5000)
    } catch (err: any) {
      setStatus({ type: 'error', message: err.response?.data?.detail || err.message || 'Bülten gönderilirken bir hata oluştu.' })
      setTimeout(() => setStatus(null), 5000)
    } finally {
      setIsBriefingLoading(false)
    }
  }

  return (
    <div className="p-6 sm:p-8 min-h-screen">
      <div className="mb-6 flex justify-between items-start">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Portföyüm</h1>
          <p className="text-sm text-slate-400 mt-1">
            Hisse senedi, altın ve döviz varlıklarınızın dağılımını ve performansını tek bir ekranda görüntüleyin.
          </p>
        </div>
        
        <div className="flex flex-col items-end">
          <button
            onClick={handleSendBriefing}
            disabled={isBriefingLoading}
            className="px-4 py-2 bg-[#4b7be5]/10 text-[#4b7be5] border border-[#4b7be5]/30 hover:bg-[#4b7be5]/20 rounded-xl text-sm font-medium transition-colors flex items-center gap-2 disabled:opacity-50"
          >
            {isBriefingLoading ? (
              <svg className="animate-spin h-4 w-4" xmlns="http://www.w3.org/2000/svg" fill="none" viewBox="0 0 24 24">
                <circle className="opacity-25" cx="12" cy="12" r="10" stroke="currentColor" strokeWidth="4"></circle>
                <path className="opacity-75" fill="currentColor" d="M4 12a8 8 0 018-8V0C5.373 0 0 5.373 0 12h4zm2 5.291A7.962 7.962 0 014 12H0c0 3.042 1.135 5.824 3 7.938l3-2.647z"></path>
              </svg>
            ) : (
              <svg className="w-4 h-4" fill="none" stroke="currentColor" viewBox="0 0 24 24">
                <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M3 8l7.89 5.26a2 2 0 002.22 0L21 8M5 19h14a2 2 0 002-2V7a2 2 0 00-2-2H5a2 2 0 00-2 2v10a2 2 0 002 2z" />
              </svg>
            )}
            <span>Portföy Özetini Gönder</span>
          </button>
          
          {status && (
            <div className={`mt-2 text-xs font-medium px-2 py-1 rounded-md ${
              status.type === 'success' 
                ? 'bg-emerald-500/10 text-emerald-400' 
                : 'bg-rose-500/10 text-rose-400'
            }`}>
              {status.message}
            </div>
          )}
        </div>
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

import { useEffect, useState } from 'react'
import { Outlet } from 'react-router-dom'
import { apiClient } from '../api/client'
import type { MarketInstrument, MarketTicker } from '../api/client'
import MarketTickerWidget from '../components/widgets/MarketTickerWidget'
import MarketStatusBadge from '../components/markets/MarketStatusBadge'
import MarketPulseSummary from '../components/markets/MarketPulseSummary'
import MarketsSubNav from '../components/markets/MarketsSubNav'

/**
 * Piyasalar — ince kabuk sayfa. Ortak üst bölüm (başlık, piyasa durumu, nabız
 * özeti, ticker şeridi, alt-sekme navigasyonu) burada; her bölümün asıl içeriği
 * `pages/markets/*` altındaki alt rotalarda (`<Outlet />`) render edilir.
 */
export default function Investment() {
  // Nabız özeti tüm evrenin genişliğini ölçer (kaç enstrüman yükseldi/düştü),
  // bu yüzden şeritteki dört başlıktan ayrı olarak enstrüman listesi çekilir.
  const [instruments, setInstruments] = useState<MarketInstrument[]>([])
  const [tickers, setTickers] = useState<MarketTicker[]>([])

  useEffect(() => {
    apiClient
      .getInstruments({ top_k: 200 })
      .then((response) => setInstruments(response.instruments ?? []))
      .catch((error) => console.error('Failed to load instruments', error))
    apiClient
      .getMarketTickers()
      .then(setTickers)
      .catch((error) => console.error('Failed to load tickers', error))
  }, [])

  const movements = instruments
    // Fiyatı olmayan enstrüman bir hareket değil, bir boşluktur; 0 sayarak
    // "yatay kaldı" demek sayımı bozardı.
    .filter((row) => row.change_percent != null)
    .map((row) => ({ symbol: row.symbol, changePercent: row.change_percent as number }))

  const tickerMovements = tickers.map((row) => ({
    symbol: row.symbol,
    changePercent: row.changePercent ?? 0,
  }))

  return (
    <div className="p-6 sm:p-8 min-h-screen">
      <div className="mb-6 flex flex-col gap-3 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Piyasalar</h1>
          <p className="text-sm text-slate-400 mt-1">
            Hisseler, fonlar, endeksler, sektörler ve piyasa geneli analizleri tek ekrandan takip edin.
          </p>
        </div>
        <MarketStatusBadge />
      </div>

      <MarketPulseSummary instruments={movements} tickers={tickerMovements} />

      <div className="mb-6 bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
        <MarketTickerWidget />
      </div>

      <MarketsSubNav />

      <Outlet />
    </div>
  )
}

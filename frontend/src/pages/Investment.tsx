import { Outlet } from 'react-router-dom'
import { MOCK_MARKET_TICKERS, MOCK_MARKET_INSTRUMENTS } from '../data/mockData'
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

      <MarketPulseSummary instruments={MOCK_MARKET_INSTRUMENTS} tickers={MOCK_MARKET_TICKERS} />

      <div className="mb-6 bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
        <MarketTickerWidget tickers={MOCK_MARKET_TICKERS} />
      </div>

      <MarketsSubNav />

      <Outlet />
    </div>
  )
}

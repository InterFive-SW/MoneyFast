import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { findInstrument, MOCK_EARNINGS_REPORTS, MOCK_DIVIDEND_ANNOUNCEMENTS, MOCK_FUNDS } from '../../data/mockData'

type DetailTab = 'ozet' | 'finansallar' | 'oran-analizi' | 'temettu' | 'fon-pozisyonlari'

const TABS: { key: DetailTab; label: string }[] = [
  { key: 'ozet', label: 'Özet' },
  { key: 'finansallar', label: 'Finansallar' },
  { key: 'oran-analizi', label: 'Oran Analizi' },
  { key: 'temettu', label: 'Temettü' },
  { key: 'fon-pozisyonlari', label: 'Fon Pozisyonları' },
]

export function fmt(value: number | undefined, opts: Intl.NumberFormatOptions = {}): string {
  if (value === undefined) return '—'
  return value.toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1, ...opts })
}

// Mock verisinde pe/netMargin tanımlı olan her enstrümanın revenueGrowth'u da tanımlı
// geliyor (bkz. data/mockData.ts) — bu iki yardımcının undefined dalları testle ulaşılamaz.
function revenueGrowthColor(revenueGrowth: number | undefined): string {
  /* v8 ignore next */
  return (revenueGrowth ?? 0) < 0 ? 'text-rose-500' : 'text-emerald-500'
}

function revenueGrowthLabel(revenueGrowth: number | undefined): string {
  /* v8 ignore next */
  if (revenueGrowth === undefined) return '—'
  return `${revenueGrowth > 0 ? '+' : ''}${revenueGrowth}%`
}

function fmtCompact(value: number): string {
  return new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

/** Hisse detay sayfası — /investment/hisseler/:symbol, 5 sekme (Fintables'ın "onlarca sekme"sinin V1'de daraltılmış hali) */
export default function StockDetail() {
  const { symbol = '' } = useParams()
  const [activeTab, setActiveTab] = useState<DetailTab>('ozet')

  const instrument = findInstrument(symbol.toUpperCase())

  const earningsReport = useMemo(
    () => MOCK_EARNINGS_REPORTS.find((r) => r.symbol === symbol.toUpperCase()),
    [symbol]
  )
  const dividends = useMemo(
    () => MOCK_DIVIDEND_ANNOUNCEMENTS.filter((d) => d.symbol === symbol.toUpperCase()),
    [symbol]
  )
  const holdingFunds = useMemo(
    () => MOCK_FUNDS
      .map((fund) => ({ fund, holding: fund.holdings.find((h) => h.symbol === symbol.toUpperCase()) }))
      .filter((x): x is { fund: typeof MOCK_FUNDS[0]; holding: { symbol: string; weight: number } } => Boolean(x.holding))
      .sort((a, b) => b.holding.weight - a.holding.weight),
    [symbol]
  )

  if (!instrument) {
    return (
      <div className="bg-slate-800/70 backdrop-blur-md rounded-[2rem] p-8 border border-white/50 shadow-sm text-center">
        <p className="text-sm text-slate-400 mb-3">"{symbol}" için bir enstrüman bulunamadı.</p>
        <Link to="/investment/hisseler" className="text-sm font-semibold text-emerald-500 hover:text-emerald-400">
          ← Hisseler listesine dön
        </Link>
      </div>
    )
  }

  const derivedNetIncome = instrument.pe ? instrument.marketCap / instrument.pe : undefined
  const derivedRevenue = derivedNetIncome && instrument.netMargin ? derivedNetIncome / (instrument.netMargin / 100) : undefined

  return (
    <div>
      <Link to="/investment/hisseler" className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-emerald-500 mb-4 transition-colors">
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        Hisseler listesine dön
      </Link>

      <div className="bg-slate-800/70 backdrop-blur-md rounded-[2rem] p-6 border border-white/50 shadow-sm mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-white">{instrument.symbol}</h1>
              <span className="text-[10px] font-medium text-slate-400 bg-slate-800/5 px-1.5 py-0.5 rounded">{instrument.sector}</span>
              <span className="text-[10px] font-medium text-slate-400 bg-slate-800/5 px-1.5 py-0.5 rounded">{instrument.market}</span>
            </div>
            <p className="text-sm text-slate-400 mt-0.5">{instrument.name}</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold tabular-nums text-white">{fmt(instrument.price, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {instrument.unit}</div>
            <div className={`text-sm font-semibold tabular-nums ${instrument.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
              {instrument.changePercent > 0 ? '+' : ''}{instrument.changePercent.toFixed(2)}%
            </div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap bg-slate-800/5 p-1 rounded-lg w-fit mb-6">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3.5 py-1.5 text-sm font-semibold rounded-md transition-all ${
              activeTab === tab.key ? 'bg-slate-800 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="bg-slate-800/70 backdrop-blur-md rounded-[2rem] p-6 border border-white/50 shadow-sm">
        {activeTab === 'ozet' && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: 'Piyasa Değeri', value: `${fmtCompact(instrument.marketCap)} ${instrument.unit}` },
              { label: 'Hacim', value: fmtCompact(instrument.volume) },
              { label: '52 Hafta Düşük', value: `${fmt(instrument.week52Low, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${instrument.unit}` },
              { label: '52 Hafta Yüksek', value: `${fmt(instrument.week52High, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${instrument.unit}` },
              { label: 'F/K', value: instrument.pe ? `${fmt(instrument.pe)}x` : '—' },
              { label: 'PD/DD', value: instrument.pb ? `${fmt(instrument.pb)}x` : '—' },
              ...(instrument.indexWeight ? [{ label: 'BIST 100 Ağırlığı', value: `%${fmt(instrument.indexWeight)}` }] : []),
              ...(earningsReport ? [{ label: `Son Bilanço (${earningsReport.period})`, value: `${earningsReport.surprise > 0 ? '+' : ''}${earningsReport.surprise}% sürpriz` }] : []),
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl bg-slate-800/5/60 p-3.5">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-slate-400 mb-1">{stat.label}</div>
                <div className="text-sm font-bold tabular-nums text-white">{stat.value}</div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'finansallar' && (
          derivedRevenue && derivedNetIncome ? (
            <div className="space-y-4">
              {earningsReport && (
                <div className="rounded-xl bg-emerald-500/100/10 border border-emerald-500/20 p-4 text-sm text-slate-200">
                  <span className="font-semibold text-emerald-400">{earningsReport.period} bilançosu</span> — beklenti EPS {fmt(earningsReport.epsExpected, { minimumFractionDigits: 2, maximumFractionDigits: 2 })}, gerçekleşen {fmt(earningsReport.epsActual, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ({earningsReport.surprise > 0 ? '+' : ''}{earningsReport.surprise}%)
                </div>
              )}
              <table className="w-full text-left border-collapse">
                <tbody className="divide-y divide-slate-100">
                  <tr><td className="py-2.5 text-sm text-slate-400">Tahmini Yıllık Gelir</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">{fmtCompact(derivedRevenue)} {instrument.unit}</td></tr>
                  <tr><td className="py-2.5 text-sm text-slate-400">Tahmini Yıllık Net Kâr</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">{fmtCompact(derivedNetIncome)} {instrument.unit}</td></tr>
                  <tr><td className="py-2.5 text-sm text-slate-400">Toplam Varlıklar</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">{instrument.totalAssets ? `${fmtCompact(instrument.totalAssets)} ${instrument.unit}` : '—'}</td></tr>
                  <tr><td className="py-2.5 text-sm text-slate-400">Faaliyet Nakit Akışı</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">{instrument.operatingCashFlow ? `${fmtCompact(instrument.operatingCashFlow)} ${instrument.unit}` : '—'}</td></tr>
                  <tr><td className="py-2.5 text-sm text-slate-400">Yıllık Gelir Büyümesi</td><td className={`py-2.5 text-right text-sm font-semibold tabular-nums ${revenueGrowthColor(instrument.revenueGrowth)}`}>{revenueGrowthLabel(instrument.revenueGrowth)}</td></tr>
                </tbody>
              </table>
              <p className="text-[11px] text-slate-400">Gelir/net kâr rakamları F/K ve net kâr marjından türetilmiş tahmini değerlerdir (mock veri).</p>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Bu enstrüman için finansal tablo verisi bulunmuyor.</p>
          )
        )}

        {activeTab === 'oran-analizi' && (
          instrument.pe !== undefined ? (
            <table className="w-full text-left border-collapse">
              <tbody className="divide-y divide-slate-100">
                <tr><td className="py-2.5 text-sm text-slate-400">F/K</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">{fmt(instrument.pe)}x</td></tr>
                <tr><td className="py-2.5 text-sm text-slate-400">PD/DD</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">{fmt(instrument.pb)}x</td></tr>
                <tr><td className="py-2.5 text-sm text-slate-400">FD/FAVÖK</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">{fmt(instrument.evEbitda)}x</td></tr>
                <tr><td className="py-2.5 text-sm text-slate-400">Net Kâr Marjı</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">%{fmt(instrument.netMargin)}</td></tr>
                <tr><td className="py-2.5 text-sm text-slate-400">Özkaynak Kârlılığı (ROE)</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">%{fmt(instrument.roe)}</td></tr>
                <tr><td className="py-2.5 text-sm text-slate-400">Borç/Özkaynak</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-white">{fmt(instrument.debtToEquity)}x</td></tr>
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-400">Bu enstrüman için oran analizi verisi bulunmuyor.</p>
          )
        )}

        {activeTab === 'temettu' && (
          dividends.length > 0 ? (
            <table className="w-full text-left border-collapse">
              <thead>
                <tr className="border-b border-white/10/50">
                  <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Hisse Başı</th>
                  <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Verim</th>
                  <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Ex-Date</th>
                  <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Ödeme Tarihi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100">
                {dividends.map((d, i) => (
                  <tr key={i}>
                    <td className="py-2.5 text-sm font-semibold tabular-nums text-white">{fmt(d.amountPerShare, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ₺</td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-emerald-500 font-semibold">%{fmt(d.yieldPercent)}</td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-300">{d.exDate}</td>
                    <td className="py-2.5 text-right text-sm tabular-nums text-slate-300">{d.paymentDate}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          ) : (
            <p className="text-sm text-slate-400">Bu hisse için planlanmış bir temettü bulunmuyor.</p>
          )
        )}

        {activeTab === 'fon-pozisyonlari' && (
          holdingFunds.length > 0 ? (
            <div className="flex flex-col gap-2">
              {holdingFunds.map(({ fund, holding }) => (
                <Link
                  key={fund.code}
                  to={`/investment/fonlar/${fund.code}`}
                  className="flex items-center justify-between p-3 bg-slate-800/5/60 hover:bg-slate-800/5/60 rounded-xl transition-colors"
                >
                  <div>
                    <div className="text-sm font-semibold text-white">{fund.name}</div>
                    <div className="text-xs text-slate-400">{fund.founder}</div>
                  </div>
                  <span className="text-sm font-bold tabular-nums text-emerald-500">%{fmt(holding.weight)}</span>
                </Link>
              ))}
            </div>
          ) : (
            <p className="text-sm text-slate-400">Bu hisseyi portföyünde tutan bir mock fon bulunamadı.</p>
          )
        )}
      </div>
    </div>
  )
}

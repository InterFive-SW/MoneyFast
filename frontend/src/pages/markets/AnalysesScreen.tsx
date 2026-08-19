import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  findInstrument,
  MOCK_EARNINGS_REPORTS,
  MOCK_DIVIDEND_ANNOUNCEMENTS,
  MOCK_IPO_ANNOUNCEMENTS,
  MOCK_ANALYST_RECOMMENDATIONS,
  MOCK_CAPITAL_INCREASES,
} from '../../data/mockData'

type ReportKey =
  | 'bilancolar' | 'halka-arzlar' | 'geri-alimlar' | 'yeni-is-iliskileri' | 'tedbirli-hisseler'
  | 'beklentiler' | 'araci-kurum-beklentileri' | 'analist-tavsiyeleri' | 'sermaye-artirimlari'
  | 'temettu' | 'acik-satislar' | 'ruchanlar'

const REPORTS: { key: ReportKey; label: string; available: boolean }[] = [
  { key: 'bilancolar', label: 'Son Bilançolar', available: true },
  { key: 'halka-arzlar', label: 'Halka Arzlar', available: true },
  { key: 'geri-alimlar', label: 'Geri Alımlar', available: false },
  { key: 'yeni-is-iliskileri', label: 'Yeni İş İlişkileri', available: false },
  { key: 'tedbirli-hisseler', label: 'Tedbirli Hisseler', available: false },
  { key: 'beklentiler', label: 'Beklentiler', available: false },
  { key: 'araci-kurum-beklentileri', label: 'Aracı Kurum Beklentileri', available: false },
  { key: 'analist-tavsiyeleri', label: 'Analist Tavsiyeleri', available: true },
  { key: 'sermaye-artirimlari', label: 'Sermaye Artırımları', available: true },
  { key: 'temettu', label: 'Temettü', available: true },
  { key: 'acik-satislar', label: 'Açığa Satışlar', available: false },
  { key: 'ruchanlar', label: 'Rüçhanlar', available: false },
]

/** Bir sembolü, mock enstrüman listesinde varsa detay sayfasına bağlar, yoksa düz metin gösterir */
function SymbolLink({ symbol }: { symbol: string }) {
  const found = findInstrument(symbol)
  if (!found) return <span className="text-sm font-semibold text-white">{symbol}</span>
  return (
    <Link to={`/investment/hisseler/${symbol}`} className="text-sm font-semibold text-white hover:text-emerald-500 transition-colors">
      {symbol}
    </Link>
  )
}

function ComingSoon({ label }: { label: string }) {
  return (
    <div className="flex flex-col items-center justify-center py-16 text-center">
      <svg className="h-8 w-8 text-slate-300 mb-3" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <circle cx="12" cy="12" r="10" /><polyline points="12 6 12 12 16 14" />
      </svg>
      <p className="text-sm font-medium text-slate-400">"{label}" raporu yakında eklenecek.</p>
    </div>
  )
}

const thClass = 'py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right'
const tdClass = 'py-2.5 pl-4 text-right tabular-nums text-sm text-slate-200'

/** Analizler ekranı — piyasa geneli rapor sayfaları. 12 tipten 5'i gerçek (V1), 7'si açıkça "Yakında" etiketli. */
export default function AnalysesScreen() {
  const [activeReport, setActiveReport] = useState<ReportKey>('bilancolar')
  const activeMeta = REPORTS.find((r) => r.key === activeReport)!

  return (
    <div>
      <div className="flex flex-wrap gap-1.5 mb-6">
        {REPORTS.map((report) => (
          <button
            key={report.key}
            onClick={() => setActiveReport(report.key)}
            className={`relative px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
              activeReport === report.key
                ? 'bg-slate-800 text-white border-slate-800'
                : 'bg-slate-800 text-slate-300 border-white/10 hover:border-slate-300'
            }`}
          >
            {report.label}
            {!report.available && (
              <span className={`ml-1.5 text-[9px] font-bold ${activeReport === report.key ? 'text-slate-300' : 'text-slate-400'}`}>●</span>
            )}
          </button>
        ))}
      </div>

      <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-4">{activeMeta.label}</h3>

        {!activeMeta.available && <ComingSoon label={activeMeta.label} />}

        {activeReport === 'bilancolar' && (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[640px]">
              <thead>
                <tr className="border-b border-white/10/50">
                  <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Şirket</th>
                  <th className={thClass}>Dönem</th>
                  <th className={thClass}>Gerçekleşen EPS</th>
                  <th className={thClass}>Beklenen EPS</th>
                  <th className={thClass}>Sürpriz</th>
                  <th className={thClass}>Tarih</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {MOCK_EARNINGS_REPORTS.map((r) => (
                  <tr key={r.symbol} className="hover:bg-slate-800/5/50 transition-colors">
                    <td className="py-2.5"><SymbolLink symbol={r.symbol} /></td>
                    <td className={tdClass}>{r.period}</td>
                    <td className={tdClass}>{r.epsActual.toFixed(2)}</td>
                    <td className={tdClass}>{r.epsExpected.toFixed(2)}</td>
                    <td className={`${tdClass} font-semibold ${r.surprise < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>{r.surprise > 0 ? '+' : ''}{r.surprise}%</td>
                    <td className={tdClass}>{r.reportDate}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeReport === 'temettu' && (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[560px]">
              <thead>
                <tr className="border-b border-white/10/50">
                  <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Şirket</th>
                  <th className={thClass}>Hisse Başı</th>
                  <th className={thClass}>Verim</th>
                  <th className={thClass}>Ex-Date</th>
                  <th className={thClass}>Ödeme Tarihi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {MOCK_DIVIDEND_ANNOUNCEMENTS.map((d, i) => (
                  <tr key={i} className="hover:bg-slate-800/5/50 transition-colors">
                    <td className="py-2.5"><SymbolLink symbol={d.symbol} /></td>
                    <td className={tdClass}>{d.amountPerShare.toFixed(2)} ₺</td>
                    <td className={`${tdClass} font-semibold text-emerald-500`}>%{d.yieldPercent}</td>
                    <td className={tdClass}>{d.exDate}</td>
                    <td className={tdClass}>{d.paymentDate}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeReport === 'halka-arzlar' && (
          <div className="flex flex-col gap-2">
            {MOCK_IPO_ANNOUNCEMENTS.map((ipo, i) => (
              <div key={i} className="flex items-center justify-between p-3 bg-slate-800/5/60 rounded-xl">
                <div>
                  <div className="text-sm font-semibold text-white">{ipo.companyName}</div>
                  <div className="text-xs text-slate-400">{ipo.sector} · {ipo.subscriptionStart} – {ipo.subscriptionEnd}</div>
                </div>
                <div className="text-right">
                  <div className="text-sm font-semibold tabular-nums text-slate-200">{ipo.priceRangeLow.toFixed(2)} – {ipo.priceRangeHigh.toFixed(2)} ₺</div>
                  <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                    ipo.status === 'Devam Ediyor' ? 'bg-emerald-500/10 text-emerald-400' : ipo.status === 'Yaklaşan' ? 'bg-amber-50 text-amber-700' : 'bg-slate-800/5 text-slate-400'
                  }`}>{ipo.status}</span>
                </div>
              </div>
            ))}
          </div>
        )}

        {activeReport === 'analist-tavsiyeleri' && (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[640px]">
              <thead>
                <tr className="border-b border-white/10/50">
                  <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Şirket</th>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Aracı Kurum</th>
                  <th className={thClass}>Tavsiye</th>
                  <th className={thClass}>Hedef Fiyat</th>
                  <th className={thClass}>Önceki</th>
                  <th className={thClass}>Tarih</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {MOCK_ANALYST_RECOMMENDATIONS.map((r, i) => (
                  <tr key={i} className="hover:bg-slate-800/5/50 transition-colors">
                    <td className="py-2.5"><SymbolLink symbol={r.symbol} /></td>
                    <td className="py-2.5 pl-4 text-sm text-slate-300">{r.brokerage}</td>
                    <td className={`${thClass.replace('text-slate-400', '')} font-bold ${r.recommendation === 'Al' ? 'text-emerald-500' : r.recommendation === 'Sat' ? 'text-rose-500' : 'text-amber-600'}`}>{r.recommendation}</td>
                    <td className={tdClass}>{r.targetPrice.toFixed(2)} ₺</td>
                    <td className={tdClass}>{r.previousTargetPrice !== null ? `${r.previousTargetPrice.toFixed(2)} ₺` : '—'}</td>
                    <td className={tdClass}>{r.date}</td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}

        {activeReport === 'sermaye-artirimlari' && (
          <div className="overflow-x-auto">
            <table className="w-full text-left border-collapse min-w-[520px]">
              <thead>
                <tr className="border-b border-white/10/50">
                  <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Şirket</th>
                  <th className={thClass}>Tür</th>
                  <th className={thClass}>Oran</th>
                  <th className={thClass}>Kayıt Tarihi</th>
                  <th className={thClass}>Durum</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {MOCK_CAPITAL_INCREASES.map((c, i) => (
                  <tr key={i} className="hover:bg-slate-800/5/50 transition-colors">
                    <td className="py-2.5"><SymbolLink symbol={c.symbol} /></td>
                    <td className={tdClass}>{c.type}</td>
                    <td className={`${tdClass} font-semibold`}>%{c.ratio}</td>
                    <td className={tdClass}>{c.recordDate}</td>
                    <td className={tdClass}>
                      <span className={`text-[10px] font-semibold px-1.5 py-0.5 rounded ${
                        c.status === 'Onaylandı' ? 'bg-emerald-500/10 text-emerald-400' : c.status === 'Beklemede' ? 'bg-amber-50 text-amber-700' : 'bg-slate-800/5 text-slate-400'
                      }`}>{c.status}</span>
                    </td>
                  </tr>
                ))}
              </tbody>
            </table>
          </div>
        )}
      </div>
    </div>
  )
}

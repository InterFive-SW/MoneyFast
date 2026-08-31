import { useState } from 'react'
import { Link } from 'react-router-dom'
import {
  findInstrument,
  // Bilanço, temettü ve analist listeleri artık `/api/market/calendar`'dan.
  // Halka arz ve sermaye artırımı için bir kaynağımız yok; mock kalıyor ve
  // ekranda öyle etiketleniyor.
  MOCK_IPO_ANNOUNCEMENTS,
  MOCK_CAPITAL_INCREASES,
} from '../../data/mockData'
import SampleDataBadge from '../../components/markets/SampleDataBadge'
import { formatMoney } from '../../lib/money'
import {
  RECOMMENDATION_TR, pct, shortDate, useMarketCalendar,
} from '../../hooks/useFundamentals'

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
  // Üç liste tek çağrıda: ekran otuz satır gösteriyor ve enstrüman başına
  // istek atmak, göstereceği şeyden pahalı olurdu.
  const { calendar } = useMarketCalendar()

  // Rozet YALNIZCA hâlâ mock olan iki sekmede. Bilanço takvimi, temettü ve
  // analist konsensüsü artık gerçek veriden geliyor; hepsini "örnek veri"
  // diye etiketlemek, gerçek olanı da şüpheli yapardı.
  const isSampleTab =
    activeReport === 'halka-arzlar' || activeReport === 'sermaye-artirimlari'
  const activeMeta = REPORTS.find((r) => r.key === activeReport)!

  return (
    <div>
      {isSampleTab && (
        <SampleDataBadge reason="Halka arz ve sermaye artırımı duyuruları için bir kaynağımız yok; bu iki liste örnek veridir. Bilanço takvimi, temettü ve analist konsensüsü gerçek veriden gelir." />
      )}
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
                  <th className={thClass}>Bilanço tarihi</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {/* Beklenen/gerçekleşen EPS ve sürpriz KALKTI: sağlayıcı
                    bilanço TARİHİNİ veriyor, tahmin/gerçekleşme çiftini
                    değil. Uydurulmuş bir sürpriz yüzdesi göstermektense
                    elde olanı göstermek. */}
                {(calendar?.earnings ?? []).map((r) => (
                  <tr key={r.symbol} className="hover:bg-slate-800/5/50 transition-colors">
                    <td className="py-2.5"><SymbolLink symbol={r.symbol} /></td>
                    <td className={tdClass}>{shortDate(r.earnings_date)}</td>
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
                  <th className={thClass}>Dağıtım Oranı</th>
                  <th className={thClass}>Ex-Date</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {(calendar?.dividends ?? []).map((d) => (
                  <tr key={d.symbol} className="hover:bg-slate-800/5/50 transition-colors">
                    <td className="py-2.5"><SymbolLink symbol={d.symbol} /></td>
                    <td className={tdClass}>
                      {d.dividend_rate === null ? '—' : formatMoney(d.dividend_rate, d.currency)}
                    </td>
                    <td className={`${tdClass} font-semibold text-emerald-500`}>
                      {d.dividend_yield === null ? '—' : `%${d.dividend_yield.toFixed(2)}`}
                    </td>
                    <td className={tdClass}>{pct(d.payout_ratio)}</td>
                    <td className={tdClass}>{shortDate(d.ex_dividend_date)}</td>
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
                  <th className={thClass}>Konsensüs</th>
                  <th className={thClass}>Analist sayısı</th>
                  <th className={thClass}>Ortalama hedef</th>
                </tr>
              </thead>
              <tbody className="divide-y divide-slate-100/50">
                {/* Bunlar BAŞKASININ görüşü. "39 analistin ortalama hedefi"
                    aktarılabilir bir olgudur; ürünün kendi tavsiyesi değil
                    ve öyle sunulmuyor. */}
                {(calendar?.analysts ?? []).map((r) => (
                  <tr key={r.symbol} className="hover:bg-slate-800/5/50 transition-colors">
                    <td className="py-2.5"><SymbolLink symbol={r.symbol} /></td>
                    <td className={`${tdClass} font-semibold ${
                      r.recommendation.includes('buy') ? 'text-emerald-500'
                        : r.recommendation === 'sell' ? 'text-rose-500' : 'text-amber-500'
                    }`}>
                      {RECOMMENDATION_TR[r.recommendation] ?? r.recommendation}
                    </td>
                    <td className={tdClass}>{r.analyst_count}</td>
                    <td className={tdClass}>
                      {r.target_mean_price === null ? '—' : formatMoney(r.target_mean_price, r.currency)}
                    </td>
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

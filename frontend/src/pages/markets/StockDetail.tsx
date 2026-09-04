import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { MOCK_EARNINGS_REPORTS, MOCK_DIVIDEND_ANNOUNCEMENTS, MOCK_FUNDS } from '../../data/mockData'
import { useInstrument } from '../../hooks/useInstrument'
import SampleDataBadge from '../../components/markets/SampleDataBadge'
import TeknikGorunum from '../../components/markets/TeknikGorunum'
import InstrumentCandleChart from '../../components/markets/InstrumentCandleChart'
import NewsWidget from '../../components/widgets/NewsWidget'
import { compact, pct, ratio, useFundamentals } from '../../hooks/useFundamentals'

type DetailTab = 'ozet' | 'finansallar' | 'oran-analizi' | 'temettu' | 'fon-pozisyonlari'

const TABS: { key: DetailTab; label: string }[] = [
  { key: 'ozet', label: 'Özet' },
  { key: 'finansallar', label: 'Finansallar' },
  { key: 'oran-analizi', label: 'Oran Analizi' },
  { key: 'temettu', label: 'Temettü' },
  { key: 'fon-pozisyonlari', label: 'Fon Pozisyonları' },
]

function fmt(value: number | undefined, opts: Intl.NumberFormatOptions = {}): string {
  if (value === undefined) return '—'
  return value.toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1, ...opts })
}

function fmtCompact(value: number): string {
  return new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

/** Bir oran satırı. `tone` verilirse negatif değer kırmızı yazılır: bir
 *  faaliyet ZARARI, dönemin en bilgilendirici olgusudur ve diğerleriyle aynı
 *  renkte geçiştirilmemeli. */
function Row({ label, value, tone }: { label: string; value: string; tone?: number | null }) {
  const negative = typeof tone === 'number' && tone < 0
  return (
    <tr>
      <td className="py-2.5 text-sm text-slate-400">{label}</td>
      <td className={`py-2.5 text-right text-sm font-semibold tabular-nums ${negative ? 'text-rose-400' : 'text-white'}`}>
        {value}
      </td>
    </tr>
  )
}

/** Hisse detay sayfası — /investment/hisseler/:symbol, 5 sekme (Fintables'ın "onlarca sekme"sinin V1'de daraltılmış hali) */
export default function StockDetail() {
  const { symbol = '' } = useParams()
  const [activeTab, setActiveTab] = useState<DetailTab>('ozet')

  // Live, from /api/market/instruments. Resolving against MOCK_MARKET_INSTRUMENTS
  // meant this page showed a frozen price for the row the user just clicked.
  const { instrument, loading } = useInstrument(symbol.toUpperCase())
  // Sohbetin okuduğu uç noktanın AYNISI: ikisi ayrı kaynaktan besleniyor
  // olsaydı aynı şirket için farklı bir marj söyleyebilirlerdi.
  const { fundamentals } = useFundamentals(symbol.toUpperCase())

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

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

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

  // Türetilen gelir/net kâr hesapları KALKTI: piyasa değerini F/K'ya bölüp
  // "tahmini yıllık gelir" demek, sağlayıcının gerçek hasılatı verdiği
  // yerde bir tahmini olgu diye sunmaktı. Artık `total_revenue` geliyor.

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
          <div className="flex flex-col gap-5">
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

          {/* Fiyatın kendisi, istatistiklerden hemen sonra: sayfanın cevap
              verdiği ilk soru "bu hisse nasıl davrandı" ve buna tek bir
              günlük yüzdeyle cevap verilemiyordu. */}
          <InstrumentCandleChart symbol={symbol.toUpperCase()} />

          {/* Hesaplanmış eğilim. Sohbetin okuduğu uç noktanın AYNISI: ikisi
              ayrı hesaplasaydı aynı hisse için farklı bir eğilim
              söyleyebilirlerdi. */}
          <TeknikGorunum symbol={symbol.toUpperCase()} />

          {/* Bu hisseye bağlı haberler. Süzgeç sunucuda: en yeni yirmiyi
              çekip içinden bu hisseyi ayıklamak, o yirmide o hisse yoksa
              "haber yok" cevabı üretirdi -- oysa soru hiç sorulmamış olur. */}
          <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-4">
            <NewsWidget symbols={[symbol.toUpperCase()]} />
          </div>
          </div>
        )}

        {activeTab === 'finansallar' && (
          fundamentals && fundamentals.total_revenue !== null ? (
            <div className="space-y-4">
              <table className="w-full text-left border-collapse">
                <tbody className="divide-y divide-white/5">
                  <Row label="Hasılat (yıllık)" value={compact(fundamentals.total_revenue, instrument.unit)} />
                  <Row
                    label="Hasılat büyümesi"
                    value={pct(fundamentals.revenue_growth)}
                    tone={fundamentals.revenue_growth}
                  />
                  <Row label="FAVÖK marjı" value={pct(fundamentals.ebitda_margin)} />
                  <Row label="Serbest nakit akışı" value={compact(fundamentals.free_cash_flow, instrument.unit)} />
                  <Row label="Faaliyet nakit akışı" value={compact(fundamentals.operating_cash_flow, instrument.unit)} />
                  <Row label="Toplam borç" value={compact(fundamentals.total_debt, instrument.unit)} />
                  <Row label="Toplam nakit" value={compact(fundamentals.total_cash, instrument.unit)} />
                  <Row label="Firma değeri" value={compact(fundamentals.enterprise_value, instrument.unit)} />
                  <Row
                    label="Kâr büyümesi"
                    value={pct(fundamentals.earnings_growth)}
                    tone={fundamentals.earnings_growth}
                  />
                </tbody>
              </table>
              <p className="text-[11px] text-slate-500">
                {/* "—" burada "sağlayıcı bunu yayımlamıyor" demek, sıfır değil.
                    Bankaların brüt marjı yoktur ve onu %0,0 diye çizmek,
                    şirketin hiç sahip olmadığı bir olguyu bildirmek olurdu. */}
                Boş bırakılan alanlar için sağlayıcıda veri yok; sıfır anlamına gelmez.
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Bu enstrüman için finansal tablo verisi bulunmuyor.</p>
          )
        )}

        {activeTab === 'oran-analizi' && (
          fundamentals ? (
            <div className="space-y-4">
              <table className="w-full text-left border-collapse">
                <tbody className="divide-y divide-white/5">
                  <Row label="F/K" value={ratio(fundamentals.pe_ratio)} />
                  <Row label="İleri F/K" value={ratio(fundamentals.forward_pe)} />
                  <Row label="PD/DD" value={ratio(fundamentals.pb_ratio)} />
                  <Row label="Brüt marj" value={pct(fundamentals.gross_margin)} />
                  <Row
                    label="Faaliyet marjı"
                    value={pct(fundamentals.operating_margin)}
                    tone={fundamentals.operating_margin}
                  />
                  <Row label="Net kâr marjı" value={pct(fundamentals.profit_margin)} tone={fundamentals.profit_margin} />
                  <Row label="Özkaynak kârlılığı" value={pct(fundamentals.return_on_equity)} />
                  <Row label="Aktif kârlılığı" value={pct(fundamentals.return_on_assets)} />
                  <Row label="Borç/Özkaynak" value={ratio(fundamentals.debt_to_equity)} />
                  <Row label="Cari oran" value={ratio(fundamentals.current_ratio)} />
                  <Row label="Hisse başı kâr" value={fundamentals.trailing_eps === null ? '—' : `${fmt(fundamentals.trailing_eps, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} ${instrument.unit}`} tone={fundamentals.trailing_eps} />
                  <Row label="Beta" value={fundamentals.beta === null ? '—' : fmt(fundamentals.beta, { minimumFractionDigits: 2, maximumFractionDigits: 2 })} />
                </tbody>
              </table>
              <p className="text-[11px] text-slate-500">
                Boş bırakılan alanlar için sağlayıcıda veri yok; sıfır anlamına gelmez.
              </p>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Bu enstrüman için oran analizi verisi bulunmuyor.</p>
          )
        )}

        {activeTab === 'temettu' && (
          dividends.length > 0 ? (
            <table className="w-full text-left border-collapse">
            <SampleDataBadge reason="Geçmiş temettü ödemeleri için bir kaynak yok. Portföyünüzdeki temettü verimi Portföyüm ekranında gerçek veriyle sunuluyor." />
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
            <SampleDataBadge reason="Fon portföy bilgisi (TEFAS) için okunabilir bir kaynak yok." />
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

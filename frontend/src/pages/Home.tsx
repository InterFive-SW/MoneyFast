import { useCallback, useEffect, useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import {
  Bar,
  BarChart,
  Cell,
  Line,
  LineChart,
  Pie,
  PieChart,
  ResponsiveContainer,
  Tooltip,
  XAxis,
  YAxis,
} from 'recharts'

import {
  apiClient,
  type ApiCard,
  type PortfolioAccount,
  type PortfolioAnalysis,
  type Position,
  type RiskProfile,
  type RiskSnapshot,
} from '../api/client'
import { useMarketStream } from '../hooks/useMarketStream'
import { useWatchlist } from '../hooks/useWatchlist'
import MarketBand from '../components/markets/MarketBand'
import { BASE_CURRENCY, convert, formatCompact, formatMoney } from '../lib/money'
import { paddedDomain } from '../lib/chartFormat'
import { usePortfolioWeekSeries } from '../hooks/usePortfolioWeekSeries'
import { formatDate, formatTime } from '../lib/datetime'

/** Hesap türü etiketleri; ekranda görünen ad sunumun işi, kaydın değil. */
const ACCOUNT_LABELS: Record<string, string> = {
  vadesiz: 'Vadesiz Hesap',
  vadeli: 'Vadeli Hesap',
  birikim: 'Birikim Hesabı',
  yatirim: 'Yatırım Hesabı',
}

/**
 * Hızlı işlemler. Tasarımdaki dört yuvarlak düğme.
 *
 * Fatura ödeme bir dönem yalnızca Banka İşlemleri'nin içinden ulaşılabiliyordu;
 * en çok yapılan işlerden biri için üç tık fazlaydı.
 */
const ACTIONS = [
  { to: '/banking/transfer', icon: '↗', label: 'Para gönder' },
  { to: '/banking?pay=1', icon: '🧾', label: 'Fatura' },
  { to: '/banking/cards', icon: '💳', label: 'Kartlar' },
  { to: '/banking/transfer', icon: '📈', label: 'Yatırım aktar' },
]

/**
 * Performans grafiğinin dönemleri.
 *
 * `Gün` gün içi seriyi okur: 15 dakikalık GERÇEK barlar (`15m`), sağlayıcıdan
 * OHLC olarak geliyorlar. Anlık fiyattan bar üretmek açılış, yüksek ve düşük
 * değerlerini uydurmak olurdu.
 *
 * `Hafta` ayrı bir uçtan geliyor: `/investment/portfolio/chart?range=hafta`,
 * 15 dakikalık kovalar. Günlük bardan çizildiğinde hafta yalnızca BEŞ nokta
 * oluyordu (işlem günü sayısı kadar) ve çizgi şekilsiz kalıyordu; aynı hafta
 * bu uçtan 266 nokta veriyor.
 *
 * Diğerleri günlük barlardan; pencere iki yıla kadar açık.
 */
const RANGES = [
  { key: 'day', label: 'Gün', days: 1, intraday: true },
  { key: 'week', label: 'Hafta', days: 7, intraday: false },
  { key: 'month', label: 'Ay', days: 30, intraday: false },
  { key: 'year', label: 'Yıl', days: 365, intraday: false },
  { key: 'twoYears', label: '2 Yıl', days: 730, intraday: false },
] as const
type RangeKey = (typeof RANGES)[number]['key']

/** Donut dilim renkleri. Sıra sabit: aynı hesap türü her yüklemede aynı renk. */
const SLICE_COLORS = ['#4B7BE5', '#22C55E', '#F59E0B', '#A855F7', '#EC4899', '#14B8A6']

/**
 * Şeridin sabit kısmı: temel kurlar ve altın.
 *
 * Altının TL karşılığı ayrı bir enstrüman DEĞİL -- sağlayıcı `XAUTRY` için
 * fiyat vermiyor. Kendi para biriminde gösterilip yanına canlı kurla yaklaşık
 * TL karşılığı yazılıyor (`formatWithBase`), yani `4.609,70 $ · ≈₺222.363`.
 */
const BAND_BASE = ['USDTRY', 'EURTRY', 'EURUSD', 'XAUUSD']

/**
 * İzleme listesi boşken şeridi dolduran semboller.
 *
 * Yalnızca ŞERİDİ dolduruyorlar; kullanıcının izleme listesine yazılmıyorlar.
 * Liste boşsa boş görünmeye devam eder -- kullanıcının seçmediği hisseleri
 * onun listesiymiş gibi göstermek, listenin ne olduğunu anlamsızlaştırır.
 */
const BAND_FALLBACK = ['NVDA', 'THYAO', 'ASELS', 'CCOLA']

/**
 * Asistanın gerçekten yapabildiği şeyler.
 *
 * Genel bir "sorularınızı sorun" cümlesi, ne sorabileceğini söylemiyor.
 * Buradakilerin üçü de bugün çalışan yollar: fiyat sorgusu, portföy okuma ve
 * işlem hazırlama.
 */
const ASSISTANT_EXAMPLES = [
  '"THYAO kaç lira?" — anlık fiyat, sorulduğu anda tazelenir',
  '"Portföyüm nasıl gidiyor?" — kendi pozisyonlarınız üzerinden',
  '"5 lot ASELS al" — öneri hazırlar, onayı siz verirsiniz',
]

function shortDate(value: string | null | undefined): string {
  if (!value) return 'veri yok'
  const parsed = new Date(value)
  return Number.isNaN(parsed.getTime())
    ? 'veri yok'
    : formatDate(parsed, { day: '2-digit', month: 'short', year: '2-digit' })
}

/**
 * Ana sayfa — tasarım ekibinin `ana sayfa` eskizine göre.
 *
 * Her panel veritabanından besleniyor; ekranda hesaplanan tek şey düzen.
 * Tek çağrı olan `analytics/portfolio` dört paneli birden dolduruyor
 * (dağılım halkası, performans grafiği, toplam ve nakit), risk paneli
 * `risk/profile`'dan, pozisyonlar `investment/positions`'tan geliyor.
 *
 * Toplamlar para birimleri ÇEVRİLEREK hesaplanır. Kuru bilinmeyen hesap
 * toplama katılmaz ve adıyla söylenir; 1.0 varsaymak uydurma bir toplam
 * üretir — bu projenin bedelini bir kez ödediği hata.
 */
export default function Home() {
  const [accounts, setAccounts] = useState<PortfolioAccount[]>([])
  const [cards, setCards] = useState<ApiCard[]>([])
  const [analysis, setAnalysis] = useState<PortfolioAnalysis | null>(null)
  const [risk, setRisk] = useState<RiskProfile | null>(null)
  const [riskHistory, setRiskHistory] = useState<RiskSnapshot[]>([])
  const [positions, setPositions] = useState<Position[]>([])
  const [displayName, setDisplayName] = useState<string | null>(null)
  const [range, setRange] = useState<RangeKey>('month')
  const [intradayAnalysis, setIntradayAnalysis] = useState<PortfolioAnalysis | null>(null)
  const [loading, setLoading] = useState(true)
  const [refreshing, setRefreshing] = useState(false)
  const [error, setError] = useState<string | null>(null)
  const { quotes, rates } = useMarketStream()
  const { symbols: followed } = useWatchlist()

  /**
   * Şeridin içeriği: temel kurlar, sonra izleme listesi.
   *
   * İzleme listesi paylaşılan bir depodan geliyor, dolayısıyla Piyasalar'da
   * basılan bir yıldız şeridi sayfa yenilenmeden değiştiriyor.
   */
  const bandSymbols = useMemo(() => {
    const watched = [...followed]
    return [...BAND_BASE, ...(watched.length > 0 ? watched : BAND_FALLBACK)]
  }, [followed])

  const load = useCallback(async (isRefresh = false) => {
    if (isRefresh) setRefreshing(true)
    else setLoading(true)
    try {
      // Hesaplar zorunlu ve hızlı; sayfa onlarla açılıyor. Bir panelin boş
      // dönmesi sayfayı düşürmemeli — kullanıcı bakiyesini göremeden hata
      // ekranında kalırdı.
      setAccounts(await apiClient.getAllAccounts())
      setError(null)

      // Gerisi kendi hızında yerleşiyor. Hepsini tek `Promise.all`'da
      // beklemek, en yavaş çağrının bütün sayfayı rehin alması demekti:
      // bakiyeler hazırken ekran hâlâ dönen bir tekerlek gösteriyordu.
      void apiClient.getCards().then(setCards).catch(() => setCards([]))
      void apiClient.getPortfolioAnalysis().then(setAnalysis).catch(() => undefined)
      void apiClient.getRiskProfile().then(setRisk).catch(() => undefined)
      // Skorun yönü: tek bir sayı yükseliyor mu düşüyor mu söylemiyor.
      void apiClient
        .getRiskHistory()
        .then((history) => setRiskHistory(history.points))
        .catch(() => undefined)
      void apiClient.getPositions().then(setPositions).catch(() => undefined)
      void apiClient
        .getCurrentUser()
        .then((me) => setDisplayName(`${me.first_name} ${me.last_name}`.trim()))
        .catch(() => undefined)
    } catch (e) {
      setError(e instanceof Error ? e.message : 'Hesaplar alınamadı.')
    } finally {
      setLoading(false)
      setRefreshing(false)
    }
  }, [])

  useEffect(() => { void load() }, [load])

  // ── Toplam ve dağılım ────────────────────────────────────────────────────
  const converted = accounts.map((account) => ({
    account,
    inBase: convert(account.balance, account.currency_code, BASE_CURRENCY, rates),
  }))
  const total = converted.reduce((sum, row) => sum + (row.inBase ?? 0), 0)
  const unconvertible = converted
    .filter((row) => row.inBase === null)
    .map((row) => row.account.currency_code)

  /**
   * Halka dilimleri hesap TÜRÜNE göre. Eskizdeki birikim/yatırım/vadeli/döviz
   * kırılımı bu; tür alanı zaten kayıtta duruyor, uydurulmuyor.
   */
  const slices = useMemo(() => {
    const bucket: Record<string, number> = {}
    for (const row of converted) {
      if (row.inBase === null) continue
      const label = ACCOUNT_LABELS[row.account.account_type] ?? 'Diğer'
      bucket[label] = (bucket[label] ?? 0) + row.inBase
    }
    return Object.entries(bucket)
      .map(([name, value]) => ({ name, value: Math.round(value * 100) / 100 }))
      .filter((slice) => slice.value > 0)
      .sort((a, b) => b.value - a.value)
  }, [converted])

  // ── Performans serisi ────────────────────────────────────────────────────
  const active = RANGES.find((r) => r.key === range) ?? RANGES[2]

  // Gün içi seri ayrı bir uçtan; yalnızca gerektiğinde ve bir kez çekilir.
  useEffect(() => {
    if (!active.intraday || intradayAnalysis) return
    let cancelled = false
    apiClient
      .getPortfolioAnalysis(undefined, 'day')
      .then((rows) => {
        if (!cancelled) setIntradayAnalysis(rows)
      })
      .catch(() => undefined)
    return () => {
      cancelled = true
    }
  }, [active.intraday, intradayAnalysis])

  // Hafta 15 dakikalık kovalardan; yalnızca o aralık açıkken çekiliyor.
  const weekSeries = usePortfolioWeekSeries(active.key === 'week')

  const trend = useMemo(() => {
    if (active.key === 'week') {
      // Gün ve saat birlikte: bir haftaya yayılan gün içi noktaları yalnızca
      // saatle etiketlemek, yedi ayrı günün 14:00'ünü aynı ada verirdi.
      return weekSeries.points.map((point) => ({
        label: `${formatDate(point.at, { day: '2-digit', month: 'short' })} ${formatTime(point.at)}`,
        value: point.value,
      }))
    }
    const source = active.intraday ? intradayAnalysis : analysis
    const cutoff = Date.now() - active.days * 24 * 60 * 60 * 1000
    return (source?.trend ?? [])
      .map((point) => ({ at: new Date(point.date).getTime(), value: point.value }))
      .filter((point) => Number.isFinite(point.at) && point.at >= cutoff)
      .sort((a, b) => a.at - b.at)
      .map((point) => ({
        // Gün görünümünde saat, diğerlerinde tarih. Gün içi bir seriyi
        // tarihle etiketlemek, bütün noktalara aynı adı vermek olurdu.
        label: active.intraday
          ? formatTime(point.at)
          : formatDate(point.at, { day: '2-digit', month: 'short' }),
        value: point.value,
      }))
  }, [analysis, intradayAnalysis, active, weekSeries.points])

  /**
   * Y ekseni aralığı. Recharts'ın varsayılanı `[0, 'auto']` ve portföy değeri
   * sıfırdan çok uzakta dar bir bantta geziniyor: 1,41-1,43 Mn arası hareket,
   * sıfırdan başlayan bir eksende grafiğin %1,4'ü kadar yer kaplıyordu ve
   * çizgi düz görünüyordu.
   */
  const trendDomain = useMemo(
    () => paddedDomain(trend.map((point) => point.value)),
    [trend],
  )

  /**
   * Eksen etiketi biçimleyicisi, ARALIĞA bağlı.
   *
   * `formatCompact` hassasiyeti tek bir sayının büyüklüğünden alıyordu ve
   * haftalık bant dar: ölçüldü, 1.091.137 - 1.117.318 aralığında beş Y
   * etiketinin beşi de "1,1 Mn" yazıyordu. Beş kez aynı sayıyı yazan bir
   * eksen eksen değildir.
   */
  const trendTick = useMemo(() => {
    const span = trendDomain[1] - trendDomain[0]
    return (value: number) => formatCompact(value, span)
  }, [trendDomain])

  // ── Risk bileşenleri ─────────────────────────────────────────────────────
  // Ölçülemeyen bileşen çubuğa dönüşmez: sıfır ceza ile "ölçülemedi" aynı şey
  // değil ve sıfır çubuk, düşük risk gibi okunur.
  const riskBars = (risk?.components ?? [])
    .filter((component) => component.penalty !== null && component.penalty !== undefined)
    .map((component) => ({
      name: component.name,
      value: Math.round((component.penalty as number) * 100),
    }))

  /** Skoru olan anlık görüntüler, eskiden yeniye. */
  const riskTrend = useMemo(
    () =>
      [...riskHistory]
        .filter((point) => point.score !== null)
        .sort((a, b) => a.captured_on.localeCompare(b.captured_on))
        .map((point) => ({ score: point.score })),
    [riskHistory],
  )

  /**
   * Skorun NEYİN ÜZERİNDEN ölçüldüğü.
   *
   * `window` ve `assumptions` şemaya tam bu yüzden eklendi: router'ın kendi
   * yorumu, bu alanlar düşürüldüğünde sayfanın "neye karşı ve hangi süre
   * boyunca ölçüldüğünü söylemeyen bir Sharpe ve beta" gösterdiğini yazıyor.
   *
   * Alanlar `Record<string, unknown>` olarak geliyor (şema yeniden
   * üretilmedi), o yüzden tipleri okunurken daraltılıyor: yanlış tipte bir
   * değeri metne gömmek "[object Object]" yazdırırdı.
   */
  const riskBasis = useMemo(() => {
    const count = risk?.window?.observation_count
    const benchmark = risk?.assumptions?.benchmark_symbol
    const parts: string[] = []
    if (typeof count === 'number' && count > 0) parts.push(`${count} işlem günü`)
    if (typeof benchmark === 'string' && benchmark) parts.push(`${benchmark} karşısında`)
    return parts.length ? `${parts.join(', ')} ölçüldü.` : null
  }, [risk])

  const banking = accounts.filter((a) => !a.is_investment)
  const investment = accounts.find((a) => a.is_investment)

  if (loading) {
    return <p className="p-6 text-sm text-slate-400">Yükleniyor…</p>
  }

  return (
    <div className="space-y-6 p-6">
      <MarketBand symbols={bandSymbols} quotes={quotes} rates={rates} />

      {/* ── Selamlama + panel denetimleri ───────────────────────────────── */}
      <div className="flex flex-wrap items-center justify-between gap-3">
        <h1 className="text-xl font-semibold text-white">
          Merhaba, {displayName ?? 'hoş geldiniz'}
        </h1>
        <div className="flex items-center gap-2">
          <button
            onClick={() => void load(true)}
            disabled={refreshing}
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-brandBlue/60 disabled:opacity-50"
          >
            {refreshing ? 'Yenileniyor…' : 'Yenile'}
          </button>
          {/* Panel düzenleme Hızlı Finans'ta yaşıyor; ikinci bir ızgara motoru
              kurmak yerine oraya bağlanıyor. */}
          <Link
            to="/hizli-finans"
            className="rounded-lg border border-slate-700 bg-slate-900 px-3 py-1.5 text-xs font-semibold text-slate-200 transition hover:border-brandBlue/60"
          >
            Paneli düzenle
          </Link>
        </div>
      </div>

      {error && (
        <p className="rounded-lg border border-rose-500/30 bg-rose-500/10 px-4 py-2 text-sm text-rose-300">
          {error}
        </p>
      )}

      {/* ── 1. sıra: dağılım · performans · hızlı işlemler ───────────────── */}
      <div className="grid gap-4 lg:grid-cols-3">
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="text-sm font-semibold text-white">Toplam Varlık</h2>
          <p className="mt-1 text-2xl font-bold tabular-nums text-white">
            {formatMoney(total)}
          </p>
          {slices.length === 0 ? (
            <p className="mt-6 text-sm text-slate-400">Gösterilecek bakiye yok.</p>
          ) : (
            <>
              <div className="mt-2 h-40">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie
                      data={slices}
                      dataKey="value"
                      nameKey="name"
                      innerRadius="60%"
                      outerRadius="90%"
                      stroke="none"
                    >
                      {slices.map((slice, index) => (
                        <Cell key={slice.name} fill={SLICE_COLORS[index % SLICE_COLORS.length]} />
                      ))}
                    </Pie>
                    <Tooltip
                      formatter={(value: unknown) => formatMoney(Number(value))}
                      contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
                    />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <ul className="mt-2 space-y-1">
                {slices.map((slice, index) => (
                  <li key={slice.name} className="flex items-center justify-between text-xs">
                    <span className="flex items-center gap-2 text-slate-300">
                      <span
                        aria-hidden
                        className="h-2 w-2 rounded-full"
                        style={{ background: SLICE_COLORS[index % SLICE_COLORS.length] }}
                      />
                      {slice.name}
                    </span>
                    <span className="tabular-nums text-slate-200">{formatMoney(slice.value)}</span>
                  </li>
                ))}
              </ul>
            </>
          )}
          {unconvertible.length > 0 && (
            <p className="mt-3 text-xs text-amber-400">
              {[...new Set(unconvertible)].join(', ')} kuru bilinmediği için toplama dahil
              edilmedi.
            </p>
          )}
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Portföy Performansı</h2>
            <div className="flex rounded-lg border border-slate-700 p-0.5">
              {RANGES.map((option) => (
                <button
                  key={option.key}
                  onClick={() => setRange(option.key)}
                  className={`rounded-md px-2 py-1 text-[11px] font-semibold transition ${
                    range === option.key
                      ? 'bg-slate-700 text-white'
                      : 'text-slate-400 hover:text-slate-200'
                  }`}
                >
                  {option.label}
                </button>
              ))}
            </div>
          </div>
          {trend.length === 0 ? (
            <p className="mt-10 text-sm text-slate-400">
              {active.intraday
                ? 'Bugün için gün içi veri henüz yok.'
                : 'Bu dönem için portföy geçmişi yok.'}
            </p>
          ) : (
            <div className="mt-4 h-56">
              <ResponsiveContainer width="100%" height="100%">
                <LineChart data={trend} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
                  <XAxis dataKey="label" tick={{ fontSize: 10, fill: '#94a3b8' }} tickLine={false} axisLine={false} minTickGap={24} />
                  <YAxis
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                    width={56}
                    domain={trendDomain}
                    /* Tam biçim eksende taşıyor: altı tane ₺1.412.905,33
                       ya üst üste biniyor ya paneli itiyor. */
                    tickFormatter={trendTick}
                  />
                  <Tooltip
                    formatter={(value: unknown) => formatMoney(Number(value))}
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
                  />
                  <Line
                    type="monotone"
                    dataKey="value"
                    stroke="#4B7BE5"
                    strokeWidth={2}
                    dot={false}
                    /* Kapalı bir günün karşılığı sıfır değil, veri yokluğudur;
                       çizgi o günü keserek değil atlayarak geçmeli. */
                    connectNulls
                  />
                </LineChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <h2 className="text-sm font-semibold text-white">Hızlı İşlemler</h2>
          <div className="mt-4 grid grid-cols-2 gap-4">
            {ACTIONS.map((action) => (
              <Link
                key={action.label}
                to={action.to}
                className="group flex flex-col items-center gap-2 text-center"
              >
                <span
                  aria-hidden
                  className="flex h-14 w-14 items-center justify-center rounded-full bg-brandBlue/15 text-xl ring-1 ring-brandBlue/30 transition group-hover:bg-brandBlue/25"
                >
                  {action.icon}
                </span>
                <span className="text-xs font-medium text-slate-300">{action.label}</span>
              </Link>
            ))}
          </div>

          {investment && (
            <div className="mt-6 rounded-xl border border-slate-800 bg-slate-950/60 p-3">
              <p className="text-[11px] uppercase tracking-wide text-slate-500">
                Yatırım nakdi
              </p>
              <p className="mt-1 text-lg font-semibold tabular-nums text-white">
                {formatMoney(investment.balance, investment.currency_code)}
              </p>
            </div>
          )}
        </section>
      </div>

      {/* ── 2. sıra: pozisyonlar · risk · asistan ────────────────────────── */}
      <div className="grid gap-4 lg:grid-cols-3">
        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5 lg:col-span-1">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Son Pozisyonlar</h2>
            <Link to="/portfolio" className="text-xs text-brandBlue hover:underline">
              Tümü
            </Link>
          </div>
          {positions.length === 0 ? (
            <p className="mt-6 text-sm text-slate-400">Açık pozisyonunuz yok.</p>
          ) : (
            <div className="mt-3 overflow-x-auto">
              <table className="w-full text-left text-xs">
                <thead className="text-[10px] uppercase tracking-wide text-slate-500">
                  <tr>
                    <th className="pb-2">Varlık</th>
                    <th className="pb-2">Tür</th>
                    <th className="pb-2">Giriş</th>
                    <th className="pb-2 text-right">Durum</th>
                  </tr>
                </thead>
                <tbody className="divide-y divide-slate-800">
                  {positions.slice(0, 6).map((position) => (
                    <tr key={position.symbol}>
                      <td className="py-2 font-semibold text-white">{position.symbol}</td>
                      <td className="py-2 text-slate-400">{position.productType ?? 'veri yok'}</td>
                      <td className="py-2 tabular-nums text-slate-400">
                        {shortDate(position.openedAt)}
                      </td>
                      <td
                        className={`py-2 text-right tabular-nums font-semibold ${
                          position.totalReturnPercent >= 0 ? 'text-emerald-400' : 'text-rose-400'
                        }`}
                      >
                        %{position.totalReturnPercent.toFixed(2)}
                      </td>
                    </tr>
                  ))}
                </tbody>
              </table>
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-slate-800 bg-slate-900 p-5">
          <div className="flex items-center justify-between">
            <h2 className="text-sm font-semibold text-white">Risk Skoru</h2>
            <Link to="/risk" className="text-xs text-brandBlue hover:underline">
              Detay
            </Link>
          </div>
          {/* Skor yoksa sayı uydurulmaz: ölçülemediğini söylemek, 50 yazıp
              kullanıcının üzerine karar kurmasına izin vermekten dürüst. */}
          <div className="mt-1 flex items-end justify-between gap-3">
            <div>
              <p className="text-2xl font-bold tabular-nums text-white">
                {risk?.score !== null && risk?.score !== undefined
                  ? risk.score.toFixed(0)
                  : 'Ölçülemedi'}
              </p>
              {risk?.level && <p className="text-xs text-slate-400">{risk.level}</p>}
            </div>

            {/* Skorun YÖNÜ. Tek bir sayı, yükseliyor mu düşüyor mu
                söylemiyor; kullanıcının bilmek istediği şey genellikle bu. */}
            {riskTrend.length > 1 && (
              <div className="h-10 w-28 shrink-0">
                <ResponsiveContainer width="100%" height="100%">
                  <LineChart data={riskTrend}>
                    <Line
                      type="monotone"
                      dataKey="score"
                      stroke="#F59E0B"
                      strokeWidth={2}
                      dot={false}
                      connectNulls
                    />
                  </LineChart>
                </ResponsiveContainer>
              </div>
            )}
          </div>

          {/* Neyin üzerinden ölçüldüğü. Şemanın kendi yorumu, bu alanların
              düşürülmesinin "yorumlanacak hiçbir şeyi olmayan bir Sharpe ve
              beta" bıraktığını söylüyor. */}
          {riskBasis && (
            <p className="mt-1 text-[11px] leading-snug text-slate-500">{riskBasis}</p>
          )}

          {riskBars.length === 0 ? (
            <div className="mt-6">
              <p className="text-sm text-slate-400">
                Risk bileşenleri için yeterli veri yok.
              </p>
              {/* Anket doldurulmadan çıkan skor, varsayılanlar üzerine kurulu
                  olurdu. Kullanıcıyı ölçümü mümkün kılan yere gönderiyoruz. */}
              <Link
                to="/risk"
                className="mt-2 inline-block text-xs font-semibold text-brandBlue hover:underline"
              >
                Risk anketini doldur →
              </Link>
            </div>
          ) : (
            <div className="mt-4 h-48">
              <ResponsiveContainer width="100%" height="100%">
                <BarChart data={riskBars} layout="vertical" margin={{ left: 8, right: 8 }}>
                  <XAxis type="number" domain={[0, 100]} hide />
                  <YAxis
                    type="category"
                    dataKey="name"
                    width={110}
                    tick={{ fontSize: 10, fill: '#94a3b8' }}
                    tickLine={false}
                    axisLine={false}
                  />
                  <Tooltip
                    formatter={(value: unknown) => `${Number(value)}`}
                    contentStyle={{ background: '#0f172a', border: '1px solid #1e293b', borderRadius: 8, fontSize: 12 }}
                  />
                  <Bar dataKey="value" fill="#F59E0B" radius={[0, 4, 4, 0]} barSize={12} />
                </BarChart>
              </ResponsiveContainer>
            </div>
          )}
        </section>

        <section className="rounded-2xl border border-slate-800 bg-gradient-to-br from-slate-900 to-slate-950 p-5">
          {/* Yanındaki panellerle aynı ağırlıkta olsun diye: bir işaret, ne
              yapabildiğini söyleyen üç somut satır ve tek bir belirgin eylem.
              Önceki hali bir başlık, bir cümle ve üç düğmeden ibaretti ve
              komşularının yanında düz duruyordu. */}
          <div className="flex items-start gap-3">
            <span
              aria-hidden
              className="flex h-10 w-10 shrink-0 items-center justify-center rounded-xl bg-brandBlue/15 ring-1 ring-brandBlue/30"
            >
              <svg className="h-5 w-5 text-brandBlue" fill="none" viewBox="0 0 24 24" stroke="currentColor">
                <path
                  strokeLinecap="round"
                  strokeLinejoin="round"
                  strokeWidth={2}
                  d="M13 10V3L4 14h7v7l9-11h-7z"
                />
              </svg>
            </span>
            <div className="min-w-0">
              <h2 className="text-sm font-semibold text-white">Finansal Yapay Zeka</h2>
              <p className="mt-0.5 text-xs leading-snug text-slate-400">
                Onay her zaman sizde — hiçbir emir sormadan iletilmez.
              </p>
            </div>
          </div>

          <ul className="mt-4 space-y-2">
            {ASSISTANT_EXAMPLES.map((example) => (
              <li key={example} className="flex items-start gap-2">
                <span
                  aria-hidden
                  className="mt-1.5 h-1 w-1 shrink-0 rounded-full bg-brandBlue"
                />
                <span className="text-xs leading-snug text-slate-300">{example}</span>
              </li>
            ))}
          </ul>

          <div className="mt-4 flex flex-col gap-2">
            <Link
              to="/chat"
              className="flex items-center justify-center gap-2 rounded-lg bg-brandBlue px-4 py-2.5 text-sm font-semibold text-white shadow-lg shadow-brandBlue/20 transition hover:bg-brandBlue/90"
            >
              Bana sor
              <span aria-hidden>→</span>
            </Link>
            <div className="grid grid-cols-2 gap-2">
              <Link
                to="/analytics"
                className="rounded-lg border border-slate-700 px-3 py-2 text-center text-xs font-semibold text-slate-300 transition hover:border-brandBlue/60 hover:text-white"
              >
                Analiz
              </Link>
              <Link
                to="/risk"
                className="rounded-lg border border-slate-700 px-3 py-2 text-center text-xs font-semibold text-slate-300 transition hover:border-brandBlue/60 hover:text-white"
              >
                Risk
              </Link>
            </div>
          </div>
        </section>
      </div>

      {/* ── Hesaplar ─────────────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Hesaplarım</h2>
          <Link to="/banking/accounts" className="text-xs text-brandBlue hover:underline">
            Tümü
          </Link>
        </div>
        <div className="mt-3 grid gap-3 sm:grid-cols-2 lg:grid-cols-3">
          {banking.map((account) => (
            <Link
              key={account.id}
              to="/banking/accounts"
              className="rounded-xl border border-slate-800 bg-slate-900 p-4 transition hover:border-slate-700"
            >
              <p className="text-sm font-medium text-white">
                {ACCOUNT_LABELS[account.account_type] ?? 'Hesap'}
              </p>
              <p className="mt-1 font-mono text-xs text-slate-500">
                {account.iban ?? account.account_number}
              </p>
              <p className="mt-3 text-lg font-semibold tabular-nums text-white">
                {formatMoney(account.balance, account.currency_code)}
              </p>
            </Link>
          ))}
        </div>
      </section>

      {/* ── Kartlar ──────────────────────────────────────────────────────── */}
      <section>
        <div className="flex items-center justify-between">
          <h2 className="text-sm font-semibold text-white">Kartlarım</h2>
          <Link to="/banking/cards" className="text-xs text-brandBlue hover:underline">
            Tüm kartlar
          </Link>
        </div>

        {cards.length === 0 ? (
          <p className="mt-3 rounded-xl border border-slate-800 bg-slate-900 p-5 text-sm text-slate-400">
            Henüz kartınız yok.
          </p>
        ) : (
          /* Yatay kaydırma, `scroll-snap` ile. Karusel kütüphanesi yok:
             touchpad, dokunmatik ekran ve klavye üçü de kendiliğinden
             çalışıyor, ok tuşlarıyla taklit edilmesi gerekmiyor. */
          <div
            className="mt-3 flex snap-x snap-mandatory gap-4 overflow-x-auto pb-2"
            role="list"
            aria-label="Kartlarım"
          >
            {cards.map((card) => (
              <Link
                key={card.id}
                to="/banking/cards"
                role="listitem"
                className="w-72 shrink-0 snap-start rounded-2xl border border-slate-700 bg-gradient-to-br from-slate-800 to-slate-950 p-5 transition hover:border-brandBlue/60"
              >
                <div className="flex items-start justify-between">
                  <p className="text-sm font-semibold text-white">{card.name}</p>
                  <span className="text-[10px] uppercase tracking-wide text-slate-400">
                    {card.brand}
                  </span>
                </div>
                <p className="mt-4 font-mono text-sm text-slate-300">{card.card_number}</p>
                <div className="mt-4 flex items-end justify-between">
                  <div>
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">Borç</p>
                    <p className="text-sm font-semibold tabular-nums text-white">
                      {formatMoney(card.current_debt)}
                    </p>
                  </div>
                  <div className="text-right">
                    <p className="text-[10px] uppercase tracking-wide text-slate-500">
                      Kullanılabilir
                    </p>
                    <p className="text-sm font-semibold tabular-nums text-emerald-400">
                      {formatMoney(card.available_limit)}
                    </p>
                  </div>
                </div>
              </Link>
            ))}
          </div>
        )}
      </section>
    </div>
  )
}

import { useEffect, useState } from 'react'
import { apiClient } from '../../api/client'
import type { TechnicalSignalsOut } from '../../api/client'

/**
 * Teknik Görünüm — hesaplanmış eğilim, hisse detay sayfasında.
 *
 * Cümlenin kendisi backend'den geliyor (`narrative`). Sayıları alıp burada
 * bir metin kurmak, sohbetin söylediğiyle sayfanın söylediğinin ayrışması
 * demekti: ikisi de aynı uç noktayı okuyor ve aynı cümleyi gösteriyor.
 *
 * `null` bir gösterge ÇİZİLMEZ. "200 günlük ortalama: —" satırı, o
 * ortalamanın var olduğunu ama bilinmediğini ima eder; oysa 30 barlık bir
 * enstrümanda o ortalama yoktur.
 */

const TREND_STYLE: Record<string, { label: string; className: string }> = {
  UPTREND:   { label: 'Yükseliş eğilimi', className: 'bg-emerald-500/15 text-emerald-300 border-emerald-500/30' },
  DOWNTREND: { label: 'Düşüş eğilimi',    className: 'bg-rose-500/15 text-rose-300 border-rose-500/30' },
  SIDEWAYS:  { label: 'Yatay seyir',      className: 'bg-slate-500/15 text-slate-300 border-slate-500/30' },
  UNKNOWN:   { label: 'Ölçülemedi',       className: 'bg-slate-500/15 text-slate-400 border-slate-500/30' },
}

function pct(value: number | null): string | null {
  if (value === null) return null
  return `%${value.toLocaleString('tr-TR', { minimumFractionDigits: 1, maximumFractionDigits: 1 })}`
}

function num(value: number | null, digits = 2): string | null {
  if (value === null) return null
  return value.toLocaleString('tr-TR', { minimumFractionDigits: digits, maximumFractionDigits: digits })
}

export default function TeknikGorunum({ symbol }: { symbol: string }) {
  const [data, setData] = useState<TechnicalSignalsOut | null>(null)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    let cancelled = false
    setData(null)
    setFailed(false)
    apiClient
      .getTechnicalSignals(symbol)
      .then((body) => { if (!cancelled) setData(body) })
      .catch(() => { if (!cancelled) setFailed(true) })
    return () => { cancelled = true }
  }, [symbol])

  if (failed) return null
  if (!data) {
    return (
      <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
        <div className="h-4 w-32 animate-pulse rounded bg-white/10" />
      </div>
    )
  }

  const { signals, narrative } = data
  const trend = TREND_STYLE[signals.trend] ?? TREND_STYLE.UNKNOWN

  // Yalnızca ölçülebilmiş olanlar. Boş satır, olmayan bir ölçümü "bilinmiyor"
  // gibi gösterir.
  const rows: { label: string; value: string }[] = []
  const push = (label: string, value: string | null) => {
    if (value !== null) rows.push({ label, value })
  }
  push('20 günlük ortalamaya uzaklık', pct(signals.pct_from_sma_20))
  push('50 günlük ortalamaya uzaklık', pct(signals.pct_from_sma_50))
  push('200 günlük ortalamaya uzaklık', pct(signals.pct_from_sma_200))
  push('Göreli güç (RSI)', num(signals.rsi_14, 1))
  push('52 hafta aralığındaki yeri', pct(signals.week52_position_pct))
  push(
    'Hacim, 20 günlük ortalamaya göre',
    signals.volume_vs_average === null ? null : `${num(signals.volume_vs_average, 2)}×`,
  )
  push(
    'Yıllık oynaklık',
    signals.annualised_volatility === null ? null : pct(signals.annualised_volatility * 100),
  )
  push('En büyük düşüş', pct(signals.max_drawdown_pct))

  if (signals.trend === 'UNKNOWN' && rows.length === 0) {
    return (
      <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Teknik Görünüm
        </h3>
        <p className="mt-3 text-sm text-slate-400">
          Bu enstrüman için teknik bir görünüm çıkaracak kadar fiyat geçmişi yok.
        </p>
      </div>
    )
  }

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-5">
      <div className="mb-3 flex items-center justify-between gap-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Teknik Görünüm
        </h3>
        <span className={`rounded-full border px-2.5 py-0.5 text-[11px] font-semibold ${trend.className}`}>
          {trend.label}
        </span>
      </div>

      {/* Sohbetin gösterdiği cümlenin aynısı. Çekince ondan ayrılamaz:
          cümleyi bölüp yalnızca ilk yarısını göstermek, koşulu düşürüp
          iddiayı bırakmak olur. */}
      {narrative && (
        <p className="mb-4 text-sm leading-relaxed text-slate-300">{narrative}</p>
      )}

      <dl className="grid grid-cols-1 gap-x-6 gap-y-2 sm:grid-cols-2">
        {rows.map((row) => (
          <div key={row.label} className="flex items-baseline justify-between gap-3 border-b border-white/5 pb-1">
            <dt className="text-xs text-slate-400">{row.label}</dt>
            <dd className="text-sm font-semibold tabular-nums text-white">{row.value}</dd>
          </div>
        ))}
      </dl>

      <p className="mt-3 text-[11px] text-slate-500">
        {signals.observations} işlem günü üzerinden hesaplandı.
      </p>
    </div>
  )
}

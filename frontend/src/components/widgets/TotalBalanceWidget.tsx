/**
 * TotalBalanceWidget — Toplam Varlık Bakiyesi Bileşeni
 *
 * Kullanıcının konsolide toplam varlık değerini, seçili dönemdeki
 * mutlak ve yüzdelik değişimi, sparkline geçmiş performans grafiğini
 * görüntüleyen birincil dashboard widget'ıdır.
 */

import type { BalanceData } from '../../data/mockData'

interface TotalBalanceWidgetProps {
  data: BalanceData
}

// ─── Biçimlendirme Yardımcıları ───────────────────────────────────────────────

/**
 * Sayısal değeri Türk Lirası para birimi formatında biçimlendirir.
 * `tr-TR` yerel ayarı kullanılarak binlik ayraç ve ondalık virgül uygulanır.
 */
function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

// ─── Sparkline Alt Bileşeni ───────────────────────────────────────────────────

interface SparklineChartProps {
  /** 0.0–1.0 aralığında normalize edilmiş veri noktaları dizisi */
  points: number[]
  /** Olumlu değişim için emerald, olumsuz için red renk paleti */
  isPositive: boolean
}

/**
 * SVG tabanlı mini çizgi grafiği (sparkline).
 * Normalize edilmiş veri noktalarından polyline ve dolgu alanı üretir;
 * herhangi bir harici grafik kütüphanesine bağımlılık gerektirmez.
 */
function SparklineChart({ points, isPositive }: SparklineChartProps) {
  const W = 200
  const H = 48
  const PAD = 4

  // Her noktanın piksel koordinatını hesapla
  const coords = points.map((v, i) => ({
    x: PAD + (i / (points.length - 1)) * (W - PAD * 2),
    y: H - PAD - v * (H - PAD * 2),
  }))

  // SVG polyline nokta dizesi
  const linePoints = coords.map(({ x, y }) => `${x},${y}`).join(' ')

  // Dolgu alanı için kapalı yol
  const fillPath = [
    `M${coords[0].x},${coords[0].y}`,
    ...coords.slice(1).map(({ x, y }) => `L${x},${y}`),
    `L${coords[coords.length - 1].x},${H}`,
    `L${coords[0].x},${H}`,
    'Z',
  ].join(' ')

  const strokeColor = isPositive ? '#10b981' : '#ef4444'
  const gradientId  = `spark-gradient-${isPositive ? 'pos' : 'neg'}`

  return (
    <svg
      viewBox={`0 0 ${W} ${H}`}
      className="h-12 w-full"
      aria-hidden="true"
      preserveAspectRatio="none"
    >
      <defs>
        <linearGradient id={gradientId} x1="0" y1="0" x2="0" y2="1">
          <stop offset="0%"   stopColor={strokeColor} stopOpacity="0.20" />
          <stop offset="100%" stopColor={strokeColor} stopOpacity="0"    />
        </linearGradient>
      </defs>

      {/* Dolgu alanı */}
      <path d={fillPath} fill={`url(#${gradientId})`} />

      {/* Çizgi */}
      <polyline
        points={linePoints}
        fill="none"
        stroke={strokeColor}
        strokeWidth="1.8"
        strokeLinecap="round"
        strokeLinejoin="round"
      />
    </svg>
  )
}

// ─── Ana Bileşen ──────────────────────────────────────────────────────────────

/**
 * Toplam Bakiye Widget'ı
 *
 * Üç ana bilgi bloğundan oluşur:
 *  1. Dönem etiketi ve durum rozeti (üst satır)
 *  2. Toplam bakiye rakamı ve değişim göstergesi (orta)
 *  3. Geçmiş performans sparkline grafiği (alt)
 */
export default function TotalBalanceWidget({ data }: TotalBalanceWidgetProps) {
  const isPositive = data.changePercent >= 0

  const changeBadgeClass = isPositive
    ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
    : 'bg-red-50 text-red-700 border-red-100'

  return (
    <div className="flex h-full flex-col justify-between">
      {/* ── Üst Satır: Başlık ve Durum Rozeti ────────────────────────── */}
      <div className="flex items-start justify-between mb-2">
        <h2 className="text-[11px] uppercase tracking-wider font-medium text-slate-500">{data.period} Toplam Varlık</h2>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-100 bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold text-emerald-700 tracking-wide">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          CANLI
        </span>
      </div>

      {/* ── Orta: Bakiye ve Değişim ───────────────────────────────────── */}
      <div className="flex-1 flex flex-col justify-center">
        <div className="flex items-baseline gap-3">
          <p className="text-[2.2rem] font-bold leading-none tracking-tight text-slate-900 tabular-nums">
            {formatCurrency(data.total)}
          </p>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-bold tabular-nums ${changeBadgeClass}`}>
            {isPositive ? '▲' : '▼'} {Math.abs(data.changePercent).toFixed(2)}%
          </span>
          <span className="text-[11px] text-slate-400 font-medium tracking-wide tabular-nums">
            {isPositive ? '+' : ''}{formatCurrency(data.changeAmount)}
          </span>
        </div>
      </div>

      {/* ── Alt: Sparkline Grafiği ────────────────────────────────────── */}
      <div className="mt-2 h-10 w-full overflow-hidden">
        <SparklineChart points={data.sparklinePoints} isPositive={isPositive} />
      </div>
    </div>
  )
}

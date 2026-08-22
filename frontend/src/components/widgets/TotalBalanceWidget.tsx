/**
 * TotalBalanceWidget — Toplam Varlık Bakiyesi Bileşeni
 *
 * Kullanıcının konsolide toplam varlık değerini, seçili dönemdeki
 * mutlak ve yüzdelik değişimi, sparkline geçmiş performans grafiğini
 * görüntüleyen birincil dashboard widget'ıdır.
 */

import { useEffect, useState } from 'react'
import { apiClient, type BalanceHistory } from '../../api/client'
import { formatMoney } from '../../lib/money' 

// ─── Biçimlendirme Yardımcıları ───────────────────────────────────────────────


// ─── Sparkline Alt Bileşeni ───────────────────────────────────────────────────

interface SparklineChartProps {
  /** Ham değerler (ör. bakiye geçmişi); ölçekleme burada yapılır */
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

  // Yeni bir hesapta bakiye geçmişi boştur; tek nokta da bir çizgi çizmez.
  // Bunu çizmeye çalışmak `coords[0]` üzerinden patlıyordu ve React bir
  // widget yerine tüm ağacı söküyordu.
  if (points.length < 2) return null

  // Değerler ham bakiye (ör. 132.785,38) olarak gelir; kendi aralığına göre
  // 0–1'e ölçeklenir. Aksi hâlde y koordinatı görünür alanın çok dışına düşer.
  const min = Math.min(...points)
  const max = Math.max(...points)
  const span = max - min
  const scaled = points.map((v) => (span === 0 ? 0.5 : (v - min) / span))

  // Her noktanın piksel koordinatını hesapla
  const coords = scaled.map((v, i) => ({
    x: PAD + (i / (scaled.length - 1)) * (W - PAD * 2),
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
export default function TotalBalanceWidget() {
  // Real balances and their history, from the banking ledger. This widget was
  // fed a ₺145.000 literal with a five-point invented sparkline.
  const [data, setData] = useState<BalanceHistory | null>(null)

  useEffect(() => {
    apiClient
      .getBalanceHistory()
      .then(setData)
      .catch((error) => console.error('Failed to load balance history', error))
  }, [])

  if (!data) {
    return (
      <div className="flex h-full items-center justify-center">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const changePercent = data.change_percent ?? 0
  const isPositive = changePercent >= 0
  // The real running balance after each movement — `balance_after` is stored
  // on every ledger leg precisely so this does not have to be replayed.
  const sparklinePoints = (data.points ?? []).map((point) => point.balance)

  const changeBadgeClass = isPositive
    ? 'bg-emerald-50 text-emerald-700 border-emerald-100'
    : 'bg-red-50 text-red-700 border-red-100'

  return (
    <div className="flex h-full flex-col justify-between">
      {/* ── Üst Satır: Başlık ve Durum Rozeti ────────────────────────── */}
      <div className="flex items-start justify-between mb-2">
        <h2 className="text-[11px] uppercase tracking-wider font-medium text-slate-400">Toplam Varlık</h2>
        <span className="inline-flex items-center gap-1.5 rounded-full border border-emerald-100 bg-emerald-50 px-2.5 py-1 text-[10px] font-semibold text-emerald-700 tracking-wide">
          <span className="h-1.5 w-1.5 rounded-full bg-emerald-500" />
          CANLI
        </span>
      </div>

      {/* ── Orta: Bakiye ve Değişim ───────────────────────────────────── */}
      <div className="flex-1 flex flex-col justify-center">
        <div className="flex items-baseline gap-3">
          <p className="text-[2.2rem] font-bold leading-none tracking-tight text-white tabular-nums">
            {formatMoney(data.total, data.currency_code)}
          </p>
        </div>
        <div className="mt-2 flex items-center gap-2">
          <span className={`inline-flex items-center gap-1 rounded-sm px-1.5 py-0.5 text-[11px] font-bold tabular-nums ${changeBadgeClass}`}>
            {isPositive ? '▲' : '▼'} {Math.abs(changePercent).toFixed(2)}%
          </span>
          <span className="text-[11px] text-slate-400 font-medium tracking-wide tabular-nums">
            {isPositive ? '+' : ''}{formatMoney(data.change_amount, data.currency_code)}
          </span>
        </div>
      </div>

      {/* ── Alt: Sparkline Grafiği ────────────────────────────────────── */}
      <div className="mt-2 h-10 w-full overflow-hidden">
        <SparklineChart points={sparklinePoints} isPositive={isPositive} />
      </div>
    </div>
  )
}

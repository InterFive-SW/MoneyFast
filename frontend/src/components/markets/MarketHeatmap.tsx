import { useEffect, useMemo, useState } from 'react'
import { ResponsiveContainer, Treemap } from 'recharts'

import { apiClient } from '../../api/client'
import type { HeatmapTile } from '../../api/client'

interface MarketHeatmapProps {
  /** Grid yerleşiminden gelen yükseklik birimi; widget olarak kullanıldığında. */
  h?: number
}

/** Tıklanabilir piyasalar. Borsa ya da endeks; ikisi de aynı alandan geçiyor. */
const MARKETS = [
  { label: 'BIST', value: 'BIST' },
  { label: 'S&P 500', value: 'SP500' },
  { label: 'Nasdaq', value: 'NASDAQ' },
] as const

/**
 * Renk eşiği: bu yüzdeden büyük hareketler tam doygunlukta.
 *
 * Efsane çubuğu da bu ölçekten üretiliyor, dolayısıyla çubuktaki renkle
 * kutudaki renk aynı kuralın çıktısı -- efsane süs değil, anahtar.
 */
const FULL_SCALE = 3

/** Efsane basamakları, ekrandaki çubuğun aynısı. */
const LEGEND_STEPS = [-3, -2, -1, 0, 1, 2, 3]

/**
 * Yüzde değişimi renge çevirir: kazanç yeşil, kayıp kırmızı.
 *
 * Doygunluk hareketin BÜYÜKLÜĞÜYLE artıyor -- %0,2'lik bir kıpırdanma ile
 * %8'lik bir sıçrama aynı renkte olsaydı harita hangi hissenin gerçekten
 * hareket ettiğini söylemezdi. Sıfıra çok yakın değerler nötr gri kalıyor:
 * yuvarlanmış bir sıfırı yeşile boyamak, olmayan bir kazancı göstermek olurdu.
 */
export function tileColour(changePercent: number): string {
  if (Math.abs(changePercent) < 0.05) return '#3f4654'
  const intensity = Math.min(1, Math.abs(changePercent) / FULL_SCALE)
  // 0,25 taban: en küçük hareket bile nötrden ayırt edilebilsin.
  const weight = 0.25 + intensity * 0.75
  const [r, g, b] = changePercent > 0 ? [22, 163, 74] : [220, 38, 38]
  const base = 46
  return `rgb(${Math.round(base + (r - base) * weight)}, ${Math.round(
    base + (g - base) * weight,
  )}, ${Math.round(base + (b - base) * weight)})`
}

interface TileProps {
  x?: number
  y?: number
  width?: number
  height?: number
  symbol?: string
  changePercent?: number
}

/** Bir kutu. Sembol ve yüzde ancak sığdığında yazılıyor. */
function Tile({ x = 0, y = 0, width = 0, height = 0, symbol, changePercent }: TileProps) {
  if (width <= 0 || height <= 0) return null
  const change = changePercent ?? 0
  const showSymbol = width > 42 && height > 24
  const showChange = width > 54 && height > 38

  return (
    <g>
      <rect
        x={x}
        y={y}
        width={width}
        height={height}
        fill={tileColour(change)}
        stroke="#0f172a"
        strokeWidth={1}
      />
      {showSymbol && (
        <text
          x={x + width / 2}
          y={y + height / 2 - (showChange ? 6 : 0)}
          textAnchor="middle"
          fill="#ffffff"
          fontSize={Math.min(13, Math.max(9, width / 6))}
          fontWeight={600}
        >
          {symbol}
        </text>
      )}
      {showChange && (
        <text
          x={x + width / 2}
          y={y + height / 2 + 10}
          textAnchor="middle"
          fill="#ffffff"
          fontSize={Math.min(11, Math.max(8, width / 8))}
          opacity={0.9}
        >
          {change > 0 ? '+' : ''}
          {change.toFixed(2)}%
        </text>
      )}
    </g>
  )
}

/**
 * Piyasa ısı haritası.
 *
 * Bunun yerinde portföy ağırlığına göre boyanan bir kutu ızgarası vardı: meşru
 * bir görünüm ama piyasa haritası değil. Burada her hisse PİYASA DEĞERİ kadar
 * yer kaplıyor, dolayısıyla harita piyasanın kendi ağırlığını gösteriyor.
 *
 * Piyasa değeri bilinmeyen enstrüman ÇİZİLMİYOR ve kaç tanesinin dışarıda
 * kaldığı yazılıyor: varsayılan bir boyut vermek, o hisseye sahip olmadığı bir
 * ağırlığı vermek olurdu.
 */
export default function MarketHeatmap({ h = 5 }: MarketHeatmapProps) {
  const [market, setMarket] = useState<string>(MARKETS[0].value)
  const [tiles, setTiles] = useState<HeatmapTile[]>([])
  const [missing, setMissing] = useState(0)
  const [loading, setLoading] = useState(true)
  const [error, setError] = useState<string | null>(null)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    apiClient
      .getMarketHeatmap(market)
      .then((response) => {
        if (cancelled) return
        setTiles(response.items)
        setMissing(response.missing)
        setError(null)
      })
      .catch(() => {
        if (!cancelled) setError('Isı haritası yüklenemedi.')
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [market])

  const data = useMemo(
    () =>
      tiles.map((tile) => ({
        name: tile.symbol,
        symbol: tile.symbol,
        // Recharts alanı `size`'dan hesaplıyor.
        size: tile.marketCap,
        changePercent: tile.changePercent,
      })),
    [tiles],
  )

  const height = Math.max(260, h * 60)

  return (
    <div className="flex h-full flex-col rounded-[2rem] border border-white/10 bg-slate-900/50 p-5 shadow-2xl backdrop-blur-xl">
      <div className="mb-3 flex flex-wrap items-center justify-between gap-3">
        <h3 className="text-[11px] font-semibold uppercase tracking-wider text-slate-400">
          Isı Haritası
          <span className="ml-2 normal-case tracking-normal text-slate-500">
            (piyasa değerine göre)
          </span>
        </h3>

        <div className="flex rounded-lg border border-white/10 bg-slate-900/60 p-0.5">
          {MARKETS.map((choice) => (
            <button
              key={choice.value}
              onClick={() => setMarket(choice.value)}
              className={`rounded-md px-2.5 py-1 text-[11px] font-semibold transition ${
                market === choice.value
                  ? 'bg-white/10 text-white'
                  : 'text-slate-400 hover:text-slate-200'
              }`}
            >
              {choice.label}
            </button>
          ))}
        </div>
      </div>

      {loading ? (
        <div className="flex flex-1 items-center justify-center py-10">
          <div className="h-8 w-8 animate-spin rounded-full border-b-2 border-emerald-500" />
        </div>
      ) : error ? (
        <p className="py-10 text-center text-sm text-rose-400">{error}</p>
      ) : data.length === 0 ? (
        <p className="py-10 text-center text-sm text-slate-400">
          Bu piyasada gösterilecek enstrüman yok.
        </p>
      ) : (
        <div style={{ height }}>
          <ResponsiveContainer width="100%" height="100%">
            <Treemap
              data={data}
              dataKey="size"
              isAnimationActive={false}
              content={<Tile />}
            />
          </ResponsiveContainer>
        </div>
      )}

      {/* Efsane: kutulardaki rengi üreten ölçeğin aynısı. */}
      <div className="mt-3 flex items-center justify-center gap-1">
        {LEGEND_STEPS.map((step) => (
          <span
            key={step}
            className="rounded px-2 py-0.5 text-[10px] font-semibold tabular-nums text-white"
            style={{ background: tileColour(step) }}
          >
            {step > 0 ? '+' : ''}
            {step}%
          </span>
        ))}
      </div>

      {missing > 0 && (
        <p className="mt-2 text-center text-[10px] text-slate-500">
          {missing} enstrüman piyasa değeri bilinmediği için haritada yok.
        </p>
      )}
    </div>
  )
}

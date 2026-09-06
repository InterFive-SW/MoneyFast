import { useEffect, useMemo, useState } from 'react'
import { ResponsiveContainer, Treemap } from 'recharts'

import { apiClient } from '../../api/client'
import { useMarketStream } from '../../hooks/useMarketStream'
import { formatWithBase } from '../../lib/money'
import type { HeatmapTile } from '../../api/client'
import { LEGEND_STEPS, TILE_TEXT_COLOUR, tileColour } from '../../lib/heatmapColour'

interface MarketHeatmapProps {
  /** Grid yerleşiminden gelen yükseklik birimi; widget olarak kullanıldığında. */
  h?: number
}

/** Tıklanabilir piyasalar. Borsa ya da endeks; ikisi de aynı alandan geçiyor. */
const MARKETS = [
  { label: 'BIST', value: 'BIST' },
  { label: 'S&P 500', value: 'SP500' },
  // 'NASDAQ' borsanın kendisi (183 satır), 'NASDAQ100' endeks (96). Etiket
  // endeksi söylediği için değer de endeksi göstermeli; ikisi bir dönem
  // ayrışmıştı ve düğme, adını taşımadığı bir kümeyi çiziyordu.
  { label: 'Nasdaq 100', value: 'NASDAQ100' },
] as const

/**
 * Çizilen kutu sayısı.
 *
 * Uç nokta S&P 500 için 483 satır döndürüyor ve hepsi haritaya sığmıyor:
 * ölçüldüğünde kutuların ezici çoğunluğu `showSymbol` eşiğinin altında
 * kalıyor, yani ADSIZ çiziliyordu. Adsız kutu bilgi değil; harita "S&P 500"
 * düğmesine basan kullanıcıya gri bir mozaik gösteriyordu.
 *
 * Satırlar piyasa değerine göre sıralı geldiği için ilk N tanesi haritanın
 * ağırlığının da ezici çoğunluğu. Kaçının çizildiği altta yazıyor -- kırpmayı
 * sessiz yapmak, haritayı piyasanın tamamıymış gibi sunmak olurdu.
 */
const MAX_TILES = 60

interface TileProps {
  x?: number
  y?: number
  width?: number
  height?: number
  symbol?: string
  changePercent?: number
  tile?: HeatmapTile
  onHover?: (tile: HeatmapTile | null, x: number, y: number) => void
}

/**
 * Bir kutu. Sembol ve yüzde ancak SIĞDIĞINDA yazılıyor.
 *
 * Sığmayan kutu adsız kalıyor; `MAX_TILES` bunu nadir hâle getiriyor ama
 * ortadan kaldırmıyor (dar bir ekranda kuyruktaki kutular yine küçük).
 * Bu yüzden üzerine gelince (ve klavyeyle odaklanınca) ad, fiyat ve değişim
 * bir kartta gösteriliyor: yalnızca fareyle ulaşılabilen bir etiket, etiket
 * sayılmaz.
 */
function Tile({
  x = 0, y = 0, width = 0, height = 0, symbol, changePercent, tile, onHover,
}: TileProps) {
  if (width <= 0 || height <= 0) return null
  const change = changePercent ?? 0
  const showSymbol = width > 42 && height > 24
  const showChange = width > 54 && height > 38

  const reveal = () => tile && onHover?.(tile, x + width / 2, y)
  const clear = () => onHover?.(null, 0, 0)

  return (
    <g
      tabIndex={0}
      role="img"
      aria-label={
        tile
          ? `${tile.symbol}, ${tile.name ?? ''}, %${change.toFixed(2)}`
          : undefined
      }
      onMouseEnter={reveal}
      onMouseMove={reveal}
      onMouseLeave={clear}
      onFocus={reveal}
      onBlur={clear}
      style={{ cursor: 'pointer', outline: 'none' }}
    >
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
          fill={TILE_TEXT_COLOUR}
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
          fill={TILE_TEXT_COLOUR}
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
  const [hovered, setHovered] = useState<{ tile: HeatmapTile; x: number; y: number } | null>(null)
  const { rates } = useMarketStream()

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
      tiles.slice(0, MAX_TILES).map((tile) => ({
        name: tile.symbol,
        symbol: tile.symbol,
        // Recharts alanı `size`'dan hesaplıyor.
        size: tile.marketCap,
        changePercent: tile.changePercent,
        // Satırın kendisi taşınıyor: kartta ad ve fiyat da gösteriliyor.
        tile,
      })),
    [tiles],
  )

  // Kutu başına düşen alan, etiketin yazılıp yazılmayacağını belirliyor:
  // `showSymbol` 42x24 piksel istiyor. 300 piksellik bir pencerede 60 kutu bu
  // eşiği geçemiyordu.
  const height = Math.max(340, h * 84)

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
        <div className="relative" style={{ height }}>
          {hovered && (
            <div
              role="tooltip"
              className="pointer-events-none absolute z-30 -translate-x-1/2 -translate-y-full rounded-lg border border-white/10 bg-slate-950/95 px-3 py-2 shadow-2xl"
              style={{
                left: Math.min(Math.max(hovered.x, 90), 640),
                top: Math.max(hovered.y - 6, 46),
              }}
            >
              <p className="text-xs font-semibold text-white">{hovered.tile.symbol}</p>
              {hovered.tile.name && hovered.tile.name !== hovered.tile.symbol && (
                <p className="max-w-[220px] truncate text-[11px] text-slate-400">
                  {hovered.tile.name}
                </p>
              )}
              <p className="mt-1 text-[11px] tabular-nums text-slate-300">
                {formatWithBase(hovered.tile.price, hovered.tile.currency, rates)}
              </p>
              <p
                className={`text-[11px] font-semibold tabular-nums ${
                  hovered.tile.changePercent >= 0 ? 'text-emerald-400' : 'text-rose-400'
                }`}
              >
                {hovered.tile.changePercent > 0 ? '+' : ''}
                {hovered.tile.changePercent.toFixed(2)}%
              </p>
            </div>
          )}
          <ResponsiveContainer width="100%" height="100%">
            <Treemap
              data={data}
              dataKey="size"
              isAnimationActive={false}
              content={
                <Tile
                  onHover={(tile, x, y) =>
                    setHovered(tile ? { tile, x, y } : null)
                  }
                />
              }
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

      {(missing > 0 || tiles.length > MAX_TILES) && (
        <p className="mt-2 text-center text-[10px] text-slate-500">
          {tiles.length > MAX_TILES
            ? `Piyasa değerine göre ilk ${MAX_TILES} enstrüman gösteriliyor (${tiles.length} içinden).`
            : null}
          {tiles.length > MAX_TILES && missing > 0 ? ' ' : null}
          {missing > 0
            ? `${missing} enstrüman piyasa değeri bilinmediği için haritada yok.`
            : null}
        </p>
      )}
    </div>
  )
}

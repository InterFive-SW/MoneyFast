import type { Position } from '../../api/client'

interface PortfolioHighlightsProps {
  positions: Position[]
  loading: boolean
}

/** Her sütunda kaç satır gösterilir. */
const TOP_N = 3

function formatPercent(percent: number): string {
  return `${percent > 0 ? '+' : ''}${percent.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

/** Kazanç ya da kayıp sütunu. Sıra numarası, listedeki yerini söyler. */
function Column({
  title,
  rows,
  tone,
  empty,
}: {
  title: string
  rows: Position[]
  tone: 'gain' | 'loss'
  empty: string
}) {
  const accent = tone === 'gain' ? 'text-emerald-400' : 'text-rose-400'

  return (
    <div className="flex flex-col gap-1.5">
      <h4 className="text-[10px] uppercase tracking-wider font-semibold text-slate-500">
        {title}
      </h4>
      {rows.length === 0 ? (
        <p className="text-xs text-slate-500">{empty}</p>
      ) : (
        <ol className="flex flex-col gap-1">
          {rows.map((position, index) => (
            <li
              key={position.symbol}
              className="flex items-baseline justify-between gap-2 rounded-lg bg-white/[0.03] px-2.5 py-1.5"
            >
              <span className="flex items-baseline gap-2 min-w-0">
                <span className="text-[10px] tabular-nums text-slate-500">{index + 1}</span>
                <span className="truncate text-xs font-semibold text-white">
                  {position.symbol}
                </span>
              </span>
              <span className={`shrink-0 text-xs font-semibold tabular-nums ${accent}`}>
                {formatPercent(position.totalReturnPercent)}
              </span>
            </li>
          ))}
        </ol>
      )}
    </div>
  )
}

/**
 * Portföyün uçları: en çok kazandıran üç, en çok kaybettiren üç.
 *
 * Önceden tek bir kazanan ve tek bir kaybeden gösteriliyordu ve kutu tam
 * yükseklikteydi -- iki satır için bir ekran dolusu yer.
 *
 * Kaybedenler, listenin sonundan alınarak değil, **sıfırın altında** olarak
 * seçiliyor. Eskiden `sorted[sorted.length - 1]` alınıyordu: tamamı artıda
 * olan bir portföyde bu, en az kazandıran pozisyonu kayıp diye kırmızıya
 * boyuyordu. En düşük kazanç bir kayıp değildir.
 */
export default function PortfolioHighlights({ positions, loading }: PortfolioHighlightsProps) {
  if (loading) {
    return (
      <div className="flex items-center justify-center bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl min-h-[140px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const sorted = [...positions].sort((a, b) => b.totalReturnPercent - a.totalReturnPercent)
  const gainers = sorted.filter((p) => p.totalReturnPercent > 0).slice(0, TOP_N)
  const losers = sorted
    .filter((p) => p.totalReturnPercent < 0)
    .slice(-TOP_N)
    .reverse()

  return (
    <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] p-4 border border-white/10 shadow-2xl">
      <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-3">
        Portföyünüzde Öne Çıkanlar
      </h3>

      {positions.length === 0 ? (
        <p className="text-sm text-slate-400">Portföyünüzde görüntülenecek varlık bulunmuyor.</p>
      ) : (
        <div className="grid grid-cols-2 gap-4">
          <Column
            title="En Çok Kazandıran"
            rows={gainers}
            tone="gain"
            empty="Artıda pozisyon yok."
          />
          <Column
            title="En Çok Kaybettiren"
            rows={losers}
            tone="loss"
            empty="Ekside pozisyon yok."
          />
        </div>
      )}
    </div>
  )
}

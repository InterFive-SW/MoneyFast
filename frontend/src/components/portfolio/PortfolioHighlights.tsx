import type { Position } from '../../api/client'

interface PortfolioHighlightsProps {
  positions: Position[]
  loading: boolean
}

function formatPercent(percent: number): string {
  return `${percent > 0 ? '+' : ''}${percent.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

export default function PortfolioHighlights({ positions, loading }: PortfolioHighlightsProps) {
  if (loading) {
    return (
      <div className="flex flex-col h-full items-center justify-center bg-white/70 backdrop-blur-md rounded-2xl border border-white/50 shadow-sm min-h-[160px]">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const sorted = [...positions].sort((a, b) => b.totalReturnPercent - a.totalReturnPercent)
  const topGainer = sorted[0]
  const topLoser = sorted.length > 1 ? sorted[sorted.length - 1] : undefined

  return (
    <div className="flex flex-col h-full bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Portföyünüzde Öne Çıkanlar</h3>
      </div>

      {!topGainer ? (
        <p className="text-sm text-slate-500">Portföyünüzde görüntülenecek varlık bulunmuyor.</p>
      ) : (
        <div className="flex flex-col gap-3">
          <div className="flex items-center justify-between p-3 bg-emerald-50/60 rounded-xl border border-emerald-100/60">
            <div>
              <div className="text-[10px] uppercase tracking-wider font-semibold text-emerald-600 mb-0.5">En Çok Kazandıran</div>
              <div className="font-semibold text-slate-800 text-sm">{topGainer.symbol}</div>
            </div>
            <div className="text-right tabular-nums text-sm font-bold text-emerald-600">
              {formatPercent(topGainer.totalReturnPercent)}
            </div>
          </div>

          {topLoser && (
            <div className="flex items-center justify-between p-3 bg-rose-50/60 rounded-xl border border-rose-100/60">
              <div>
                <div className="text-[10px] uppercase tracking-wider font-semibold text-rose-500 mb-0.5">En Çok Kaybettiren</div>
                <div className="font-semibold text-slate-800 text-sm">{topLoser.symbol}</div>
              </div>
              <div className="text-right tabular-nums text-sm font-bold text-rose-500">
                {formatPercent(topLoser.totalReturnPercent)}
              </div>
            </div>
          )}
        </div>
      )}
    </div>
  )
}

import { useMemo } from 'react'
import type { MarketInstrument, MarketTicker } from '../../data/mockData'

interface Props {
  instruments: MarketInstrument[]
  tickers: MarketTicker[]
}

function formatPercent(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

/**
 * "Piyasa Nabzı" — mock veriden şablon tabanlı, tek cümlelik otomatik özet.
 * LLM kullanmaz; günün genelini tek bakışta özetlemek için düz mantıkla üretilir.
 */
export default function MarketPulseSummary({ instruments, tickers }: Props) {
  const summary = useMemo(() => {
    const bist100 = tickers.find((t) => t.symbol === 'BIST100')
    const sorted = [...instruments].sort((a, b) => b.changePercent - a.changePercent)
    const topGainer = sorted[0]
    const topLoser = sorted[sorted.length - 1]
    const risingCount = instruments.filter((i) => i.changePercent > 0).length
    const fallingCount = instruments.filter((i) => i.changePercent < 0).length

    return { bist100, topGainer, topLoser, risingCount, fallingCount }
  }, [instruments, tickers])

  if (!summary.topGainer || !summary.topLoser) return null

  const { bist100, topGainer, topLoser, risingCount, fallingCount } = summary
  const bistDirection = bist100 && bist100.changePercent >= 0 ? 'yükseliyor' : 'geriliyor'

  return (
    <div className="mb-6 flex items-start gap-3 rounded-2xl border border-emerald-100/60 bg-emerald-50/40 p-4">
      <svg className="mt-0.5 h-4 w-4 shrink-0 text-emerald-600" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
        <polyline points="16 7 22 7 22 13" />
      </svg>
      <p className="text-sm leading-relaxed text-slate-700">
        {bist100 && (
          <>BIST100 bugün <span className="font-semibold">{formatPercent(bist100.changePercent)}</span> ile {bistDirection}. </>
        )}
        Takip edilen {instruments.length} enstrümandan {risingCount} tanesi yükselirken {fallingCount} tanesi geriliyor.{' '}
        En çok kazandıran <span className="font-semibold text-emerald-600">{topGainer.symbol}</span> ({formatPercent(topGainer.changePercent)}),
        en çok kaybettiren ise <span className="font-semibold text-rose-500">{topLoser.symbol}</span> ({formatPercent(topLoser.changePercent)}) oldu.
      </p>
    </div>
  )
}

import { useMemo } from 'react'

/**
 * Bileşen yalnızca sembol ve günlük değişimi okur. Prop tipini tam enstrüman
 * modeli yerine bu ikisiyle sınırlamak, aynı özeti hem canlı API satırlarıyla
 * hem de başka bir kaynakla besleyebilmeyi sağlıyor.
 */
interface Movement {
  symbol: string
  changePercent: number
}

interface Props {
  instruments: Movement[]
  tickers: Movement[]
}

function formatPercent(value: number): string {
  return `${value > 0 ? '+' : ''}${value.toFixed(2)}%`
}

/**
 * "Piyasa Nabzı" — canlı verilerden şablon tabanlı, tek cümlelik otomatik özet.
 * LLM kullanmaz; günün genelini tek bakışta özetlemek için düz mantıkla üretilir.
 */
export default function MarketPulseSummary({ instruments, tickers }: Props) {
  const summary = useMemo(() => {
    const bist100 = tickers.find((t) => t.symbol === 'XU100')
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
    <div className="mb-6 flex items-start gap-3 rounded-[2rem] border border-emerald-500/20 bg-emerald-500/10 p-4 shadow-2xl">
      <svg className="mt-0.5 h-4 w-4 shrink-0 text-emerald-500" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
        <polyline points="22 7 13.5 15.5 8.5 10.5 2 17" />
        <polyline points="16 7 22 7 22 13" />
      </svg>
      <p className="text-sm leading-relaxed text-slate-200">
        {bist100 && (
          <>BIST100 bugün <span className="font-semibold">{formatPercent(bist100.changePercent)}</span> ile {bistDirection}. </>
        )}
        Takip edilen {instruments.length} enstrümandan {risingCount} tanesi yükselirken {fallingCount} tanesi geriliyor.{' '}
        En çok kazandıran <span className="font-semibold text-emerald-500">{topGainer.symbol}</span> ({formatPercent(topGainer.changePercent)}),
        en çok kaybettiren ise <span className="font-semibold text-rose-500">{topLoser.symbol}</span> ({formatPercent(topLoser.changePercent)}) oldu.
      </p>
    </div>
  )
}

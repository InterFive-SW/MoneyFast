import type { Position } from '../../api/client'

interface PortfolioSummaryBarProps {
  positions: Position[]
  loading: boolean
}

function formatCurrency(amount: number): string {
  return new Intl.NumberFormat('tr-TR', {
    style: 'currency',
    currency: 'TRY',
    minimumFractionDigits: 2,
    maximumFractionDigits: 2,
  }).format(amount)
}

function formatPercent(percent: number): string {
  return `${percent > 0 ? '+' : ''}${percent.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}%`
}

export default function PortfolioSummaryBar({ positions, loading }: PortfolioSummaryBarProps) {
  if (loading) {
    return (
      <div className="flex h-28 items-center justify-center bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  const totalValue = positions.reduce((acc, pos) => acc + pos.totalValue, 0)
  const dailyPL = positions.reduce((acc, pos) => acc + pos.dailyReturn, 0)
  const totalPL = positions.reduce((acc, pos) => acc + pos.totalReturn, 0)
  const dailyBase = totalValue - dailyPL
  const totalBase = totalValue - totalPL
  const dailyPLPercent = dailyBase !== 0 ? (dailyPL / dailyBase) * 100 : 0
  const totalPLPercent = totalBase !== 0 ? (totalPL / totalBase) * 100 : 0

  const stats = [
    {
      label: 'Toplam Portföy Değeri',
      value: formatCurrency(totalValue),
      sub: null as string | null,
      tone: 'neutral' as const,
    },
    {
      label: 'Günlük Kâr / Zarar',
      value: formatCurrency(dailyPL),
      sub: formatPercent(dailyPLPercent),
      tone: dailyPL < 0 ? ('negative' as const) : ('positive' as const),
    },
    {
      label: 'Toplam Kâr / Zarar',
      value: formatCurrency(totalPL),
      sub: formatPercent(totalPLPercent),
      tone: totalPL < 0 ? ('negative' as const) : ('positive' as const),
    },
  ]

  return (
    <div className="grid grid-cols-1 sm:grid-cols-3 gap-4 bg-slate-900/50 backdrop-blur-xl rounded-[2rem] p-5 border border-white/10 shadow-2xl">
      {stats.map((stat) => (
        <div key={stat.label} className="flex flex-col gap-1">
          <span className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">{stat.label}</span>
          <div className="flex items-baseline gap-2">
            <span
              className={`text-2xl font-bold tabular-nums ${
                stat.tone === 'negative' ? 'text-rose-500' : stat.tone === 'positive' ? 'text-emerald-500' : 'text-white'
              }`}
            >
              {stat.value}
            </span>
            {stat.sub && (
              <span
                className={`text-sm font-semibold tabular-nums ${
                  stat.tone === 'negative' ? 'text-rose-500' : 'text-emerald-500'
                }`}
              >
                {stat.sub}
              </span>
            )}
          </div>
        </div>
      ))}
    </div>
  )
}

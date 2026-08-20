import { useMemo, useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { Fund } from '../../data/mockData'
import { buildComparisonChartData } from '../../data/comparisonSeries'

interface Props {
  funds: Fund[]
}

const MAX_SELECTION = 4
const SERIES_DAYS = 90
const PALETTE = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6']

export function formatFundComparisonTooltip(value: number, name: string, codeToName: Map<string, string>): [string, string] {
  return [`${value > 0 ? '+' : ''}${value}%`, codeToName.get(name) ?? name]
}

/** Fon karşılaştırma — en fazla 4 fonun normalize edilmiş % getiri performansı üst üste (Fintables'ın ~10 fonluk kıyaslamasının V1'de daraltılmış hali) */
export default function FundComparisonChart({ funds }: Props) {
  const [selected, setSelected] = useState<string[]>(() => funds.slice(0, 2).map((f) => f.code))

  function toggleFund(code: string) {
    setSelected((prev) => {
      if (prev.includes(code)) return prev.filter((s) => s !== code)
      // Butonlar zaten limitte disabled oluyor — bu ikinci koruma testle ulaşılamaz (defensive kod).
      /* v8 ignore next */
      if (prev.length >= MAX_SELECTION) return prev
      return [...prev, code]
    })
  }

  const chartData = useMemo(() => buildComparisonChartData(selected, SERIES_DAYS), [selected])
  const codeToName = useMemo(() => new Map(funds.map((f) => [f.code, f.name])), [funds])

  return (
    <div className="flex flex-col bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
      <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-4">
        Fon Karşılaştır <span className="normal-case text-slate-400">(son 90 gün, % getiri)</span>
      </h3>

      <div className="flex flex-wrap gap-1.5 mb-4">
        {funds.map((fund) => {
          const isSelected = selected.includes(fund.code)
          const disabled = !isSelected && selected.length >= MAX_SELECTION
          return (
            <button
              key={fund.code}
              onClick={() => toggleFund(fund.code)}
              disabled={disabled}
              className={`px-2.5 py-1 text-xs font-semibold rounded-lg border transition-colors ${
                isSelected
                  ? 'bg-slate-800 text-white border-slate-800'
                  : disabled
                  ? 'bg-slate-800/5 text-slate-300 border-white/10 cursor-not-allowed'
                  : 'bg-slate-800 text-slate-300 border-white/10 hover:border-slate-300'
              }`}
            >
              {fund.code}
            </button>
          )
        })}
      </div>

      {selected.length === 0 ? (
        <div className="flex items-center justify-center h-[260px] text-sm text-slate-400">
          Karşılaştırmak için en fazla {MAX_SELECTION} fon seçin.
        </div>
      ) : (
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(226, 232, 240, 0.6)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} interval={Math.floor(SERIES_DAYS / 6)} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} width={44} />
              <Tooltip
                // codeToName her render'da değiştiği için formatFundComparisonTooltip'i doğrudan referans
                // veremiyoruz; bu ince sarmalayıcı yalnızca gerçek fare hover'ında (jsdom'da simüle
                // edilemeyen SVG hit-detection) çağrılıyor, testle ulaşılamaz.
                /* v8 ignore next */
                formatter={(value: number, name: string) => formatFundComparisonTooltip(value, name, codeToName)}
                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px -8px rgba(0,0,0,0.1)', fontSize: '12px' }}
              />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {selected.map((code, index) => (
                <Line key={code} type="monotone" dataKey={code} stroke={PALETTE[index % PALETTE.length]} strokeWidth={2} dot={false} />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

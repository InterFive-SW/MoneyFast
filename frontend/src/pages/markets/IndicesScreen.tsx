import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import { MOCK_INDICES, findInstrument, type MarketIndex } from '../../data/mockData'
import { buildComparisonChartData } from '../../data/comparisonSeries'

const SERIES_DAYS = 90

function getWeightedConstituents(index: MarketIndex) {
  const rows = index.constituents
    .map((symbol) => ({ symbol, instrument: findInstrument(symbol) }))
    .filter((r): r is { symbol: string; instrument: NonNullable<ReturnType<typeof findInstrument>> } => Boolean(r.instrument))

  const totalMarketCap = rows.reduce((acc, r) => acc + r.instrument.marketCap, 0)

  return rows
    .map((r) => ({ ...r, weight: totalMarketCap > 0 ? (r.instrument.marketCap / totalMarketCap) * 100 : 0 }))
    .sort((a, b) => b.weight - a.weight)
}

function IndexDetail({ index }: { index: MarketIndex }) {
  const weightedConstituents = useMemo(() => getWeightedConstituents(index), [index])
  const benchmark = index.code === 'XU100' ? MOCK_INDICES.find((i) => i.code === 'XU030')! : MOCK_INDICES.find((i) => i.code === 'XU100')!
  const chartData = useMemo(() => buildComparisonChartData([index.code, benchmark.code], SERIES_DAYS), [index.code, benchmark.code])

  return (
    <div className="mt-3 pt-4 border-t border-slate-100 grid grid-cols-1 lg:grid-cols-2 gap-6">
      <div>
        <h4 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mb-3">Endeks Ağırlıkları</h4>
        <div className="flex flex-col gap-1.5">
          {weightedConstituents.map((c) => (
            <Link key={c.symbol} to={`/investment/hisseler/${c.symbol}`} className="flex items-center justify-between p-2 rounded-lg hover:bg-slate-50/60 transition-colors">
              <div>
                <span className="text-sm font-semibold text-slate-800">{c.symbol}</span>
                <span className="text-xs text-slate-400 ml-2">{c.instrument.name}</span>
              </div>
              <span className="text-sm font-bold tabular-nums text-slate-700">%{c.weight.toFixed(1)}</span>
            </Link>
          ))}
        </div>

        <h4 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mt-5 mb-3">Getiri Vadeleri</h4>
        <div className="grid grid-cols-4 gap-2">
          {[
            { label: '6 Ay', value: index.returns.sixMonth },
            { label: '1 Yıl', value: index.returns.oneYear },
            { label: '3 Yıl', value: index.returns.threeYear },
            { label: '5 Yıl', value: index.returns.fiveYear },
          ].map((r) => (
            <div key={r.label} className="rounded-lg bg-slate-50/60 p-2.5 text-center">
              <div className="text-[10px] uppercase font-semibold text-slate-400">{r.label}</div>
              <div className="text-sm font-bold tabular-nums text-emerald-600">+{r.value.toFixed(1)}%</div>
            </div>
          ))}
        </div>
      </div>

      <div>
        <h4 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500 mb-3">
          Benchmark Karşılaştırma <span className="normal-case text-slate-400">({index.name} vs {benchmark.name}, son 90 gün)</span>
        </h4>
        <div className="h-[220px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(226, 232, 240, 0.6)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} interval={Math.floor(SERIES_DAYS / 5)} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} width={40} />
              <Tooltip formatter={(value: number, name: string) => [`${value > 0 ? '+' : ''}${value}%`, name]} contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px -8px rgba(0,0,0,0.1)', fontSize: '12px' }} />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              <Line type="monotone" dataKey={index.code} name={index.name} stroke="#10b981" strokeWidth={2} dot={false} />
              <Line type="monotone" dataKey={benchmark.code} name={benchmark.name} stroke="#94a3b8" strokeWidth={2} dot={false} strokeDasharray="4 4" />
            </LineChart>
          </ResponsiveContainer>
        </div>
      </div>
    </div>
  )
}

/** Endeksler ekranı — BIST'in seçilmiş ~5-6 temsili endeksi (resmî onlarca endeksin tamamı değil, V1) */
export default function IndicesScreen() {
  const [expandedCode, setExpandedCode] = useState<string | null>('XU100')

  return (
    <div className="flex flex-col gap-3">
      {MOCK_INDICES.map((index) => {
        const isExpanded = expandedCode === index.code
        return (
          <div key={index.code} className="bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm">
            <button
              onClick={() => setExpandedCode(isExpanded ? null : index.code)}
              className="w-full flex items-center justify-between text-left"
            >
              <div>
                <div className="flex items-center gap-2">
                  <span className="text-sm font-bold text-slate-900">{index.name}</span>
                  <span className="text-[10px] font-medium text-slate-400 bg-slate-100 px-1.5 py-0.5 rounded">{index.code}</span>
                </div>
                <p className="text-xs text-slate-400 mt-0.5">{index.constituents.length} bileşen</p>
              </div>
              <div className="flex items-center gap-4">
                <div className="text-right">
                  <div className="text-sm font-bold tabular-nums text-slate-800">{index.value.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })}</div>
                  <div className={`text-xs font-semibold tabular-nums ${index.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                    {index.changePercent > 0 ? '+' : ''}{index.changePercent.toFixed(2)}%
                  </div>
                </div>
                <svg className={`h-4 w-4 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
                  <polyline points="6 9 12 15 18 9" />
                </svg>
              </div>
            </button>

            {isExpanded && <IndexDetail index={index} />}
          </div>
        )
      })}
    </div>
  )
}

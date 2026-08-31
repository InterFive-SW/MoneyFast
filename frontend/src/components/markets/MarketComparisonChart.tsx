import { useState } from 'react'
import { CartesianGrid, Legend, Line, LineChart, ResponsiveContainer, Tooltip, XAxis, YAxis } from 'recharts'
import type { MarketInstrument } from '../../data/mockData'
import { useComparisonSeries } from '../../hooks/useComparisonSeries'
import { signedPercent, seriesName } from '../../lib/chartFormat'
import InstrumentPicker from './InstrumentPicker'

interface Props {
  instruments: MarketInstrument[]
}

const MAX_SELECTION = 4
const SERIES_DAYS = 90
const PALETTE = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6']

/**
 * Karşılaştırma modu — en fazla 4 enstrümanın normalize edilmiş (% değişim)
 * fiyat performansını aynı grafikte üst üste gösterir. Tamamen mock/seed'li veri,
 * apiClient'a veya diğer widget'lara bağımlılığı yok.
 */
export default function MarketComparisonChart({ instruments }: Props) {
  const [selected, setSelected] = useState<string[]>(() => instruments.slice(0, 2).map((i) => i.symbol))

  function toggleSymbol(symbol: string) {
    setSelected((prev) => {
      if (prev.includes(symbol)) return prev.filter((s) => s !== symbol)
      if (prev.length >= MAX_SELECTION) return prev
      return [...prev, symbol]
    })
  }

  // Real closes, rebased to percent so instruments at different price
  // levels share one axis. The generator this replaces had a positive
  // bias, so every line trended up whatever the instrument had done.
  const { data: chartData } = useComparisonSeries(selected, SERIES_DAYS)

  return (
    <div className="flex flex-col bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
      <div className="flex flex-col gap-3 sm:flex-row sm:items-center sm:justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">
          Karşılaştır <span className="normal-case text-slate-400">(son 90 gün, % değişim)</span>
        </h3>
      </div>

      {/* Seçim ARAMAYLA. Her enstrüman için bir düğme basmak evren 190
          enstrümanken idare ediyordu; binin üzerine çıkınca ekranın yarısını
          kaplayan bir düğme duvarına dönüştü. */}
      <div className="mb-4 flex flex-col gap-2">
        <InstrumentPicker
          onPick={toggleSymbol}
          disabled={selected.length >= MAX_SELECTION}
          placeholder={
            selected.length >= MAX_SELECTION
              ? `En fazla ${MAX_SELECTION} enstrüman`
              : 'Karşılaştırmaya ekle — sembol ya da şirket adı'
          }
        />
        {selected.length > 0 && (
          <div className="flex flex-wrap gap-1.5">
            {selected.map((symbol, index) => (
              <button
                key={symbol}
                onClick={() => toggleSymbol(symbol)}
                className="flex items-center gap-1.5 rounded-lg border border-white/10 bg-slate-800 px-2.5 py-1 text-xs font-semibold text-white transition hover:border-rose-400/60"
                aria-label={`${symbol} karşılaştırmadan çıkar`}
              >
                <span
                  aria-hidden
                  className="h-2 w-2 rounded-full"
                  style={{ background: PALETTE[index % PALETTE.length] }}
                />
                {symbol}
                <span aria-hidden className="text-slate-500">×</span>
              </button>
            ))}
          </div>
        )}
      </div>

      {selected.length === 0 ? (
        <div className="flex items-center justify-center h-[260px] text-sm text-slate-400">
          Karşılaştırmak için en fazla {MAX_SELECTION} enstrüman seçin.
        </div>
      ) : (
        <div className="h-[260px]">
          <ResponsiveContainer width="100%" height="100%">
            <LineChart data={chartData} margin={{ top: 4, right: 8, left: 0, bottom: 0 }}>
              <CartesianGrid strokeDasharray="3 3" stroke="rgba(226, 232, 240, 0.6)" vertical={false} />
              <XAxis dataKey="date" tick={{ fontSize: 11, fill: '#94a3b8' }} interval={Math.floor(SERIES_DAYS / 6)} axisLine={false} tickLine={false} />
              <YAxis tick={{ fontSize: 11, fill: '#94a3b8' }} tickFormatter={(v) => `${v}%`} axisLine={false} tickLine={false} width={44} />
              <Tooltip
                formatter={(value, name) => [signedPercent(value), seriesName(name)]}
                contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px -8px rgba(0,0,0,0.1)', fontSize: '12px' }}
              />
              <Legend wrapperStyle={{ fontSize: '12px' }} />
              {selected.map((symbol, index) => (
                <Line
                  key={symbol}
                  type="monotone"
                  dataKey={symbol}
                  stroke={PALETTE[index % PALETTE.length]}
                  strokeWidth={2}
                  dot={false}
                  /* Borsalar aynı günlerde kapanmıyor: BIST'in tatil olduğu bir
                     günde Nasdaq serisi doluyken BIST serisinin o tarihte
                     anahtarı hiç yok. connectNulls olmadan Recharts çizgiyi
                     orada kesiyordu — grafiğin "kesintili" görünmesinin sebebi
                     buydu. Veri yok demek sıfır demek değil; çizgi o günü
                     atlayarak devam etmeli. */
                  connectNulls
                />
              ))}
            </LineChart>
          </ResponsiveContainer>
        </div>
      )}
    </div>
  )
}

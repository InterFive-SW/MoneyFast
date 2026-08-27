import { Bar, BarChart, CartesianGrid, Cell, ResponsiveContainer, XAxis, YAxis } from 'recharts'
import { useRiskSimulation } from '../../hooks/useRiskSimulation'
import type { RiskLookback } from '../../api/client'
import { NOT_MEASURED, describeEffectiveN, formatPercent, formatRatio } from '../../lib/riskFormat'
import Term from '../common/Term'

/**
 * "Bu alımı yapsam riskim ne olur?"
 *
 * Yeni bir matematik yok: motor zaten dışarıdan bir pozisyon listesi alıyor,
 * sunucu ikinci bir liste kurup aynı hesabı iki kez yapıyor.
 *
 * Panel hiçbir yerde "daha iyi/daha kötü" demiyor ve hiçbir şey ÖNERMİYOR —
 * değişikliği kullanıcı yazıyor. İki ölçüm yan yana konuyor, yorumu okuyan
 * yapıyor. Bu, özelliği bir hesap makinesi olarak tutan sınır.
 */
interface SimulationPanelProps {
    lookback: RiskLookback
}

const ROWS = [
    { key: 'volatility', label: 'Yıllık oynaklık', term: 'volatility', kind: 'percent' },
    { key: 'effective_n', label: 'Etkin dağılım', term: 'effective_n', kind: 'effective' },
    { key: 'hhi', label: 'Yoğunlaşma ölçüsü', term: 'concentration', kind: 'ratio' },
    { key: 'max_drawdown', label: 'En derin düşüş', term: 'max_drawdown', kind: 'percent' },
] as const

function present(kind: string, value: number | null | undefined): string {
    if (value === null || value === undefined) return NOT_MEASURED
    if (kind === 'percent') return formatPercent(Math.abs(value))
    if (kind === 'effective') return describeEffectiveN(value)
    return formatRatio(value, 3)
}

export default function SimulationPanel({ lookback }: SimulationPanelProps) {
    const sim = useRiskSimulation(lookback)
    const result = sim.result

    const chartData = result
        ? [
              { name: 'Şimdi', score: result.current.score ?? 0 },
              { name: 'Değişiklikten sonra', score: result.hypothetical.score ?? 0 },
          ]
        : []

    return (
        <div className="flex flex-col rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl">
            <h3 className="mb-1 text-base font-semibold text-white">Ne olurdu?</h3>
            <p className="mb-4 text-xs leading-relaxed text-slate-400">
                Bir alım veya satım yapsaydınız ölçülen riskiniz nasıl değişirdi. Hiçbir
                emir iletilmez; yalnızca iki ölçüm yan yana konur.
            </p>

            <div className="flex flex-col gap-2 sm:flex-row">
                <input
                    value={sim.symbol}
                    onChange={(event) => sim.setSymbol(event.target.value)}
                    placeholder="Sembol (ör. THYAO)"
                    aria-label="Sembol"
                    className="flex-1 rounded-lg border border-white/10 bg-slate-950/50 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-brandBlue focus:outline-none"
                />
                <input
                    value={sim.quantity}
                    onChange={(event) => sim.setQuantity(event.target.value)}
                    placeholder="Adet (satış için negatif)"
                    aria-label="Adet"
                    inputMode="numeric"
                    className="w-full rounded-lg border border-white/10 bg-slate-950/50 px-3 py-2 text-sm text-white placeholder:text-slate-600 focus:border-brandBlue focus:outline-none sm:w-56"
                />
                <button
                    type="button"
                    disabled={!sim.ready || sim.running}
                    onClick={() => { void sim.run() }}
                    className="rounded-lg bg-brandBlue px-4 py-2 text-sm font-medium text-white transition-colors hover:bg-blue-600 disabled:cursor-not-allowed disabled:opacity-40"
                >
                    {sim.running ? 'Hesaplanıyor…' : 'Hesapla'}
                </button>
            </div>

            {sim.error && (
                <p className="mt-3 rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-sm text-rose-200">
                    {sim.error}
                </p>
            )}

            {result && (
                <div className="mt-5">
                    {/* Uygulanmayan bir değişikliği sessizce yutmak, kullanıcıya
                        istemediği bir karşılaştırmayı doğruymuş gibi okutur. */}
                    {result.changes
                        .filter((change) => !change.applied)
                        .map((change) => (
                            <p
                                key={change.symbol}
                                className="mb-3 rounded-lg border border-amber-500/30 bg-amber-500/10 px-3 py-2 text-xs text-amber-200"
                            >
                                {change.symbol}: {change.note}
                            </p>
                        ))}

                    <div className="h-40">
                        <ResponsiveContainer width="100%" height="100%">
                            <BarChart data={chartData}>
                                <CartesianGrid strokeDasharray="3 3" stroke="rgba(255,255,255,0.06)" />
                                <XAxis dataKey="name" tick={{ fill: '#94a3b8', fontSize: 11 }} />
                                <YAxis domain={[0, 100]} tick={{ fill: '#94a3b8', fontSize: 11 }} />
                                <Bar dataKey="score" radius={[6, 6, 0, 0]}>
                                    {chartData.map((entry) => (
                                        <Cell
                                            key={entry.name}
                                            fill={entry.name === 'Şimdi' ? '#64748b' : '#0ea5e9'}
                                        />
                                    ))}
                                </Bar>
                            </BarChart>
                        </ResponsiveContainer>
                    </div>
                    <p className="mb-4 text-center text-[11px] text-slate-500">
                        Risk puanı — 100’e yakın puan daha sakin bir portföy demek.
                    </p>

                    <div className="overflow-x-auto">
                        <table className="w-full text-sm">
                            <thead>
                                <tr className="border-b border-white/10 text-xs text-slate-500">
                                    <th className="py-2 text-left font-medium">Ölçüm</th>
                                    <th className="py-2 text-right font-medium">Şimdi</th>
                                    <th className="py-2 text-right font-medium">Sonra</th>
                                </tr>
                            </thead>
                            <tbody>
                                {ROWS.map((row) => (
                                    <tr key={row.key} className="border-b border-white/5">
                                        <td className="py-2 text-slate-300">
                                            <span className="flex items-center gap-1.5">
                                                {row.label}
                                                <Term termKey={row.term} />
                                            </span>
                                        </td>
                                        <td className="py-2 text-right text-slate-400">
                                            {present(row.kind, result.current[row.key])}
                                        </td>
                                        <td className="py-2 text-right font-medium text-white">
                                            {present(row.kind, result.hypothetical[row.key])}
                                        </td>
                                    </tr>
                                ))}
                            </tbody>
                        </table>
                    </div>

                    <div className="mt-4 flex items-center justify-between gap-3">
                        <p className="text-[11px] leading-relaxed text-slate-500">
                            Varsayımsal bir hesaptır; hiçbir emir iletilmemiştir.
                        </p>
                        <button
                            type="button"
                            onClick={sim.reset}
                            className="shrink-0 text-xs font-medium text-slate-400 transition-colors hover:text-slate-200"
                        >
                            Temizle
                        </button>
                    </div>
                </div>
            )}
        </div>
    )
}

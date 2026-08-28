import { formatPercent, toContributions, describeContribution } from '../../lib/riskFormat'
import Term from '../common/Term'

/**
 * Riskin kaynağı: hangi pozisyondan geliyor.
 *
 * "Riskiniz Yüksek" dedikten sonraki ilk soru budur ve bugüne kadar cevabı
 * yoktu. Yoğunlaşma paneli ağırlıkları söylüyor — ama **ağırlık risk
 * değildir**.
 *
 * Her satırda ikisi birden var, çünkü ayrışmaları asıl bilgi. Panel hiçbir
 * yerde ne yapılması gerektiğini söylemiyor: riskin nereden geldiğini
 * söylemek bir ölçüm, azaltmayı önermek bir tavsiyedir.
 */
export default function RiskContributionPanel({ raw }: { raw: unknown }) {
    const rows = toContributions(raw)
    if (rows.length === 0) return null

    return (
        <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl">
            <h3 className="mb-1 flex items-center gap-2 text-base font-semibold text-white">
                Risk nereden geliyor
                <Term termKey="risk_contribution" align="right" />
            </h3>
            <p className="mb-5 text-xs leading-relaxed text-slate-400">
                Portföyün dalgalanmasının ne kadarının hangi pozisyondan geldiği.
                Ağırlıkla aynı şey değil: birlikte hareket eden pozisyonlar,
                ağırlıklarının toplamından daha fazla risk taşır.
            </p>

            <div className="flex flex-col gap-4">
                {rows.map((row) => {
                    const share = Math.max(0, Math.min(1, row.contribution))
                    return (
                        <div key={row.symbol}>
                            <div className="mb-1.5 flex items-baseline justify-between gap-3 text-sm">
                                <span className="font-semibold text-white">{row.symbol}</span>
                                <span className="shrink-0 tabular-nums text-slate-400">
                                    ağırlık {formatPercent(row.weight, 1)} ·{' '}
                                    <span className="font-semibold text-white">
                                        riskin {formatPercent(row.contribution, 1)}’i
                                    </span>
                                </span>
                            </div>
                            {/* İki çubuk üst üste: ince olan ağırlık, kalın olan
                                risk payı. Farkı okumak için sayıyı çözmek
                                gerekmiyor. */}
                            <div className="relative h-2 overflow-hidden rounded-full bg-white/5">
                                <div
                                    className="absolute inset-y-0 left-0 rounded-full bg-white/20"
                                    style={{ width: `${Math.min(100, row.weight * 100)}%` }}
                                />
                                <div
                                    className={`absolute inset-y-0 left-0 rounded-full ${
                                        row.contribution < 0
                                            ? 'bg-sky-500/70'
                                            : row.gap > 0.05
                                              ? 'bg-rose-500/70'
                                              : 'bg-emerald-500/60'
                                    }`}
                                    style={{ width: `${share * 100}%`, opacity: 0.85 }}
                                />
                            </div>
                            <p className="mt-1 text-[11px] leading-relaxed text-slate-500">
                                {describeContribution(row)}
                            </p>
                        </div>
                    )
                })}
            </div>
        </div>
    )
}

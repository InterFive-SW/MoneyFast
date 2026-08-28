import { Link } from 'react-router-dom'
import { useRiskSummary } from '../../hooks/useRiskSummary'
import { alignmentBadge } from '../../lib/riskFormat'
import Term from '../common/Term'

/**
 * Gösterge panelindeki risk kartı.
 *
 * Panelde risk adına yalnızca `QuickActionsWidget`'taki kısayol vardı: risk
 * sayfası hesaplanıyor ama panele hiç yansımıyordu.
 *
 * Puan risk sayfasıyla AYNI uç noktadan geliyor. İki yüzeyin aynı portföy
 * için farklı bir puan göstermesi, kullanıcının hangisine güveneceğini
 * bilememesi demekti.
 */
const LEVEL_TONE: Record<string, string> = {
    Düşük: 'text-emerald-400',
    Orta: 'text-amber-400',
    Yüksek: 'text-rose-400',
}

export default function RiskSummaryWidget() {
    const { score, level, suitability, loading, error, hasPositions } = useRiskSummary()

    const radius = 42
    const circumference = 2 * Math.PI * radius
    const offset = circumference - ((score ?? 0) / 100) * circumference
    const tone = LEVEL_TONE[level ?? ''] ?? 'text-slate-400'
    const badge = alignmentBadge(suitability?.alignment)

    return (
        <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-slate-900/50 p-5 shadow-2xl backdrop-blur-xl">
            <div className="mb-3 flex items-center justify-between gap-2">
                <h3 className="flex items-center gap-2 text-sm font-semibold text-white">
                    Risk Özeti
                    <Term termKey="risk_score" />
                </h3>
                <Link to="/analiz/risk" className="text-xs font-medium text-sky-400 hover:text-sky-300">
                    Detay →
                </Link>
            </div>

            {loading && <p className="my-auto text-center text-sm text-slate-400">Ölçülüyor…</p>}

            {!loading && error && (
                <p className="my-auto rounded-lg border border-rose-500/30 bg-rose-500/10 px-3 py-2 text-center text-sm text-rose-200">
                    {error}
                </p>
            )}

            {/* Ölçülecek pozisyon yoksa puan yerine bir çağrı. Boş bir portföy
                için "0 puan" yazmak, en oynak portföyle aynı sayıyı gösterirdi. */}
            {!loading && !error && !hasPositions && (
                <div className="my-auto text-center">
                    <p className="text-sm leading-relaxed text-slate-400">
                        Ölçülebilecek bir pozisyon yok.
                    </p>
                    <Link
                        to="/investment/piyasalar"
                        className="mt-3 inline-block rounded-lg bg-sky-500/10 px-3 py-1.5 text-xs font-semibold text-sky-400 hover:bg-sky-500/20"
                    >
                        Piyasalara göz at
                    </Link>
                </div>
            )}

            {!loading && !error && hasPositions && (
                <div className="flex flex-1 items-center gap-4">
                    <div className="relative flex shrink-0 items-center justify-center">
                        <svg className="h-24 w-24 -rotate-90 transform" viewBox="0 0 100 100">
                            <circle cx="50" cy="50" r={radius} className="text-slate-800"
                                    strokeWidth="8" stroke="currentColor" fill="transparent" />
                            <circle cx="50" cy="50" r={radius} className={tone}
                                    strokeWidth="8" strokeDasharray={circumference}
                                    strokeDashoffset={offset} strokeLinecap="round"
                                    stroke="currentColor" fill="transparent" />
                        </svg>
                        <div className="absolute flex flex-col items-center">
                            <span className="text-xl font-bold text-white">{score ?? '—'}</span>
                            <span className="text-[10px] text-slate-500">/ 100</span>
                        </div>
                    </div>

                    <div className="min-w-0 flex-1">
                        <p className={`text-lg font-semibold ${tone}`}>{level ?? 'ölçülemedi'}</p>
                        {/* Ölçek TERS. Kartta puanı gören biri "83 = riskli"
                            diye okur; yön puanın hemen yanında olmak zorunda. */}
                        <p className="mt-0.5 text-[11px] leading-snug text-slate-500">
                            100’e yakın puan daha sakin bir portföy demek.
                        </p>
                        <span
                            className={`mt-2 inline-block rounded-full px-2.5 py-1 text-[11px] font-semibold ${badge.tone}`}
                        >
                            {badge.label}
                        </span>
                    </div>
                </div>
            )}
        </div>
    )
}

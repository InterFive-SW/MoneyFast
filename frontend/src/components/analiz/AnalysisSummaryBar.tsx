import type { PortfolioAnalysis, RiskLookback, RiskProfile } from '../../api/client'
import { formatMoney } from '../../lib/money'
import { alignmentBadge, measurementCaption } from '../../lib/riskFormat'
import Term from '../common/Term'

/**
 * Her sekmede duran özet şerit.
 *
 * İki ekran ayrıyken toplam değer, kâr/zarar ve risk puanı ikisinde de vardı;
 * tek çatı altında bir kez gösteriliyor. Dönem seçici de burada, çünkü tek
 * seçici iki ucu birden sürüyor — sekmeye özel bir seçici, kullanıcının bir
 * sekmede 3 ay seçip diğerine geçtiğinde bir yıl görmesi demekti.
 */
const LOOKBACKS: { value: RiskLookback; label: string }[] = [
    { value: '1M', label: '1 Ay' },
    { value: '3M', label: '3 Ay' },
    { value: '6M', label: '6 Ay' },
    { value: '1Y', label: '1 Yıl' },
]

const LEVEL_TONE: Record<string, string> = {
    Düşük: 'text-emerald-400',
    Orta: 'text-amber-400',
    Yüksek: 'text-rose-400',
}

interface Props {
    analysis: PortfolioAnalysis | null
    risk: RiskProfile | null
    lookback: RiskLookback
    onLookbackChange: (value: RiskLookback) => void
}

function Cell({ label, children }: { label: React.ReactNode; children: React.ReactNode }) {
    return (
        <div>
            <div className="flex items-center gap-1.5 text-[11px] uppercase tracking-wider text-slate-400">
                {label}
            </div>
            <div className="mt-1 text-lg font-bold tabular-nums text-white">{children}</div>
        </div>
    )
}

export default function AnalysisSummaryBar({
    analysis,
    risk,
    lookback,
    onLookbackChange,
}: Props) {
    const currency = analysis?.base_currency ?? 'TRY'
    const pnl = analysis?.unrealised_pnl ?? null
    const pnlPercent = analysis?.unrealised_pnl_percent ?? null
    const level = risk?.level ?? null
    const badge = alignmentBadge(risk?.suitability?.alignment)
    const caption = measurementCaption(risk?.window, risk?.assumptions)

    return (
        <div className="mb-6 rounded-2xl border border-white/10 bg-slate-900/50 p-5 backdrop-blur-xl">
            <div className="flex flex-col gap-5 lg:flex-row lg:items-start lg:justify-between">
                <div className="grid flex-1 grid-cols-2 gap-5 sm:grid-cols-4">
                    <Cell label="Toplam Değer">
                        {analysis ? formatMoney(analysis.total_value ?? 0, currency) : '—'}
                    </Cell>
                    <Cell label="Gerçekleşmemiş K/Z">
                        <span
                            className={
                                pnl === null
                                    ? 'text-slate-400'
                                    : pnl < 0
                                      ? 'text-rose-400'
                                      : 'text-emerald-400'
                            }
                        >
                            {pnl === null ? '—' : formatMoney(pnl, currency)}
                            {pnlPercent != null && (
                                <span className="ml-1 text-xs font-medium">
                                    ({pnlPercent > 0 ? '+' : ''}
                                    {pnlPercent.toLocaleString('tr-TR', {
                                        minimumFractionDigits: 2,
                                        maximumFractionDigits: 2,
                                    })}
                                    %)
                                </span>
                            )}
                        </span>
                    </Cell>
                    <Cell
                        label={
                            <>
                                Risk Puanı
                                <Term termKey="risk_score" />
                            </>
                        }
                    >
                        {/* Ölçek TERS ve bu şerit puanın görüldüğü ilk yer, o
                            yüzden yön sayının hemen yanında duruyor. */}
                        {risk?.score ?? '—'}
                        <span className="ml-1 text-xs font-medium text-slate-500">/ 100</span>
                        <span className="ml-2 text-[10px] font-normal text-slate-500">
                            100’e yakın daha sakin
                        </span>
                    </Cell>
                    <Cell label="Seviye">
                        <span className={LEVEL_TONE[level ?? ''] ?? 'text-slate-400'}>
                            {level ?? 'ölçülemedi'}
                        </span>
                        <span
                            className={`ml-2 inline-block rounded-full px-2 py-0.5 text-[10px] font-semibold ${badge.tone}`}
                        >
                            {badge.label}
                        </span>
                    </Cell>
                </div>

                <div className="flex shrink-0 gap-1 rounded-lg bg-white/5 p-1">
                    {LOOKBACKS.map((option) => (
                        <button
                            key={option.value}
                            type="button"
                            onClick={() => onLookbackChange(option.value)}
                            aria-pressed={lookback === option.value}
                            className={`rounded-md px-2.5 py-1 text-xs font-medium transition-colors ${
                                lookback === option.value
                                    ? 'bg-brandBlue text-white'
                                    : 'text-slate-400 hover:text-slate-200'
                            }`}
                        >
                            {option.label}
                        </button>
                    ))}
                </div>
            </div>

            {/* Neyi, ne kadar süreyle, neye göre ölçtüğümüz. Sharpe ve beta
                bunlar olmadan yorumlanamaz ve sayfa ikisini de gösteriyordu. */}
            {caption && (
                <p className="mt-4 border-t border-white/5 pt-3 text-[11px] text-slate-500">
                    {caption}
                </p>
            )}
        </div>
    )
}

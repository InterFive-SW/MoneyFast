import { useState } from 'react'
import type { RiskSuggestion } from '../../api/client'
import EmptyPortfolioCard from '../../components/risk/EmptyPortfolioCard'
import FinancialBalanceWidget from '../../components/risk/FinancialBalanceWidget'
import QuestionnaireModal from '../../components/risk/QuestionnaireModal'
import RiskConcentrationPanel from '../../components/risk/RiskConcentrationPanel'
import RiskFactorsWidget from '../../components/risk/RiskFactorsWidget'
import RiskMetricsPanel from '../../components/risk/RiskMetricsPanel'
import RiskNarrativeCard from '../../components/risk/RiskNarrativeCard'
import RiskRecommendationsWidget from '../../components/risk/RiskRecommendationsWidget'
import RiskScoreWidget from '../../components/risk/RiskScoreWidget'
import ScoreBreakdown from '../../components/risk/ScoreBreakdown'
import SuitabilityCard from '../../components/risk/SuitabilityCard'
import { useAnalysis } from '../Analiz'

/**
 * Analiz > Risk — ne kadar risk taşıyorum ve neden.
 *
 * Eski `pages/Risk.tsx`. Başlık, dönem seçici ve "son hesaplama" satırı
 * buradan çıktı: üçü de artık her sekmede duran özet şeritte. Simülasyon ve
 * puan geçmişi Senaryo sekmesine taşındı — ikisi de "ne olurdu" ve "nereden
 * geldim" sorularının cevabı, bu sekmeninki ise "şu an ne".
 */
function suggestionTarget(
    suggestion: RiskSuggestion,
    largestSymbol: string | null,
): string | null {
    if (suggestion.id === 'review-largest' && largestSymbol) {
        return `/investment/hisseler/${largestSymbol}`
    }
    if (suggestion.id === 'sector-weight') return '/analiz/genel'
    return null
}

export default function RiskSekmesi() {
    const { risk, lookback, reload } = useAnalysis()
    const [surveyOpen, setSurveyOpen] = useState(false)

    if (!risk) {
        return (
            <p className="rounded-2xl border border-white/10 bg-white/5 p-4 text-sm text-slate-400">
                Risk verilerine ulaşılamadı. Lütfen daha sonra tekrar deneyin.
            </p>
        )
    }

    const cashflow = risk.cashflow
    const noPositions = (risk.position_count ?? 0) === 0
    const metrics = (risk.metrics ?? {}) as Record<string, unknown>
    const concentration = metrics.concentration as Record<string, unknown> | undefined
    const largestSymbol =
        ((concentration?.largest_position as { symbol?: string } | undefined)?.symbol) ?? null

    return (
        <>
            {/* Ölçülemeyen bir şey varsa sessizce geçilmez: puanın neyi
                kapsamadığı puanın kendisi kadar önemli. */}
            {(risk.warnings?.length ?? 0) > 0 && (
                <div className="mb-6 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
                    <p className="text-xs font-semibold text-amber-400">Hesaba katılmayanlar</p>
                    <ul className="mt-1 list-disc pl-5 text-xs text-slate-400">
                        {risk.warnings?.map((warning) => <li key={warning}>{warning}</li>)}
                    </ul>
                </div>
            )}

            {/* Rakam yığınından önce üç cümle. Aynı metriklerden üretiliyor. */}
            {!noPositions && <RiskNarrativeCard metrics={metrics} lookback={lookback} />}

            {/* Yumuşak kapı: anket yoksa kart bir çağrıya dönüşür, sayfa kapanmaz. */}
            <div className="mb-6">
                <SuitabilityCard
                    suitability={risk.suitability}
                    declared={risk.declared}
                    onStart={() => setSurveyOpen(true)}
                />
            </div>

            <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
                <div className="flex flex-col gap-6 lg:col-span-1">
                    <RiskScoreWidget score={risk.score ?? null} level={risk.level ?? null} />
                    <ScoreBreakdown components={risk.components ?? []} />
                </div>

                <div className="flex flex-col gap-6 lg:col-span-2">
                    {cashflow && (
                        <FinancialBalanceWidget
                            period={cashflow.period}
                            income={cashflow.monthly_income ?? 0}
                            expense={cashflow.monthly_expense ?? 0}
                            savingsRate={cashflow.savings_rate ?? null}
                            currency={cashflow.currency_code ?? 'TRY'}
                        />
                    )}
                    {noPositions ? (
                        <EmptyPortfolioCard />
                    ) : (
                        <>
                            <RiskMetricsPanel
                                metrics={metrics}
                                currency={cashflow?.currency_code ?? 'TRY'}
                            />
                            <RiskConcentrationPanel concentration={concentration} />
                            <RiskFactorsWidget factors={risk.findings ?? []} />
                            <RiskRecommendationsWidget
                                recommendations={risk.suggestions ?? []}
                                resolveTarget={(rec) => suggestionTarget(rec, largestSymbol)}
                            />
                        </>
                    )}
                </div>
            </div>

            <QuestionnaireModal
                open={surveyOpen}
                onClose={() => setSurveyOpen(false)}
                // Karşılaştırma sunucuda üretiliyor, istemcide tahmin
                // edilmiyor: anket kaydedilince profil yeniden çekilir.
                onSaved={() => void reload()}
            />
        </>
    )
}

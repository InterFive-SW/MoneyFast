import { useState, useEffect } from 'react'
import { apiClient } from '../api/client'
import type { RiskLookback, RiskProfile, RiskSuggestion } from '../api/client'

import RiskScoreWidget from '../components/risk/RiskScoreWidget'
import FinancialBalanceWidget from '../components/risk/FinancialBalanceWidget'
import RiskFactorsWidget from '../components/risk/RiskFactorsWidget'
import RiskRecommendationsWidget from '../components/risk/RiskRecommendationsWidget'
import ScoreBreakdown from '../components/risk/ScoreBreakdown'
import RiskMetricsPanel from '../components/risk/RiskMetricsPanel'
import RiskConcentrationPanel from '../components/risk/RiskConcentrationPanel'
import RiskNarrativeCard from '../components/risk/RiskNarrativeCard'
import EmptyPortfolioCard from '../components/risk/EmptyPortfolioCard'
import SuitabilityCard from '../components/risk/SuitabilityCard'
import QuestionnaireModal from '../components/risk/QuestionnaireModal'
import SimulationPanel from '../components/risk/SimulationPanel'
import RiskHistoryPanel from '../components/risk/RiskHistoryPanel'

/**
 * Risk Analizi sayfası.
 *
 * Her sayı `GET /api/risk/profile`'dan gelir ve oradan da
 * `risk/service.calculate`'in gerçek kapanış serilerinden hesapladığı
 * metriklere kadar izlenebilir. Sayfa daha önce `MOCK_RISK_DATA`'yı okuyup
 * 1200 ms'lik sahte bir gecikme uyguluyordu: 68 puan, dört uydurma bulgu ve
 * hiç ölçülmemiş bir borç/gelir oranı.
 */
/** Sayfadan seçilebilen pencereler. Uzun aralıklar için yeterli mum yoksa
 *  yanıtın `data_quality` bloğu bunu zaten söylüyor. */
const LOOKBACKS: { value: RiskLookback; label: string }[] = [
  { value: '1M', label: '1 Ay' },
  { value: '3M', label: '3 Ay' },
  { value: '6M', label: '6 Ay' },
  { value: '1Y', label: '1 Yıl' },
]

/**
 * Bir önerinin gideceği ekran, ya da hedefi yoksa `null`.
 *
 * Hedefi olmayan öneride düğme hiç çizilmez; tıklanıp hiçbir şey yapmayan
 * bir düğme, kullanıcıya özelliğin bozuk olduğunu söyler.
 */
function suggestionTarget(
  suggestion: RiskSuggestion,
  largestSymbol: string | null,
): string | null {
  if (suggestion.id === 'review-largest' && largestSymbol) {
    return `/investment/hisseler/${largestSymbol}`
  }
  if (suggestion.id === 'sector-weight') return '/analytics'
  return null
}

export default function Risk() {
  const [data, setData] = useState<RiskProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)
  const [lookback, setLookback] = useState<RiskLookback>('1Y')
  const [surveyOpen, setSurveyOpen] = useState(false)
  // Anket kaydedilince profili yeniden çekmek için: karşılaştırma
  // sunucuda üretiliyor, istemcide tahmin edilmiyor.
  const [reloadKey, setReloadKey] = useState(0)

  useEffect(() => {
    let cancelled = false
    setLoading(true)
    apiClient
      .getRiskProfile(lookback)
      .then((profile) => {
        if (!cancelled) setData(profile)
      })
      .catch((error) => {
        if (cancelled) return
        console.error('Risk profili alınamadı', error)
        setFailed(true)
      })
      .finally(() => {
        if (!cancelled) setLoading(false)
      })
    return () => {
      cancelled = true
    }
  }, [lookback, reloadKey])

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center p-6">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/10 border-t-brandBlue" />
          <p className="text-sm font-medium text-slate-400">Risk profiliniz hesaplanıyor...</p>
        </div>
      </div>
    )
  }

  if (failed || !data) {
    return (
      <div className="min-h-screen p-6 sm:p-8">
        <h1 className="text-2xl font-bold tracking-tight text-white">Risk Analizi</h1>
        <p className="mt-4 text-slate-400">
          Risk verilerine ulaşılamadı. Lütfen daha sonra tekrar deneyin.
        </p>
      </div>
    )
  }

  const cashflow = data.cashflow
  const noPositions = (data.position_count ?? 0) === 0
  const metrics = (data.metrics ?? {}) as Record<string, unknown>
  const concentration = metrics.concentration as Record<string, unknown> | undefined
  const largestSymbol =
    ((concentration?.largest_position as { symbol?: string } | undefined)?.symbol) ?? null

  return (
    <div className="min-h-screen p-6 sm:p-8">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Risk Analizi</h1>
          <p className="mt-1 text-sm text-slate-400">
            Portföyünüzün ölçülen oynaklığı, yoğunlaşması ve geçmiş düşüşleri.
          </p>
        </div>
        <div className="flex flex-col items-start gap-2 sm:items-end">
          <div className="flex gap-1 rounded-lg bg-white/5 p-1">
            {LOOKBACKS.map((option) => (
              <button
                key={option.value}
                type="button"
                onClick={() => setLookback(option.value)}
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
          <div className="text-sm font-medium text-slate-400">
            Son hesaplama:{' '}
            {new Date(data.as_of).toLocaleDateString('tr-TR', {
              hour: '2-digit',
              minute: '2-digit',
            })}
          </div>
        </div>
      </div>

      {/* Ölçülemeyen bir şey varsa sessizce geçilmez: puanın neyi kapsamadığı
          puanın kendisi kadar önemli. */}
      {(data.warnings?.length ?? 0) > 0 && (
        <div className="mb-6 rounded-xl border border-amber-500/20 bg-amber-500/5 p-4">
          <p className="text-xs font-semibold text-amber-400">Hesaba katılmayanlar</p>
          <ul className="mt-1 list-disc pl-5 text-xs text-slate-400">
            {data.warnings?.map((warning) => <li key={warning}>{warning}</li>)}
          </ul>
        </div>
      )}

      {/* Rakam yığınından önce üç cümle. Aynı metriklerden üretiliyor. */}
      {!noPositions && <RiskNarrativeCard metrics={metrics} lookback={lookback} />}

      {/* Yumuşak kapı: anket yoksa kart bir çağrıya dönüşür, sayfa kapanmaz. */}
      <div className="mb-6">
        <SuitabilityCard
          suitability={data.suitability}
          declared={data.declared}
          onStart={() => setSurveyOpen(true)}
        />
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3">
        <div className="flex flex-col gap-6 lg:col-span-1">
          <RiskScoreWidget score={data.score ?? null} level={data.level ?? null} />
          <ScoreBreakdown components={data.components ?? []} />
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
              {/* Motorun hesaplayıp sayfanın hiç göstermediği blok. */}
              <RiskMetricsPanel
                metrics={metrics}
                currency={cashflow?.currency_code ?? 'TRY'}
              />
              <RiskConcentrationPanel concentration={concentration} />
              <RiskHistoryPanel />
              <SimulationPanel lookback={lookback} />
              <RiskFactorsWidget factors={data.findings ?? []} />
              <RiskRecommendationsWidget
                recommendations={data.suggestions ?? []}
                resolveTarget={(rec) => suggestionTarget(rec, largestSymbol)}
              />
            </>
          )}
        </div>
      </div>

      <QuestionnaireModal
        open={surveyOpen}
        onClose={() => setSurveyOpen(false)}
        onSaved={() => setReloadKey((value) => value + 1)}
      />
    </div>
  )
}

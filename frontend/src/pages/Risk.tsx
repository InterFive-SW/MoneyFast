import { useState, useEffect } from 'react'
import { apiClient } from '../api/client'
import type { RiskProfile } from '../api/client'

import RiskScoreWidget from '../components/risk/RiskScoreWidget'
import FinancialBalanceWidget from '../components/risk/FinancialBalanceWidget'
import RiskFactorsWidget from '../components/risk/RiskFactorsWidget'
import RiskRecommendationsWidget from '../components/risk/RiskRecommendationsWidget'
import ScoreBreakdown from '../components/risk/ScoreBreakdown'

/**
 * Risk Analizi sayfası.
 *
 * Her sayı `GET /api/risk/profile`'dan gelir ve oradan da
 * `risk/service.calculate`'in gerçek kapanış serilerinden hesapladığı
 * metriklere kadar izlenebilir. Sayfa daha önce `MOCK_RISK_DATA`'yı okuyup
 * 1200 ms'lik sahte bir gecikme uyguluyordu: 68 puan, dört uydurma bulgu ve
 * hiç ölçülmemiş bir borç/gelir oranı.
 */
export default function Risk() {
  const [data, setData] = useState<RiskProfile | null>(null)
  const [loading, setLoading] = useState(true)
  const [failed, setFailed] = useState(false)

  useEffect(() => {
    apiClient
      .getRiskProfile()
      .then(setData)
      .catch((error) => {
        console.error('Risk profili alınamadı', error)
        setFailed(true)
      })
      .finally(() => setLoading(false))
  }, [])

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

  return (
    <div className="min-h-screen p-6 sm:p-8">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Risk Analizi</h1>
          <p className="mt-1 text-sm text-slate-400">
            Portföyünüzün ölçülen oynaklığı, yoğunlaşması ve geçmiş düşüşleri.
          </p>
        </div>
        <div className="text-sm font-medium text-slate-400">
          Son hesaplama:{' '}
          {new Date(data.as_of).toLocaleDateString('tr-TR', {
            hour: '2-digit',
            minute: '2-digit',
          })}
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
            <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6 text-sm text-slate-400">
              Portföyünüzde değerlenebilir pozisyon bulunmadığı için risk
              ölçütleri hesaplanamadı.
            </div>
          ) : (
            <>
              <RiskFactorsWidget factors={data.findings ?? []} />
              <RiskRecommendationsWidget recommendations={data.suggestions ?? []} />
            </>
          )}
        </div>
      </div>
    </div>
  )
}

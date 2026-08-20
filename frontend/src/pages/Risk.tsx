import { useState, useEffect } from 'react'
import { MOCK_RISK_DATA } from '../data/mockRiskData'
import type { RiskData } from '../data/mockRiskData'

import RiskScoreWidget from '../components/risk/RiskScoreWidget'
import FinancialBalanceWidget from '../components/risk/FinancialBalanceWidget'
import RiskFactorsWidget from '../components/risk/RiskFactorsWidget'
import RiskRecommendationsWidget from '../components/risk/RiskRecommendationsWidget'

export default function Risk() {
  const [data, setData] = useState<RiskData | null>(null)
  const [loading, setLoading] = useState(true)

  useEffect(() => {
    // Simulating API fetch
    const timer = setTimeout(() => {
      setData(MOCK_RISK_DATA)
      setLoading(false)
    }, 1200)

    return () => clearTimeout(timer)
  }, [])

  if (loading) {
    return (
      <div className="flex min-h-[50vh] items-center justify-center p-6">
        <div className="flex flex-col items-center gap-4">
          <div className="h-10 w-10 animate-spin rounded-full border-4 border-white/10 border-t-brandBlue" />
          <p className="text-sm font-medium text-slate-400">Risk profiliniz analiz ediliyor...</p>
        </div>
      </div>
    )
  }

  if (!data) {
    return (
      <div className="p-6 sm:p-8 min-h-screen">
        <h1 className="text-2xl font-bold tracking-tight text-white">Risk Analizi</h1>
        <p className="mt-4 text-slate-400">Risk verilerine ulaşılamadı. Lütfen daha sonra tekrar deneyin.</p>
      </div>
    )
  }

  return (
    <div className="p-6 sm:p-8 min-h-screen">
      <div className="mb-6 flex flex-col gap-2 sm:flex-row sm:items-end sm:justify-between">
        <div>
          <h1 className="text-2xl font-bold tracking-tight text-white">Risk Analizi</h1>
          <p className="text-sm text-slate-400 mt-1">
            Finansal sağlığınızı, portföy riskinizi ve iyileştirme fırsatlarınızı buradan takip edebilirsiniz.
          </p>
        </div>
        <div className="text-sm text-slate-400 font-medium">
          Son güncelleme: {new Date(data.lastCalculated).toLocaleDateString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
        </div>
      </div>

      <div className="grid grid-cols-1 gap-6 lg:grid-cols-3 lg:grid-rows-2">
        {/* Sol Sütun: Skor ve Faktörler */}
        <div className="flex flex-col gap-6 lg:col-span-1 lg:row-span-2">
          <RiskScoreWidget score={data.overallScore} level={data.riskLevel} />
          <RiskFactorsWidget factors={data.factors} />
        </div>

        {/* Sağ Sütun: Finansal Denge ve Öneriler */}
        <div className="lg:col-span-2">
          <FinancialBalanceWidget 
            income={data.financialBalance.monthlyIncome} 
            expense={data.financialBalance.monthlyExpense}
            debt={data.financialBalance.totalDebt}
            debtToIncomeRatio={data.financialBalance.debtToIncomeRatio}
          />
        </div>
        <div className="lg:col-span-2">
          <RiskRecommendationsWidget recommendations={data.recommendations} />
        </div>
      </div>
    </div>
  )
}

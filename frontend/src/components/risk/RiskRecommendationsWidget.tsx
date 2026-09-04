import { Link } from 'react-router-dom'
import type { RiskSuggestion } from '../../api/client'

interface RiskRecommendationsWidgetProps {
  recommendations: RiskSuggestion[]
  /**
   * Önerinin gideceği rota, ya da hedefi yoksa `null`.
   *
   * Düğmenin `onClick`'i yoktu: tıklanıyor ve hiçbir şey olmuyordu, ki bu
   * kullanıcıya özelliğin bozuk olduğunu söyler. Her önerinin bir hedefi de
   * yok — "geçmişi eksik enstrümanlar" gidilecek bir ekran değil, bir
   * bilgilendirmedir; o durumda düğme hiç çizilmez.
   */
  resolveTarget?: (suggestion: RiskSuggestion) => string | null
}

const IconArrowRight = () => (
  <svg className="h-4 w-4" fill="none" viewBox="0 0 24 24" stroke="currentColor" strokeWidth={2}>
    <path strokeLinecap="round" strokeLinejoin="round" d="M9 5l7 7-7 7" />
  </svg>
)

export default function RiskRecommendationsWidget({
  recommendations,
  resolveTarget,
}: RiskRecommendationsWidgetProps) {
  return (
    <div className="flex flex-col rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl border-white/10 shadow-2xl p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-white">İyileştirme Önerileri</h3>
        <span className="rounded-full bg-white/10 px-2.5 py-1 text-xs font-medium text-slate-300">
          {recommendations.length} Öneri
        </span>
      </div>
      
      <div className="flex flex-col gap-4">
        {recommendations.map((rec) => {
          // Önceliğe göre ufak bir sol border rengi
          const priorityColor = 
            rec.priority === 'high' ? 'bg-rose-500' :
            rec.priority === 'medium' ? 'bg-amber-500' : 'bg-emerald-500'
          const target = resolveTarget?.(rec) ?? null

          return (
            <div key={rec.id} className="relative flex flex-col rounded-xl border border-white/10 p-4 pl-5 shadow-sm transition-shadow hover:shadow-md">
              {/* Sol kenar çizgisi */}
              <div className={`absolute bottom-0 left-0 top-0 w-1 rounded-l-xl ${priorityColor}`} />
              
              <div className="flex items-start justify-between gap-4">
                <div>
                  <h4 className="text-sm font-semibold text-white">{rec.title}</h4>
                  <p className="mt-1 text-sm text-slate-400">{rec.description}</p>
                </div>
              </div>
              
              {target && (
                <div className="mt-4 flex">
                  <Link
                    to={target}
                    className="group flex items-center gap-1.5 text-sm font-medium text-brandBlue transition-colors hover:text-blue-500"
                  >
                    {rec.actionLabel}
                    <span className="transition-transform group-hover:translate-x-0.5">
                      <IconArrowRight />
                    </span>
                  </Link>
                </div>
              )}
            </div>
          )
        })}
      </div>
    </div>
  )
}

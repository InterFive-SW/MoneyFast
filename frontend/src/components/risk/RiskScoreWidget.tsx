import { useMemo } from 'react'

interface RiskScoreWidgetProps {
  /** null when nothing could be measured. Refusing to score beats defaulting
   *  to 50, which is a number the user could act on. */
  score: number | null
  level: string | null
}

export default function RiskScoreWidget({ score, level }: RiskScoreWidgetProps) {
  const { color, bgColor, label } = useMemo(() => {
    if (level === 'Düşük') return { color: 'text-emerald-500', bgColor: 'bg-emerald-500/10', label: 'Düşük Risk' }
    if (level === 'Orta') return { color: 'text-amber-500', bgColor: 'bg-amber-500/10', label: 'Orta Risk' }
    if (level === 'Yüksek') return { color: 'text-rose-500', bgColor: 'bg-rose-500/10', label: 'Yüksek Risk' }
    return { color: 'text-slate-400', bgColor: 'bg-white/5', label: 'Hesaplanamadı' }
  }, [level])

  // Dairesel progress hesaplamaları
  const radius = 60
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - ((score ?? 0) / 100) * circumference

  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl border-white/10 shadow-2xl p-6 shadow-sm">
      <h3 className="mb-6 text-base font-semibold text-white self-start">Genel Risk Skoru</h3>
      
      <div className="relative flex items-center justify-center">
        {/* Arka plan dairesi */}
        <svg className="h-40 w-40 -rotate-90 transform" viewBox="0 0 140 140">
          <circle
            cx="70"
            cy="70"
            r={radius}
            className="text-slate-800"
            strokeWidth="12"
            stroke="currentColor"
            fill="transparent"
          />
          {/* İlerleme dairesi */}
          <circle
            cx="70"
            cy="70"
            r={radius}
            className={`${color} transition-all duration-1000 ease-out`}
            strokeWidth="12"
            strokeDasharray={circumference}
            strokeDashoffset={strokeDashoffset}
            strokeLinecap="round"
            stroke="currentColor"
            fill="transparent"
          />
        </svg>
        
        {/* Skor Metni */}
        <div className="absolute flex flex-col items-center justify-center">
          <span className="text-4xl font-bold text-white">{score ?? "—"}</span>
          <span className="text-xs font-medium text-slate-400">/ 100</span>
        </div>
      </div>
      
      <div className={`mt-6 rounded-full px-4 py-1.5 text-sm font-semibold ${bgColor} ${color}`}>
        {label}
      </div>
      
      <p className="mt-4 text-center text-sm text-slate-400">
        {score === null
          ? 'Ölçülebilir veri olmadığı için skor hesaplanamadı.'
          : `Risk skoru ${score}/100. Yüksek puan daha sakin bir portföy demektir; oynaklık, yoğunlaşma ve geçmiş düşüşten türetilir.`}
      </p>
    </div>
  )
}

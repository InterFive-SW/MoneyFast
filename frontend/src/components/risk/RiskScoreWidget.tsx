import { useMemo } from 'react'

interface RiskScoreWidgetProps {
  score: number
  level: 'Düşük' | 'Orta' | 'Yüksek'
}

export default function RiskScoreWidget({ score, level }: RiskScoreWidgetProps) {
  const { color, bgColor, label } = useMemo(() => {
    if (level === 'Düşük') return { color: 'text-emerald-500', bgColor: 'bg-emerald-50', label: 'Düşük Risk' }
    if (level === 'Orta') return { color: 'text-amber-500', bgColor: 'bg-amber-50', label: 'Orta Risk' }
    return { color: 'text-rose-500', bgColor: 'bg-rose-50', label: 'Yüksek Risk' }
  }, [level])

  // Dairesel progress hesaplamaları
  const radius = 60
  const circumference = 2 * Math.PI * radius
  const strokeDashoffset = circumference - (score / 100) * circumference

  return (
    <div className="flex flex-col items-center justify-center rounded-2xl border border-slate-200 bg-white p-6 shadow-sm">
      <h3 className="mb-6 text-base font-semibold text-slate-800 self-start">Genel Risk Skoru</h3>
      
      <div className="relative flex items-center justify-center">
        {/* Arka plan dairesi */}
        <svg className="h-40 w-40 -rotate-90 transform" viewBox="0 0 140 140">
          <circle
            cx="70"
            cy="70"
            r={radius}
            className="text-slate-100"
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
          <span className="text-4xl font-bold text-slate-800">{score}</span>
          <span className="text-xs font-medium text-slate-400">/ 100</span>
        </div>
      </div>
      
      <div className={`mt-6 rounded-full px-4 py-1.5 text-sm font-semibold ${bgColor} ${color}`}>
        {label}
      </div>
      
      <p className="mt-4 text-center text-sm text-slate-500">
        Risk skorunuz {score}. Bu skor finansal dayanıklılığınızı ve yatırımlarınızın volatilitesini yansıtır.
      </p>
    </div>
  )
}

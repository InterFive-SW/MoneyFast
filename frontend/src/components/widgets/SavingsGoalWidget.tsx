/**
 * SavingsGoalWidget — Birikim Hedefleri Bileşeni
 */

import type { SavingsGoal } from '../../data/mockData'

export default function SavingsGoalWidget({ goals }: { goals: SavingsGoal[] }) {
  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-medium text-slate-400">Birikim Hedefleri</h3>
      </div>
      <div className="flex-1 overflow-auto -mx-2 px-2 flex flex-col gap-4">
        {goals.map(g => {
          const percent = Math.min(100, Math.round((g.current / g.target) * 100))
          return (
            <div key={g.id} className="flex flex-col">
              <div className="flex justify-between items-center mb-1.5">
                <div className="flex items-center gap-2">
                  <span className="text-sm" aria-hidden="true">{g.icon}</span>
                  <span className="text-[12px] font-semibold text-white uppercase tracking-wider">{g.name}</span>
                </div>
                <span className="text-[12px] font-bold text-white tabular-nums">{percent}%</span>
              </div>
              <div className="h-1.5 w-full bg-white/5/10/80 rounded-full overflow-hidden">
                <div className={`h-full bg-gradient-to-r ${g.color}`} style={{ width: `${percent}%` }} />
              </div>
              <div className="flex justify-between mt-1 text-[10px] text-slate-400 font-medium uppercase tracking-wider">
                <span className="tabular-nums">₺{g.current.toLocaleString('tr-TR')} / ₺{g.target.toLocaleString('tr-TR')}</span>
                <span className="tabular-nums">{g.deadline}</span>
              </div>
            </div>
          )
        })}
      </div>
    </div>
  )
}

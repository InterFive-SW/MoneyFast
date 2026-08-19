/**
 * QuickActionsWidget — Hızlı İşlemler Bileşeni
 */

export default function QuickActionsWidget() {
  const actions = [
    { label: 'Para Gönder', icon: '💸', color: 'bg-emerald-50 text-emerald-600 border-emerald-100' },
    { label: 'Fatura Öde',  icon: '🧾', color: 'bg-blue-50 text-blue-600 border-blue-100' },
    { label: 'Döviz Al/Sat',icon: '💱', color: 'bg-violet-50 text-violet-600 border-violet-100' },
    { label: 'Kredi Çek',   icon: '🏦', color: 'bg-amber-50 text-amber-600 border-amber-100' },
  ]

  return (
    <div className="flex flex-col h-full">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-medium text-slate-400">Hızlı İşlemler</h3>
      </div>
      <div className="grid grid-cols-2 gap-2 h-full">
        {actions.map(a => (
          <button key={a.label} className="flex flex-col items-center justify-center p-2 rounded-xl border border-white/10 bg-white/5 hover:bg-white/5 transition-all hover:shadow-sm">
            <div className={`w-8 h-8 rounded-full flex items-center justify-center text-sm mb-1.5 border ${a.color}`}>
              <span aria-hidden="true">{a.icon}</span>
            </div>
            <span className="text-[10px] font-semibold uppercase tracking-wider text-slate-400">{a.label}</span>
          </button>
        ))}
      </div>
    </div>
  )
}

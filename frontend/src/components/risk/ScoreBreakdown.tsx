import type { RiskProfile } from '../../api/client'

type Component = NonNullable<RiskProfile['components']>[0]

/** Bileşen adlarının Türkçe karşılığı ve ölçünün nasıl okunacağı. */
const LABELS: Record<string, { title: string; unit: 'percent' | 'ratio' }> = {
  volatility: { title: 'Yıllık oynaklık', unit: 'percent' },
  concentration: { title: 'Yoğunlaşma (HHI)', unit: 'ratio' },
  drawdown: { title: 'En büyük düşüş', unit: 'percent' },
}

function measured(value: number | null | undefined, unit: 'percent' | 'ratio') {
  if (value === null || value === undefined) return 'ölçülemedi'
  return unit === 'percent' ? `%${(value * 100).toFixed(1)}` : value.toFixed(3)
}

/**
 * Puanın nereden geldiği.
 *
 * Türetilmesi görülemeyen bir puan, fazladan adımı olan bir sabit değerdir —
 * bu sayfada tam olarak öyle bir puan vardı. Her bileşen, ham ölçüsü ve
 * ağırlığıyla birlikte gösterilir.
 */
export default function ScoreBreakdown({ components }: { components: Component[] }) {
  if (components.length === 0) return null

  return (
    <div className="rounded-2xl border border-white/10 bg-slate-900/50 p-6 shadow-2xl backdrop-blur-xl">
      <h3 className="text-base font-semibold text-white">Puan nasıl oluştu</h3>
      <p className="mt-1 text-[11px] leading-snug text-slate-400">
        Puan 100'den başlar; her bileşen ağırlığı oranında düşürür.
        Ölçülemeyen bir bileşen sıfır sayılmaz, hesaptan çıkarılır.
      </p>

      <div className="mt-4 flex flex-col gap-4">
        {components.map((component) => {
          const meta = LABELS[component.name] ?? { title: component.name, unit: 'ratio' as const }
          const penalty = component.penalty
          const unmeasured = penalty === null || penalty === undefined
          return (
            <div key={component.name}>
              <div className="flex items-baseline justify-between gap-2">
                <span className="text-sm text-slate-300">{meta.title}</span>
                <span className="tabular-nums text-sm font-medium text-white">
                  {measured(component.measured, meta.unit)}
                </span>
              </div>
              <div className="mt-1.5 h-1.5 w-full overflow-hidden rounded-full bg-white/5">
                {!unmeasured && (
                  <div
                    className={`h-full rounded-full ${
                      penalty > 0.66 ? 'bg-rose-500' : penalty > 0.33 ? 'bg-amber-500' : 'bg-emerald-500'
                    }`}
                    style={{ width: `${Math.round(penalty * 100)}%` }}
                  />
                )}
              </div>
              <p className="mt-1 text-[11px] text-slate-500">
                Ağırlık %{component.weight.toFixed(0)}
                {unmeasured && ' · yeterli veri yok, hesaba katılmadı'}
              </p>
            </div>
          )
        })}
      </div>
    </div>
  )
}

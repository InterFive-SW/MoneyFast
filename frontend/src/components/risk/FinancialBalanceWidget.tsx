import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'
import { toNumber } from '../../lib/chartFormat'
import { BASE_CURRENCY, formatMoney } from '../../lib/money'

interface FinancialBalanceWidgetProps {
  period: string
  income: number
  expense: number
  /** null when there was no income to divide by. */
  savingsRate: number | null
  currency?: string
}

/**
 * Gelir ve giderin karşılaştırması — ikisi de banka defterinden.
 *
 * Üçüncü bir "Borç" sütunu ve bir borç/gelir oranı vardı; ikisi de sabit bir
 * fixture'dan geliyordu. Sistemde kredi ya da borç kaydı YOK, dolayısıyla o
 * oran ölçülmüş bir şeyi değil, uydurulmuş iki sayının bölümünü gösteriyordu.
 * Uydurmak yerine raporlanmıyor.
 */
export default function FinancialBalanceWidget({
  period, income, expense, savingsRate, currency = BASE_CURRENCY,
}: FinancialBalanceWidgetProps) {
  const data = [
    { name: 'Gelir', value: income, color: '#10b981' },   // emerald-500
    { name: 'Gider', value: expense, color: '#f59e0b' },  // amber-500
  ]
  const positive = savingsRate !== null && savingsRate >= 0

  return (
    <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl border-white/10 shadow-2xl p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <div>
          <h3 className="text-base font-semibold text-white">Gelir ve Gider</h3>
          <p className="text-[11px] text-slate-400">{period}</p>
        </div>
        {savingsRate === null ? (
          <span className="rounded-full border border-white/10 px-2.5 py-1 text-xs font-medium text-slate-400">
            Tasarruf oranı hesaplanamadı
          </span>
        ) : (
          <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
            positive ? 'bg-emerald-500/10 text-emerald-400' : 'bg-rose-500/10 text-rose-400'
          }`}>
            Tasarruf: %{(savingsRate * 100).toFixed(1)}
          </span>
        )}
      </div>

      <div className="h-64 w-full flex-1">
        <ResponsiveContainer width="100%" height="100%">
          <BarChart data={data} margin={{ top: 10, right: 10, left: 0, bottom: 0 }} barSize={40}>
            <CartesianGrid strokeDasharray="3 3" vertical={false} stroke="#e2e8f0" />
            <XAxis dataKey="name" axisLine={false} tickLine={false} tick={{ fill: '#94a3b8', fontSize: 13 }} dy={10} />
            <YAxis 
              axisLine={false} 
              tickLine={false} 
              tick={{ fill: '#94a3b8', fontSize: 12 }} 
              tickFormatter={(val) => `${(val / 1000).toFixed(0)}k`}
            />
            <Tooltip 
              cursor={{ fill: 'transparent' }}
              contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)' }}
              formatter={(value) => [formatMoney(toNumber(value) ?? 0, currency), 'Tutar']}
            />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      
      <p className="mt-4 text-center text-xs text-slate-400">
        Gelir, hesaplarınıza dışarıdan gelen para; gider, kategorilenmiş harcamalarınız.
        Kendi hesaplarınız arasındaki transferler ikisine de sayılmaz.
      </p>
    </div>
  )
}

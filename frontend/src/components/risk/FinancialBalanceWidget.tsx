import { BarChart, Bar, XAxis, YAxis, CartesianGrid, Tooltip, ResponsiveContainer, Cell } from 'recharts'

interface FinancialBalanceWidgetProps {
  income: number
  expense: number
  debt: number
  debtToIncomeRatio: number
}

const formatCurrency = (val: number) => {
  return new Intl.NumberFormat('tr-TR', { style: 'currency', currency: 'TRY', maximumFractionDigits: 0 }).format(val)
}

export default function FinancialBalanceWidget({ income, expense, debt, debtToIncomeRatio }: FinancialBalanceWidgetProps) {
  const data = [
    { name: 'Gelir', value: income, color: '#10b981' },   // emerald-500
    { name: 'Gider', value: expense, color: '#f59e0b' },  // amber-500
    { name: 'Borç', value: debt, color: '#f43f5e' },      // rose-500
  ]

  return (
    <div className="flex h-full flex-col rounded-2xl border border-white/10 bg-slate-900/50 backdrop-blur-xl border-white/10 shadow-2xl p-6 shadow-sm">
      <div className="mb-4 flex items-center justify-between">
        <h3 className="text-base font-semibold text-white">Finansal Denge</h3>
        <span className={`rounded-full px-2.5 py-1 text-xs font-medium ${
          debtToIncomeRatio > 40 ? 'bg-rose-50 text-rose-600' : 'bg-emerald-50 text-emerald-600'
        }`}>
          Borç/Gelir: %{debtToIncomeRatio}
        </span>
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
              tickFormatter={(val) => `₺${val / 1000}k`}
            />
            <Tooltip 
              cursor={{ fill: 'transparent' }}
              contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 6px -1px rgb(0 0 0 / 0.1), 0 2px 4px -2px rgb(0 0 0 / 0.1)' }}
              formatter={(value: number) => [formatCurrency(value), 'Tutar']}
            />
            <Bar dataKey="value" radius={[6, 6, 0, 0]}>
              {data.map((entry, index) => (
                <Cell key={`cell-${index}`} fill={entry.color} />
              ))}
            </Bar>
          </BarChart>
        </ResponsiveContainer>
      </div>
      
      <p className="mt-4 text-xs text-slate-400 text-center">
        İdeal senaryoda aylık borç ödemelerinizin, gelirinizin %30'unu aşmaması önerilir.
      </p>
    </div>
  )
}

import { useMemo, useState } from 'react'
import { Link, useParams } from 'react-router-dom'
import { Cell, Pie, PieChart, ResponsiveContainer, Tooltip } from 'recharts'
import { findFund, findInstrument } from '../../data/mockData'

type DetailTab = 'ozet' | 'portfoy' | 'getiri'

const TABS: { key: DetailTab; label: string }[] = [
  { key: 'ozet', label: 'Özet' },
  { key: 'portfoy', label: 'Portföy Dağılımı' },
  { key: 'getiri', label: 'Getiri' },
]

const PALETTE = ['#10b981', '#3b82f6', '#f59e0b', '#8b5cf6', '#ef4444', '#06b6d4']

function fmtCompact(value: number): string {
  return new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function fmtReturn(value: number | null): string {
  if (value === null) return 'NA'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

/** Fon detay sayfası — /investment/fonlar/:code, 3 sekme */
export default function FundDetail() {
  const { code = '' } = useParams()
  const [activeTab, setActiveTab] = useState<DetailTab>('ozet')

  const fund = findFund(code.toUpperCase())

  const holdingsWithColor = useMemo(
    () => (fund?.holdings ?? []).map((h, i) => ({ ...h, color: PALETTE[i % PALETTE.length] })),
    [fund]
  )

  if (!fund) {
    return (
      <div className="bg-slate-800/70 backdrop-blur-md rounded-[2rem] p-8 border border-white/50 shadow-sm text-center">
        <p className="text-sm text-slate-400 mb-3">"{code}" kodlu bir fon bulunamadı.</p>
        <Link to="/investment/fonlar" className="text-sm font-semibold text-emerald-500 hover:text-emerald-400">
          ← Fonlar listesine dön
        </Link>
      </div>
    )
  }

  return (
    <div>
      <Link to="/investment/fonlar" className="inline-flex items-center gap-1.5 text-xs font-medium text-slate-400 hover:text-emerald-500 mb-4 transition-colors">
        <svg className="h-3.5 w-3.5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M15 18l-6-6 6-6" /></svg>
        Fonlar listesine dön
      </Link>

      <div className="bg-slate-800/70 backdrop-blur-md rounded-[2rem] p-6 border border-white/50 shadow-sm mb-6">
        <div className="flex flex-wrap items-start justify-between gap-4">
          <div>
            <div className="flex items-center gap-2">
              <h1 className="text-xl font-bold text-white">{fund.code}</h1>
              <span className="text-[10px] font-medium text-slate-400 bg-slate-800/5 px-1.5 py-0.5 rounded">{fund.umbrella}</span>
            </div>
            <p className="text-sm text-slate-400 mt-0.5">{fund.name} — {fund.founder}</p>
          </div>
          <div className="text-right">
            <div className="text-2xl font-bold tabular-nums text-emerald-500">{fmtReturn(fund.returns.yearly)}</div>
            <div className="text-xs text-slate-400">Yıllık getiri</div>
          </div>
        </div>
      </div>

      <div className="flex flex-wrap bg-slate-800/5 p-1 rounded-lg w-fit mb-6">
        {TABS.map((tab) => (
          <button
            key={tab.key}
            onClick={() => setActiveTab(tab.key)}
            className={`px-3.5 py-1.5 text-sm font-semibold rounded-md transition-all ${
              activeTab === tab.key ? 'bg-slate-800 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`}
          >
            {tab.label}
          </button>
        ))}
      </div>

      <div className="bg-slate-800/70 backdrop-blur-md rounded-[2rem] p-6 border border-white/50 shadow-sm">
        {activeTab === 'ozet' && (
          <div className="grid grid-cols-2 sm:grid-cols-4 gap-4">
            {[
              { label: 'Fon Büyüklüğü', value: `${fmtCompact(fund.size)} ₺` },
              { label: 'Yatırımcı Sayısı', value: fmtCompact(fund.investorCount) },
              { label: 'Yönetim Ücreti', value: `%${fund.managementFee.toFixed(1)}` },
              { label: 'Stopaj', value: `%${fund.withholdingTax.toFixed(0)}` },
              { label: 'Risk Değeri', value: `${fund.riskValue} / 7` },
              { label: 'Net Giriş/Çıkış (1A)', value: `${fund.netCashFlow > 0 ? '+' : ''}${fmtCompact(fund.netCashFlow)} ₺` },
            ].map((stat) => (
              <div key={stat.label} className="rounded-xl bg-slate-800/5/60 p-3.5">
                <div className="text-[10px] uppercase tracking-wider font-semibold text-slate-400 mb-1">{stat.label}</div>
                <div className="text-sm font-bold tabular-nums text-white">{stat.value}</div>
              </div>
            ))}
          </div>
        )}

        {activeTab === 'portfoy' && (
          holdingsWithColor.length > 0 ? (
            <div className="flex flex-col sm:flex-row gap-6 items-center">
              <div className="w-full sm:w-1/2 h-[220px]">
                <ResponsiveContainer width="100%" height="100%">
                  <PieChart>
                    <Pie data={holdingsWithColor} dataKey="weight" nameKey="symbol" cx="50%" cy="50%" innerRadius={55} outerRadius={80} paddingAngle={3} stroke="none">
                      {holdingsWithColor.map((h, i) => <Cell key={i} fill={h.color} />)}
                    </Pie>
                    <Tooltip formatter={(value: number, name: string) => [`%${value}`, name]} contentStyle={{ borderRadius: '12px', border: 'none', boxShadow: '0 4px 20px -8px rgba(0,0,0,0.1)' }} />
                  </PieChart>
                </ResponsiveContainer>
              </div>
              <div className="w-full sm:w-1/2 flex flex-col gap-2">
                {holdingsWithColor.map((h) => {
                  const stock = findInstrument(h.symbol)
                  return (
                    <Link key={h.symbol} to={`/investment/hisseler/${h.symbol}`} className="flex items-center justify-between p-2.5 rounded-lg hover:bg-slate-800/5/60 transition-colors">
                      <div className="flex items-center gap-2">
                        <span className="w-2.5 h-2.5 rounded-full" style={{ backgroundColor: h.color }} />
                        <span className="text-sm font-semibold text-white">{h.symbol}</span>
                        {stock && <span className="text-xs text-slate-400">{stock.name}</span>}
                      </div>
                      <span className="text-sm font-bold tabular-nums text-slate-200">%{h.weight}</span>
                    </Link>
                  )
                })}
              </div>
            </div>
          ) : (
            <p className="text-sm text-slate-400">Bu fon türü (borçlanma/para piyasası) için hisse portföyü verisi bulunmuyor.</p>
          )
        )}

        {activeTab === 'getiri' && (
          <table className="w-full text-left border-collapse">
            <tbody className="divide-y divide-slate-100">
              <tr><td className="py-2.5 text-sm text-slate-400">Günlük</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-emerald-500">{fmtReturn(fund.returns.daily)}</td></tr>
              <tr><td className="py-2.5 text-sm text-slate-400">Aylık</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-emerald-500">{fmtReturn(fund.returns.monthly)}</td></tr>
              <tr><td className="py-2.5 text-sm text-slate-400">3 Aylık</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-emerald-500">{fmtReturn(fund.returns.threeMonth)}</td></tr>
              <tr><td className="py-2.5 text-sm text-slate-400">Yıllık</td><td className="py-2.5 text-right text-sm font-semibold tabular-nums text-emerald-500">{fmtReturn(fund.returns.yearly)}</td></tr>
              <tr><td className="py-2.5 text-sm text-slate-400">3 Yıllık</td><td className={`py-2.5 text-right text-sm font-semibold tabular-nums ${fund.returns.threeYear === null ? 'text-slate-400' : 'text-emerald-500'}`}>{fmtReturn(fund.returns.threeYear)}</td></tr>
              <tr><td className="py-2.5 text-sm text-slate-400">5 Yıllık</td><td className={`py-2.5 text-right text-sm font-semibold tabular-nums ${fund.returns.fiveYear === null ? 'text-slate-400' : 'text-emerald-500'}`}>{fmtReturn(fund.returns.fiveYear)}</td></tr>
            </tbody>
          </table>
        )}
      </div>
    </div>
  )
}

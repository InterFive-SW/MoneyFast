import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { Fund } from '../../data/mockData'

type ReturnTab = 'getiri' | 'buyukluk'

interface Props {
  funds: Fund[]
}

function fmtCompact(value: number): string {
  return new Intl.NumberFormat('tr-TR', { notation: 'compact', maximumFractionDigits: 1 }).format(value)
}

function fmtReturn(value: number | null): string {
  if (value === null) return 'NA'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
}

function riskBadgeColor(risk: number): string {
  if (risk <= 2) return 'bg-emerald-500/10 text-emerald-400'
  if (risk <= 4) return 'bg-amber-50 text-amber-700'
  return 'bg-rose-500/10 text-rose-400'
}

/** Fon listesi tablosu — Getiri (1A/3A/1Y/3Y/5Y, NA desteği) / Büyüklük (AUM, yatırımcı, nakit akışı) sekmeleri */
export default function FundsTable({ funds }: Props) {
  const navigate = useNavigate()
  const [tab, setTab] = useState<ReturnTab>('getiri')

  return (
    <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Fon Listesi</h3>
        <div className="flex bg-slate-800/5 p-1 rounded-lg">
          <button onClick={() => setTab('getiri')} className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${tab === 'getiri' ? 'bg-slate-800 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}>Getiri</button>
          <button onClick={() => setTab('buyukluk')} className={`px-3 py-1 text-xs font-semibold rounded-md transition-all ${tab === 'buyukluk' ? 'bg-slate-800 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'}`}>Büyüklük</button>
        </div>
      </div>

      <div className="overflow-x-auto">
        <table className="w-full text-left border-collapse min-w-[820px]">
          <thead>
            <tr className="border-b border-white/10/50">
              <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Fon</th>
              <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Risk</th>
              <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Yön. Ücreti</th>
              {tab === 'getiri' ? (
                <>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">1A</th>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">3A</th>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">1Y</th>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">3Y</th>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">5Y</th>
                </>
              ) : (
                <>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Büyüklük</th>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Yatırımcı</th>
                  <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Net Giriş/Çıkış (1A)</th>
                </>
              )}
            </tr>
          </thead>
          <tbody className="divide-y divide-slate-100/50">
            {funds.map((fund) => (
              <tr
                key={fund.code}
                onClick={() => navigate(`/investment/fonlar/${fund.code}`)}
                className="hover:bg-slate-800/5/50 transition-colors cursor-pointer"
              >
                <td className="py-3">
                  <div className="font-semibold text-white text-sm">{fund.code} <span className="text-slate-400 font-normal">— {fund.name}</span></div>
                  <div className="flex items-center gap-1.5 mt-0.5">
                    <span className="text-xs text-slate-400">{fund.founder}</span>
                    <span className="text-[10px] font-medium text-slate-400 bg-slate-800/5 px-1.5 py-0.5 rounded">{fund.umbrella}</span>
                  </div>
                </td>
                <td className="py-3 pl-4 text-right">
                  <span className={`inline-block px-2 py-0.5 rounded-md text-xs font-bold tabular-nums ${riskBadgeColor(fund.riskValue)}`}>{fund.riskValue}</span>
                </td>
                <td className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">%{fund.managementFee.toFixed(1)}</td>
                {tab === 'getiri' ? (
                  <>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm font-semibold text-emerald-500">{fmtReturn(fund.returns.monthly)}</td>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm font-semibold text-emerald-500">{fmtReturn(fund.returns.threeMonth)}</td>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm font-semibold text-emerald-500">{fmtReturn(fund.returns.yearly)}</td>
                    <td className={`py-3 pl-4 text-right tabular-nums text-sm font-semibold ${fund.returns.threeYear === null ? 'text-slate-400' : 'text-emerald-500'}`}>{fmtReturn(fund.returns.threeYear)}</td>
                    <td className={`py-3 pl-4 text-right tabular-nums text-sm font-semibold ${fund.returns.fiveYear === null ? 'text-slate-400' : 'text-emerald-500'}`}>{fmtReturn(fund.returns.fiveYear)}</td>
                  </>
                ) : (
                  <>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">{fmtCompact(fund.size)} ₺</td>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">{fmtCompact(fund.investorCount)}</td>
                    <td className={`py-3 pl-4 text-right tabular-nums text-sm font-semibold ${fund.netCashFlow < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                      {fund.netCashFlow > 0 ? '+' : ''}{fmtCompact(fund.netCashFlow)} ₺
                    </td>
                  </>
                )}
              </tr>
            ))}
            {funds.length === 0 && (
              <tr>
                <td colSpan={8} className="py-8 text-center text-sm text-slate-400">Filtrenizle eşleşen fon bulunamadı.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

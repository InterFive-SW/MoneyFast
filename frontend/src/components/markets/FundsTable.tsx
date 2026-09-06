import { useState } from 'react'
import { useNavigate } from 'react-router-dom'
import type { ApiFund } from '../../api/client'
import { formatCompact, formatMoney } from '../../lib/money'

type ReturnTab = 'getiri' | 'buyukluk'

interface Props {
  funds: ApiFund[]
}

/** Getiri sütununun rengi.
 *
 *  Hepsi yeşildi ve bu bir hataydı: negatif bir getiri de yeşil yazılıyordu.
 *  Ölçülemeyen pencere (`null`) gri -- "kaybettirdi" ile "o kadar geçmişi
 *  yok" karşıt iddialar. */
function returnClass(value: number | null): string {
  const base = 'py-3 pl-4 text-right tabular-nums text-sm font-semibold '
  if (value === null) return base + 'text-slate-400'
  return base + (value < 0 ? 'text-rose-500' : 'text-emerald-500')
}

/** Sayı yoksa tire. Sıfır DEĞİL: boş bir alan ölçüm değildir. */
function fmtCompact(value: number | null | undefined): string {
  return value == null ? '—' : formatCompact(value)
}

function fmtReturn(value: number | null): string {
  if (value === null) return 'NA'
  return `${value > 0 ? '+' : ''}${value.toFixed(1)}%`
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
              {/* Risk değeri ve yönetim ücreti sütunları KALDIRILDI: TEFAS
                  API'si ikisini de döndürmüyor (bkz. docs/TEFAS_INTEGRATION.md)
                  ve döndürmediği bir alan için sütun yazmak, "veri yok"u bir
                  ölçüm gibi göstermek olurdu. Yerine gerçekten dönen şey. */}
              <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Fiyat</th>
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
                <td className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">
                  {fund.price == null ? '—' : formatMoney(fund.price)}
                </td>
                {tab === 'getiri' ? (
                  <>
                    <td className={returnClass(fund.returns.monthly)}>{fmtReturn(fund.returns.monthly)}</td>
                    <td className={returnClass(fund.returns.threeMonth)}>{fmtReturn(fund.returns.threeMonth)}</td>
                    <td className={returnClass(fund.returns.yearly)}>{fmtReturn(fund.returns.yearly)}</td>
                    <td className={returnClass(fund.returns.threeYear)}>{fmtReturn(fund.returns.threeYear)}</td>
                    <td className={returnClass(fund.returns.fiveYear)}>{fmtReturn(fund.returns.fiveYear)}</td>
                  </>
                ) : (
                  <>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">{fmtCompact(fund.size)} ₺</td>
                    <td className="py-3 pl-4 text-right tabular-nums text-sm text-slate-300">{fmtCompact(fund.investorCount)}</td>
                  </>
                )}
              </tr>
            ))}
            {funds.length === 0 && (
              <tr>
                <td colSpan={7} className="py-8 text-center text-sm text-slate-400">Filtrenizle eşleşen fon bulunamadı.</td>
              </tr>
            )}
          </tbody>
        </table>
      </div>
    </div>
  )
}

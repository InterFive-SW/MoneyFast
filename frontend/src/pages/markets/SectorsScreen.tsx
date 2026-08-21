import { useMemo, useState } from 'react'
import { Link } from 'react-router-dom'
import type { MarketInstrument } from '../../data/mockData'
import { CUSTOM_SECTOR_GROUPS } from '../../data/sectorGroups'
import { useInstruments } from '../../hooks/useInstruments'

function fmt(value: number | undefined, suffix = ''): string {
  if (value === undefined) return '—'
  return `${value.toFixed(1)}${suffix}`
}

function CompanyComparisonTable({ instruments }: { instruments: MarketInstrument[] }) {
  return (
    <div className="overflow-x-auto mt-3">
      <table className="w-full text-left border-collapse min-w-[560px]">
        <thead>
          <tr className="border-b border-white/10/50">
            <th className="py-2 text-[10px] uppercase tracking-wider font-semibold text-slate-400">Şirket</th>
            <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Fiyat</th>
            <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">Değişim</th>
            <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">F/K</th>
            <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">PD/DD</th>
            <th className="py-2 pl-4 text-[10px] uppercase tracking-wider font-semibold text-slate-400 text-right">FD/FAVÖK</th>
          </tr>
        </thead>
        <tbody className="divide-y divide-slate-100/50">
          {instruments.map((item) => (
            <tr key={item.symbol} className="hover:bg-slate-800/5/50 transition-colors">
              <td className="py-2.5">
                <Link to={`/investment/hisseler/${item.symbol}`} className="text-sm font-semibold text-white hover:text-emerald-500 transition-colors">{item.symbol}</Link>
                <span className="text-xs text-slate-400 ml-2">{item.name}</span>
              </td>
              <td className="py-2.5 pl-4 text-right tabular-nums text-sm text-slate-200">{item.price.toLocaleString('tr-TR', { minimumFractionDigits: 2, maximumFractionDigits: 2 })} {item.unit}</td>
              <td className={`py-2.5 pl-4 text-right tabular-nums text-sm font-semibold ${item.changePercent < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>{item.changePercent > 0 ? '+' : ''}{item.changePercent.toFixed(2)}%</td>
              <td className="py-2.5 pl-4 text-right tabular-nums text-sm text-slate-300">{fmt(item.pe, 'x')}</td>
              <td className="py-2.5 pl-4 text-right tabular-nums text-sm text-slate-300">{fmt(item.pb, 'x')}</td>
              <td className="py-2.5 pl-4 text-right tabular-nums text-sm text-slate-300">{fmt(item.evEbitda, 'x')}</td>
            </tr>
          ))}
        </tbody>
      </table>
    </div>
  )
}

/** Sektörler ekranı — resmî sektör listesi + F/K,PD/DD,FD/FAVÖK karşılaştırması + En Sektörler/En Hisseler + özel segmentasyon */
export default function SectorsScreen() {
  const [expandedSector, setExpandedSector] = useState<string | null>(null)
  const [expandedGroup, setExpandedGroup] = useState<string | null>(null)

  // Sektör kırılımı canlı evrenden türetiliyor. `/api/investment/
  // sector-allocation` kullanılmadı: o uç nokta PORTFÖY sektör dağılımını
  // verir, bu ekran ise piyasa genelini gösteriyor — ikisi farklı soru.
  const { instruments, loading } = useInstruments()

  const sectorStats = useMemo(() => {
    const bySector = new Map<string, MarketInstrument[]>()
    for (const item of instruments) {
      if (!bySector.has(item.sector)) bySector.set(item.sector, [])
      bySector.get(item.sector)!.push(item)
    }
    return Array.from(bySector.entries())
      .map(([sector, items]) => ({
        sector,
        items,
        avgChange: items.reduce((acc, i) => acc + i.changePercent, 0) / items.length,
      }))
      .sort((a, b) => b.avgChange - a.avgChange)
  }, [instruments])

  const topSectors = sectorStats.slice(0, 3)
  const bottomSectors = [...sectorStats].sort((a, b) => a.avgChange - b.avgChange).slice(0, 3)

  const topStocks = useMemo(
    () => [...instruments].sort((a, b) => b.changePercent - a.changePercent).slice(0, 3),
    [instruments]
  )
  const bottomStocks = useMemo(
    () => [...instruments].sort((a, b) => a.changePercent - b.changePercent).slice(0, 3),
    [instruments]
  )

  if (loading) {
    return (
      <div className="flex items-center justify-center py-20">
        <div className="animate-spin rounded-full h-8 w-8 border-b-2 border-emerald-500"></div>
      </div>
    )
  }

  return (
    <div>
      {/* En Sektörler / En Hisseler */}
      <div className="grid grid-cols-1 lg:grid-cols-2 gap-6 mb-6">
        <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
          <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-3">En Sektörler</h3>
          <div className="flex flex-col gap-2">
            {topSectors.map((s) => (
              <div key={s.sector} className="flex items-center justify-between p-2.5 bg-emerald-500/10/50 rounded-lg">
                <span className="text-sm font-semibold text-white">{s.sector}</span>
                <span className="text-sm font-bold tabular-nums text-emerald-500">+{s.avgChange.toFixed(2)}%</span>
              </div>
            ))}
            {bottomSectors.map((s) => (
              <div key={s.sector} className="flex items-center justify-between p-2.5 bg-rose-500/10/50 rounded-lg">
                <span className="text-sm font-semibold text-white">{s.sector}</span>
                <span className="text-sm font-bold tabular-nums text-rose-500">{s.avgChange.toFixed(2)}%</span>
              </div>
            ))}
          </div>
        </div>

        <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
          <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-3">En Hisseler</h3>
          <div className="flex flex-col gap-2">
            {topStocks.map((s) => (
              <Link key={s.symbol} to={`/investment/hisseler/${s.symbol}`} className="flex items-center justify-between p-2.5 bg-emerald-500/10/50 rounded-lg hover:bg-emerald-500/10 transition-colors">
                <span className="text-sm font-semibold text-white">{s.symbol} <span className="text-xs text-slate-400 font-normal">{s.name}</span></span>
                <span className="text-sm font-bold tabular-nums text-emerald-500">+{s.changePercent.toFixed(2)}%</span>
              </Link>
            ))}
            {bottomStocks.map((s) => (
              <Link key={s.symbol} to={`/investment/hisseler/${s.symbol}`} className="flex items-center justify-between p-2.5 bg-rose-500/10/50 rounded-lg hover:bg-rose-500/10 transition-colors">
                <span className="text-sm font-semibold text-white">{s.symbol} <span className="text-xs text-slate-400 font-normal">{s.name}</span></span>
                <span className="text-sm font-bold tabular-nums text-rose-500">{s.changePercent.toFixed(2)}%</span>
              </Link>
            ))}
          </div>
        </div>
      </div>

      {/* Resmî sektör listesi */}
      <div className="mb-6">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-3 px-1">Sektörler</h3>
        <div className="flex flex-col gap-3">
          {sectorStats.map(({ sector, items, avgChange }) => {
            const isExpanded = expandedSector === sector
            return (
              <div key={sector} className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5">
                <button onClick={() => setExpandedSector(isExpanded ? null : sector)} className="w-full flex items-center justify-between text-left">
                  <div>
                    <span className="text-sm font-bold text-white">{sector}</span>
                    <span className="text-xs text-slate-400 ml-2">{items.length} şirket</span>
                  </div>
                  <div className="flex items-center gap-3">
                    <span className={`text-sm font-bold tabular-nums ${avgChange < 0 ? 'text-rose-500' : 'text-emerald-500'}`}>
                      {avgChange > 0 ? '+' : ''}{avgChange.toFixed(2)}%
                    </span>
                    <svg className={`h-4 w-4 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
                  </div>
                </button>
                {isExpanded && <CompanyComparisonTable instruments={items} />}
              </div>
            )
          })}
        </div>
      </div>

      {/* Özel segmentasyon — BIST'in resmî sınıflandırmasında olmayan gruplar */}
      <div>
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400 mb-3 px-1">
          Özel Gruplar <span className="normal-case text-slate-400">(resmî BIST sınıflandırmasında yer almaz)</span>
        </h3>
        <div className="flex flex-col gap-3">
          {CUSTOM_SECTOR_GROUPS.map((group) => {
            const items = instruments.filter((i) => group.symbols.includes(i.symbol))
            const isExpanded = expandedGroup === group.name
            return (
              <div key={group.name} className="bg-slate-800/70 backdrop-blur-md rounded-[2rem] p-5 border border-dashed border-emerald-200/70 shadow-sm">
                <button onClick={() => setExpandedGroup(isExpanded ? null : group.name)} className="w-full flex items-center justify-between text-left">
                  <div>
                    <div className="flex items-center gap-2">
                      <span className="text-sm font-bold text-white">{group.name}</span>
                      <span className="text-[10px] font-semibold text-emerald-500 bg-emerald-500/10 px-1.5 py-0.5 rounded">Özel</span>
                    </div>
                    <p className="text-xs text-slate-400 mt-1 max-w-xl">{group.description}</p>
                  </div>
                  <svg className={`h-4 w-4 shrink-0 text-slate-400 transition-transform ${isExpanded ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="6 9 12 15 18 9" /></svg>
                </button>
                {isExpanded && <CompanyComparisonTable instruments={items} />}
              </div>
            )
          })}
        </div>
      </div>
    </div>
  )
}

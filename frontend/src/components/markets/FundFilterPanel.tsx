import type { Fund } from '../../data/mockData'

export interface FundFilters {
  feeMax:    string
  riskValue: string // '' = tümü, '1'-'7'
  founder:   string
  umbrella:  string
}

export const EMPTY_FUND_FILTERS: FundFilters = { feeMax: '', riskValue: '', founder: '', umbrella: '' }

export function applyFundFilters(funds: Fund[], filters: FundFilters): Fund[] {
  return funds.filter((f) => {
    if (filters.feeMax && f.managementFee > Number(filters.feeMax)) return false
    if (filters.riskValue && f.riskValue !== Number(filters.riskValue)) return false
    if (filters.founder && f.founder !== filters.founder) return false
    if (filters.umbrella && f.umbrella !== filters.umbrella) return false
    return true
  })
}

interface Props {
  filters:   FundFilters
  onChange:  (filters: FundFilters) => void
  founders:  string[]
  umbrellas: string[]
}

/** Fonlar filtre paneli — yönetim ücreti, risk değeri, kurucu/PYŞ, şemsiye türü */
export default function FundFilterPanel({ filters, onChange, founders, umbrellas }: Props) {
  const inputClass = 'w-full rounded-lg border border-slate-200 bg-white px-2.5 py-1.5 text-xs text-slate-700 outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400'

  function updateField(key: keyof FundFilters, value: string) {
    onChange({ ...filters, [key]: value })
  }

  return (
    <div className="bg-white/70 backdrop-blur-md rounded-2xl p-5 border border-white/50 shadow-sm mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-500">Filtrele</h3>
        <button onClick={() => onChange(EMPTY_FUND_FILTERS)} className="text-xs font-medium text-slate-400 hover:text-slate-600">
          Temizle
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Azami Yönetim Ücreti %</label>
          <input type="number" value={filters.feeMax} onChange={(e) => updateField('feeMax', e.target.value)} placeholder="Örn. 2.0" className={inputClass} />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Risk Değeri</label>
          <select value={filters.riskValue} onChange={(e) => updateField('riskValue', e.target.value)} className={inputClass}>
            <option value="">Tümü</option>
            {[1, 2, 3, 4, 5, 6, 7].map((r) => <option key={r} value={r}>{r}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Kurucu / PYŞ</label>
          <select value={filters.founder} onChange={(e) => updateField('founder', e.target.value)} className={inputClass}>
            <option value="">Tümü</option>
            {founders.map((f) => <option key={f} value={f}>{f}</option>)}
          </select>
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Şemsiye Türü</label>
          <select value={filters.umbrella} onChange={(e) => updateField('umbrella', e.target.value)} className={inputClass}>
            <option value="">Tümü</option>
            {umbrellas.map((u) => <option key={u} value={u}>{u}</option>)}
          </select>
        </div>
      </div>
    </div>
  )
}

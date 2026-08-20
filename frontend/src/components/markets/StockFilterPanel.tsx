import { useState } from 'react'
import type { MarketInstrument } from '../../data/mockData'

export interface StockFilters {
  peMin:          string
  peMax:          string
  pbMin:          string
  pbMax:          string
  marketCapMinBn: string // Milyar cinsinden
  marketCapMaxBn: string
  changeMin:      string
  changeMax:      string
  sector:         string
}

export const EMPTY_STOCK_FILTERS: StockFilters = {
  peMin: '', peMax: '', pbMin: '', pbMax: '',
  marketCapMinBn: '', marketCapMaxBn: '',
  changeMin: '', changeMax: '', sector: '',
}

/** ~8-10 kriterlik sadeleştirilmiş filtre — Fintables'taki "onlarca kriter"in daraltılmış V1 hali */
export function applyStockFilters(instruments: MarketInstrument[], filters: StockFilters): MarketInstrument[] {
  return instruments.filter((item) => {
    if (filters.peMin && (item.pe === undefined || item.pe < Number(filters.peMin))) return false
    if (filters.peMax && (item.pe === undefined || item.pe > Number(filters.peMax))) return false
    if (filters.pbMin && (item.pb === undefined || item.pb < Number(filters.pbMin))) return false
    if (filters.pbMax && (item.pb === undefined || item.pb > Number(filters.pbMax))) return false
    if (filters.marketCapMinBn && item.marketCap < Number(filters.marketCapMinBn) * 1_000_000_000) return false
    if (filters.marketCapMaxBn && item.marketCap > Number(filters.marketCapMaxBn) * 1_000_000_000) return false
    if (filters.changeMin && item.changePercent < Number(filters.changeMin)) return false
    if (filters.changeMax && item.changePercent > Number(filters.changeMax)) return false
    if (filters.sector && item.sector !== filters.sector) return false
    return true
  })
}

interface SavedSearch {
  id:      string
  name:    string
  filters: StockFilters
}

const STORAGE_KEY = 'mf_stock_saved_searches'

function loadSavedSearches(): SavedSearch[] {
  try {
    const raw = localStorage.getItem(STORAGE_KEY)
    if (raw) return JSON.parse(raw)
  } catch {}
  return []
}

interface Props {
  filters: StockFilters
  onChange: (filters: StockFilters) => void
  sectors: string[]
}

/**
 * Hisseler filtre paneli — F/K, PD/DD, piyasa değeri, değişim% aralıkları + sektör.
 * Kayıtlı Aramalar localStorage'da tutulur (isim + filtre state); link paylaşımı V1 kapsamı dışı.
 */
export default function StockFilterPanel({ filters, onChange, sectors }: Props) {
  const [savedSearches, setSavedSearches] = useState<SavedSearch[]>(loadSavedSearches)
  const [saveName, setSaveName] = useState('')
  const [showSaveInput, setShowSaveInput] = useState(false)

  function updateField(key: keyof StockFilters, value: string) {
    onChange({ ...filters, [key]: value })
  }

  function handleSave() {
    if (!saveName.trim()) return
    const next = [...savedSearches, { id: `search-${Date.now()}`, name: saveName.trim(), filters }]
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setSavedSearches(next)
    setSaveName('')
    setShowSaveInput(false)
  }

  function handleLoad(search: SavedSearch) {
    onChange(search.filters)
  }

  function handleDelete(id: string) {
    const next = savedSearches.filter((s) => s.id !== id)
    localStorage.setItem(STORAGE_KEY, JSON.stringify(next))
    setSavedSearches(next)
  }

  const inputClass = 'w-full rounded-lg border border-white/10 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400'

  return (
    <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Filtrele</h3>
        <button onClick={() => onChange(EMPTY_STOCK_FILTERS)} className="text-xs font-medium text-slate-400 hover:text-slate-300">
          Temizle
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-3 lg:grid-cols-5 gap-3 mb-4">
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">F/K</label>
          <div className="flex gap-1.5">
            <input type="number" value={filters.peMin} onChange={(e) => updateField('peMin', e.target.value)} placeholder="Min" className={inputClass} />
            <input type="number" value={filters.peMax} onChange={(e) => updateField('peMax', e.target.value)} placeholder="Max" className={inputClass} />
          </div>
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">PD/DD</label>
          <div className="flex gap-1.5">
            <input type="number" value={filters.pbMin} onChange={(e) => updateField('pbMin', e.target.value)} placeholder="Min" className={inputClass} />
            <input type="number" value={filters.pbMax} onChange={(e) => updateField('pbMax', e.target.value)} placeholder="Max" className={inputClass} />
          </div>
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Piy. Değeri (Milyar)</label>
          <div className="flex gap-1.5">
            <input type="number" value={filters.marketCapMinBn} onChange={(e) => updateField('marketCapMinBn', e.target.value)} placeholder="Min" className={inputClass} />
            <input type="number" value={filters.marketCapMaxBn} onChange={(e) => updateField('marketCapMaxBn', e.target.value)} placeholder="Max" className={inputClass} />
          </div>
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Değişim %</label>
          <div className="flex gap-1.5">
            <input type="number" value={filters.changeMin} onChange={(e) => updateField('changeMin', e.target.value)} placeholder="Min" className={inputClass} />
            <input type="number" value={filters.changeMax} onChange={(e) => updateField('changeMax', e.target.value)} placeholder="Max" className={inputClass} />
          </div>
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Sektör</label>
          <select value={filters.sector} onChange={(e) => updateField('sector', e.target.value)} className={inputClass}>
            <option value="">Tümü</option>
            {sectors.map((s) => (
              <option key={s} value={s}>{s}</option>
            ))}
          </select>
        </div>
      </div>

      <div className="flex items-center justify-between flex-wrap gap-3 pt-3 border-t border-white/10">
        <div className="flex flex-wrap items-center gap-1.5">
          <span className="text-[10px] uppercase font-semibold text-slate-400 mr-1">Kayıtlı Aramalar:</span>
          {savedSearches.length === 0 && <span className="text-xs text-slate-400">yok</span>}
          {savedSearches.map((s) => (
            <span key={s.id} className="inline-flex items-center gap-1 rounded-lg bg-slate-800/5 pl-2.5 pr-1 py-1 text-xs font-medium text-slate-300">
              <button onClick={() => handleLoad(s)} className="hover:text-emerald-500">{s.name}</button>
              <button onClick={() => handleDelete(s.id)} aria-label={`${s.name} sil`} className="text-slate-400 hover:text-rose-500 px-1">×</button>
            </span>
          ))}
        </div>

        {showSaveInput ? (
          <div className="flex items-center gap-1.5">
            <input autoFocus value={saveName} onChange={(e) => setSaveName(e.target.value)} placeholder="Arama adı..." className={`${inputClass} w-32`} />
            <button onClick={handleSave} className="text-xs font-semibold text-emerald-500 hover:text-emerald-400">Kaydet</button>
            <button onClick={() => setShowSaveInput(false)} className="text-xs text-slate-400 hover:text-slate-300">İptal</button>
          </div>
        ) : (
          <button onClick={() => setShowSaveInput(true)} className="text-xs font-semibold text-emerald-500 hover:text-emerald-400">
            + Bu Aramayı Kaydet
          </button>
        )}
      </div>
    </div>
  )
}

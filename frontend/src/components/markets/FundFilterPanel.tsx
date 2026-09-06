/**
 * Fonlar süzgeç paneli.
 *
 * "Azami Yönetim Ücreti" ve "Risk Değeri" KALDIRILDI. Mock'ta vardılar ama
 * TEFAS API'si bu iki alanı döndürmüyor -- HAR kaydındaki 85 alanın hepsi
 * tarandı, bkz. `docs/TEFAS_INTEGRATION.md`. Hiçbir şeyi süzemeyen bir
 * süzgeç, kullanıcıya sistemin bilmediği bir şeyi biliyormuş gibi
 * gösteriyor; boş bırakmaktansa kaldırmak dürüst.
 *
 * Yerlerine TEFAS'ın gerçekten verdiği iki eksen geldi: fon tipi ve serbest
 * metin araması.
 *
 * Süzme SUNUCUDA: evren 2.602 fon. `applyFundFilters` diye bir istemci
 * fonksiyonu vardı ve o mock listeyi süzüyordu; artık süzgeçler sorguya
 * gidiyor.
 */

export interface FundFilters {
  fundType: string
  founder:  string
  umbrella: string
  q:        string
}

export const EMPTY_FUND_FILTERS: FundFilters = {
  fundType: '', founder: '', umbrella: '', q: '',
}

/** TEFAS'ın fon tipi kodları. */
const FUND_TYPES: { value: string; label: string }[] = [
  { value: 'YAT', label: 'Menkul Kıymet' },
  { value: 'EMK', label: 'Emeklilik' },
  { value: 'BYF', label: 'Borsa Yatırım' },
]

interface Props {
  filters:   FundFilters
  onChange:  (filters: FundFilters) => void
  founders:  string[]
  umbrellas: string[]
}

export default function FundFilterPanel({ filters, onChange, founders, umbrellas }: Props) {
  const inputClass = 'w-full rounded-lg border border-white/10 bg-slate-800 px-2.5 py-1.5 text-xs text-slate-200 outline-none focus:border-emerald-400 focus:ring-1 focus:ring-emerald-400'

  function updateField(key: keyof FundFilters, value: string) {
    onChange({ ...filters, [key]: value })
  }

  return (
    <div className="bg-slate-900/50 backdrop-blur-xl rounded-[2rem] border border-white/10 shadow-2xl p-5 mb-6">
      <div className="flex items-center justify-between mb-4">
        <h3 className="text-[11px] uppercase tracking-wider font-semibold text-slate-400">Filtrele</h3>
        <button onClick={() => onChange(EMPTY_FUND_FILTERS)} className="text-xs font-medium text-slate-400 hover:text-slate-300">
          Temizle
        </button>
      </div>

      <div className="grid grid-cols-2 sm:grid-cols-4 gap-3">
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Fon Ara</label>
          <input
            type="search"
            value={filters.q}
            onChange={(e) => updateField('q', e.target.value)}
            placeholder="Kod ya da ad"
            className={inputClass}
          />
        </div>
        <div>
          <label className="block text-[10px] font-semibold text-slate-400 uppercase mb-1">Fon Tipi</label>
          <select value={filters.fundType} onChange={(e) => updateField('fundType', e.target.value)} className={inputClass}>
            <option value="">Tümü</option>
            {FUND_TYPES.map((t) => <option key={t.value} value={t.value}>{t.label}</option>)}
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

import { COLUMN_SETS, type ColumnSetKey } from '../../data/columnSets'

interface Props {
  value: ColumnSetKey
  onChange: (key: ColumnSetKey) => void
}

/** Hazır kolon setleri arasında tek tıkla geçiş — Getiri/Değerleme/Kârlılık/Borçluluk/Büyüme/Bilanço/Gelir Tablosu/Nakit Akım */
export default function ColumnSetSwitcher({ value, onChange }: Props) {
  return (
    <div className="flex flex-wrap gap-1.5">
      {COLUMN_SETS.map((set) => (
        <button
          key={set.key}
          onClick={() => onChange(set.key)}
          className={`px-3 py-1.5 text-xs font-semibold rounded-lg border transition-colors ${
            value === set.key
              ? 'bg-emerald-500 text-white border-emerald-500'
              : 'bg-slate-800 text-slate-300 border-white/10 hover:border-slate-300'
          }`}
        >
          {set.label}
        </button>
      ))}
    </div>
  )
}

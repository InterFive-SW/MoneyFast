import { NavLink } from 'react-router-dom'

const TABS = [
  { to: '/investment/hisseler',  label: 'Hisseler' },
  { to: '/investment/doviz-altin', label: 'Döviz & Altın' },
  { to: '/investment/fonlar',    label: 'Fonlar' },
  { to: '/investment/endeksler', label: 'Endeksler' },
  { to: '/investment/sektorler', label: 'Sektörler' },
  { to: '/investment/analizler', label: 'Analizler' },
]

/** Piyasalar ekranının 5 bölümü arasında geçiş için yatay pill-tab şeridi */
export default function MarketsSubNav() {
  return (
    <div className="flex flex-wrap bg-slate-800/5 p-1 rounded-lg backdrop-blur-sm w-fit mb-6" role="tablist" aria-label="Piyasalar bölümleri">
      {TABS.map((tab) => (
        <NavLink
          key={tab.to}
          to={tab.to}
          className={({ isActive }) =>
            `px-4 py-1.5 text-sm font-semibold rounded-md transition-all ${
              isActive ? 'bg-slate-800 text-white shadow-sm' : 'text-slate-400 hover:text-slate-200'
            }`
          }
        >
          {tab.label}
        </NavLink>
      ))}
    </div>
  )
}

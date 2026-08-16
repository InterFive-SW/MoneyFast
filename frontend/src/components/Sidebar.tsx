import { NavLink } from 'react-router-dom'
import { useState } from 'react'

const links = [
  { 
    to: '/dashboard', 
    label: 'Gösterge Paneli',
    icon: <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="3" y="3" width="7" height="7"></rect><rect x="14" y="3" width="7" height="7"></rect><rect x="14" y="14" width="7" height="7"></rect><rect x="3" y="14" width="7" height="7"></rect></svg>
  },
  { 
    to: '/banking', 
    label: 'Cüzdan',
    icon: <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><rect x="2" y="5" width="20" height="14" rx="2"></rect><line x1="2" y1="10" x2="22" y2="10"></line></svg>
  },
  { 
    to: '/investment', 
    label: 'Yatırımlar',
    icon: <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline><polyline points="16 7 22 7 22 13"></polyline></svg>
  },
  { 
    to: '/chat', 
    label: 'AI Asistan',
    icon: <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path></svg>
  },
  { 
    to: '/risk', 
    label: 'Risk Analizi',
    icon: <svg className="w-[18px] h-[18px]" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M12 22s8-4 8-10V5l-8-3-8 3v7c0 6 8 10 8 10z"></path></svg>
  },
]

export default function Sidebar() {
  const [collapsed, setCollapsed] = useState(false)

  return (
    <aside className={`${collapsed ? 'w-20' : 'w-64'} shrink-0 h-screen bg-white border-r border-slate-100 flex flex-col transition-all duration-300 relative`}>
      
      {/* ── Daralt/Genişlet Butonu ── */}
      <button 
        onClick={() => setCollapsed(!collapsed)}
        className="absolute -right-3.5 top-8 flex h-7 w-7 items-center justify-center rounded-full border border-slate-200 bg-white text-slate-400 shadow-sm hover:text-slate-600 z-10 transition-colors"
      >
        <svg className={`w-4 h-4 transition-transform ${collapsed ? 'rotate-180' : ''}`} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><polyline points="15 18 9 12 15 6"></polyline></svg>
      </button>

      {/* ── Logo Alanı ── */}
      <div className={`px-6 py-8 flex items-center ${collapsed ? 'justify-center px-0' : 'gap-3'}`}>
        <div className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-emerald-400 text-white shadow-sm">
          <span className="font-bold text-sm tracking-wide">MF</span>
        </div>
        {!collapsed && (
          <div className="flex flex-col whitespace-nowrap overflow-hidden">
            <span className="text-[17px] font-bold tracking-tight text-slate-900 leading-tight">
              MoneyFast
            </span>
            <span className="text-[13px] font-medium text-slate-400 leading-tight">
              Finans Platformu
            </span>
          </div>
        )}
      </div>
      
      {/* ── Menü ── */}
      <nav className="flex-1 px-4 py-2 space-y-1.5 overflow-hidden">
        {!collapsed && (
          <div className="px-3 pb-3 text-[11px] font-bold uppercase tracking-wider text-slate-400">
            MENÜ
          </div>
        )}
        {links.map(({ to, label, icon }) => (
          <NavLink
            key={to}
            to={to}
            className={({ isActive }) =>
              `group relative flex items-center ${collapsed ? 'justify-center px-0' : 'gap-3.5 px-4'} py-3 rounded-2xl text-[15px] transition-all duration-200 ${
                isActive
                  ? 'bg-emerald-50 text-emerald-700 font-semibold border border-emerald-100/60'
                  : 'text-slate-500 font-medium hover:bg-slate-50 hover:text-slate-800 border border-transparent'
              }`
            }
          >
            {({ isActive }) => (
              <>
                <div className={`transition-colors duration-200 ${isActive ? 'text-emerald-600' : 'text-slate-400 group-hover:text-slate-600'}`}>
                  {icon}
                </div>
                {!collapsed && (
                  <>
                    <span className="whitespace-nowrap">{label}</span>
                    {isActive && (
                      <div className="absolute right-4 w-1.5 h-1.5 rounded-full bg-emerald-500"></div>
                    )}
                  </>
                )}
              </>
            )}
          </NavLink>
        ))}
      </nav>

      {/* ── Profil Alanı ── */}
      <div className="p-4 border-t border-slate-100 mt-auto">
        <div className={`flex items-center ${collapsed ? 'justify-center' : 'justify-between px-2'} py-2`}>
          <div className={`flex items-center ${collapsed ? '' : 'gap-3'}`}>
            <div className="h-10 w-10 shrink-0 rounded-full bg-emerald-400 flex items-center justify-center text-white font-bold text-sm shadow-sm">
              K
            </div>
            {!collapsed && (
              <div className="flex flex-col overflow-hidden whitespace-nowrap">
                <span className="text-[15px] font-bold text-slate-800 leading-tight">Kullanıcı</span>
                <span className="text-[13px] font-medium text-slate-400">Premium Üye</span>
              </div>
            )}
          </div>
          {!collapsed && (
            <button className="text-slate-400 hover:text-slate-600 transition-colors p-1">
              <svg className="w-5 h-5" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4"></path><polyline points="16 17 21 12 16 7"></polyline><line x1="21" y1="12" x2="9" y2="12"></line></svg>
            </button>
          )}
        </div>
      </div>
    </aside>
  )
}

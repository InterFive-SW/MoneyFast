/**
 * Sidebar — Dashboard Kenar Çubuğu Bileşeni (v2)
 */

import { useState }             from 'react'
import { NavLink, useNavigate } from 'react-router-dom'
import type { ReactNode }       from 'react'
import { useUser }              from '../../contexts/UserContext'
import logoInline               from '../../assets/logo-inline.png'

// ─── Navigasyon Veri Yapısı ───────────────────────────────────────────────────

interface NavItem {
  to:     string
  label:  string
  icon:   ReactNode
  end?:   boolean
}

// ─── Inline SVG İkon Bileşenleri ─────────────────────────────────────────────

interface IconProps { className?: string }

function IconDashboard({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="3" y="3" width="7" height="9"></rect>
      <rect x="14" y="3" width="7" height="5"></rect>
      <rect x="14" y="12" width="7" height="9"></rect>
      <rect x="3" y="16" width="7" height="5"></rect>
    </svg>
  )
}

function IconPortfolio({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21.21 15.89A10 10 0 1 1 8 2.83"></path>
      <path d="M22 12A10 10 0 0 0 12 2v10z"></path>
    </svg>
  )
}

function IconMarkets({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <polyline points="22 7 13.5 15.5 8.5 10.5 2 17"></polyline>
      <polyline points="16 7 22 7 22 13"></polyline>
    </svg>
  )
}

function IconBanking({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <rect x="1" y="4" width="22" height="16" rx="2" ry="2"></rect>
      <line x1="1" y1="10" x2="23" y2="10"></line>
    </svg>
  )
}

function IconChat({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z"></path>
    </svg>
  )
}

function IconLogout({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <path d="M9 21H5a2 2 0 0 1-2-2V5a2 2 0 0 1 2-2h4" />
      <polyline points="16 17 21 12 16 7" />
      <line x1="21" y1="12" x2="9" y2="12" />
    </svg>
  )
}

function IconSettings({ className }: IconProps) {
  return (
    <svg className={className} viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round" aria-hidden="true">
      <circle cx="12" cy="12" r="3" />
      <path d="M19.4 15a1.65 1.65 0 0 0 .33 1.82l.06.06a2 2 0 0 1 0 2.83 2 2 0 0 1-2.83 0l-.06-.06a1.65 1.65 0 0 0-1.82-.33 1.65 1.65 0 0 0-1 1.51V21a2 2 0 0 1-2 2 2 2 0 0 1-2-2v-.09A1.65 1.65 0 0 0 9 19.4a1.65 1.65 0 0 0-1.82.33l-.06.06a2 2 0 0 1-2.83 0 2 2 0 0 1 0-2.83l.06-.06a1.65 1.65 0 0 0 .33-1.82 1.65 1.65 0 0 0-1.51-1H3a2 2 0 0 1-2-2 2 2 0 0 1 2-2h.09A1.65 1.65 0 0 0 4.6 9a1.65 1.65 0 0 0-.33-1.82l-.06-.06a2 2 0 0 1 0-2.83 2 2 0 0 1 2.83 0l.06.06a1.65 1.65 0 0 0 1.82.33H9a1.65 1.65 0 0 0 1-1.51V3a2 2 0 0 1 2-2 2 2 0 0 1 2 2v.09a1.65 1.65 0 0 0 1 1.51 1.65 1.65 0 0 0 1.82-.33l.06-.06a2 2 0 0 1 2.83 0 2 2 0 0 1 0 2.83l-.06.06a1.65 1.65 0 0 0-.33 1.82V9a1.65 1.65 0 0 0 1.51 1H21a2 2 0 0 1 2 2 2 2 0 0 1-2 2h-.09a1.65 1.65 0 0 0-1.51 1z" />
    </svg>
  )
}

/** Portföy analizi — pasta grafiği çağrıştıran ikon */
function IconAnalytics({ className }: IconProps) {
  return (
    <svg
      className={className}
      viewBox="0 0 24 24"
      fill="none"
      stroke="currentColor"
      strokeWidth="2"
      strokeLinecap="round"
      strokeLinejoin="round"
      aria-hidden="true"
    >
      <path d="M21.21 15.89A10 10 0 1 1 8 2.83" />
      <path d="M22 12A10 10 0 0 0 12 2v10z" />
    </svg>
  )
}

// ─── Navigasyon Yapılandırması ────────────────────────────────────────────────

const NAV_ITEMS: NavItem[] = [
  { to: '/dashboard',  label: 'Genel Bakış',        icon: <IconDashboard  className="h-[18px] w-[18px] shrink-0" />, end: true },
  { to: '/banking',    label: 'Banka İşlemleri',    icon: <IconBanking    className="h-[18px] w-[18px] shrink-0" /> },
  { to: '/portfolio',  label: 'Portföyüm',          icon: <IconPortfolio  className="h-[18px] w-[18px] shrink-0" /> },
  { to: '/analiz',     label: 'Analiz',             icon: <IconAnalytics  className="h-[18px] w-[18px] shrink-0" /> },
  { to: '/investment', label: 'Piyasalar',          icon: <IconMarkets    className="h-[18px] w-[18px] shrink-0" /> },
  { to: '/chat',       label: 'Yapay Zeka Asistan', icon: <IconChat       className="h-[18px] w-[18px] shrink-0" /> },
  { to: '/settings',   label: 'Ayarlar',            icon: <IconSettings   className="h-[18px] w-[18px] shrink-0" /> },
]

// ─── Navigasyon Öğesi Alt Bileşeni ────────────────────────────────────────────

interface NavItemProps {
  item:        NavItem
  isCollapsed: boolean
}

/**
 * Tekil navigasyon satırı — daraltılmış modda ikon + CSS tooltip,
 * genişletilmiş modda ikon + etiket gösterir.
 */
function SidebarNavItem({ item, isCollapsed }: NavItemProps) {
  return (
    <li className="relative">
      <NavLink
        to={item.to}
        end={item.end}
        className={({ isActive }) =>
          `group flex items-center gap-3.5 rounded-2xl px-4 py-3 text-[15px] transition-all duration-200 ${
            isActive
              ? 'bg-white/10 text-white font-semibold border border-white/10'
              : 'text-slate-400 font-medium hover:bg-white/5 hover:text-slate-200 border border-transparent'
          }`
        }
      >
        {({ isActive }) => (
          <>
            {/* Navigasyon ikonu */}
            <span className={`transition-colors duration-200 ${isActive ? 'text-brandBlue' : 'text-slate-400 group-hover:text-slate-200'}`}>
              {item.icon}
            </span>

            {/* Etiket — daraltılmış modda gizlenir */}
            <span
              className={`whitespace-nowrap overflow-hidden transition-all duration-300 ${
                isCollapsed ? 'w-0 opacity-0' : 'w-auto opacity-100'
              }`}
            >
              {item.label}
            </span>

            {/* Aktif gösterge noktası */}
            {isActive && !isCollapsed && (
              <span className="absolute right-4 h-1.5 w-1.5 shrink-0 rounded-full bg-brandBlue" aria-hidden="true" />
            )}
          </>
        )}
      </NavLink>

      {/* CSS Tooltip — yalnızca daraltılmış modda görünür */}
      {isCollapsed && (
        <div
          role="tooltip"
          className="pointer-events-none absolute left-full top-1/2 z-50 ml-3 -translate-y-1/2 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg transition-opacity duration-150 group-hover:opacity-100 [li:hover_&]:opacity-100"
        >
          {item.label}
          {/* Tooltip ok */}
          <span className="absolute right-full top-1/2 -translate-y-1/2 border-4 border-transparent border-r-slate-900" />
        </div>
      )}
    </li>
  )
}

// ─── Ana Bileşen ──────────────────────────────────────────────────────────────

/**
 * Dashboard Kenar Çubuğu (v2 Cosmos.so Style)
 *
 * `isCollapsed=false` → 256px, ikon + etiket
 * `isCollapsed=true`  → 80px, yalnızca ikon + hover tooltip
 */
export default function Sidebar() {
  const navigate                    = useNavigate()
  const [isCollapsed, setCollapsed] = useState(true)
  const { profile, isLoading }      = useUser()

  /** Oturumu sonlandırır: token silinir, giriş sayfasına yönlendirilir */
  function handleLogout() {
    localStorage.removeItem('access_token')
    localStorage.removeItem('refresh_token')
    navigate('/login')
  }

  return (
    <aside
      onMouseEnter={() => setCollapsed(false)}
      onMouseLeave={() => setCollapsed(true)}
      className={`relative flex h-screen shrink-0 flex-col border-r border-white/10 bg-slate-950/80 backdrop-blur-xl shadow-sm transition-all duration-300 ease-in-out z-50 ${
        isCollapsed ? 'w-[80px]' : 'w-[256px]'
      }`}
    >
      {/* ── Marka / Logo Alanı ───────────────────────────────────────── */}
      <div className={`flex items-center py-8 ${isCollapsed ? 'justify-center px-0' : 'px-6 gap-3'}`}>
        <img 
          src={logoInline} 
          alt="MoneyFast Logo" 
          className="h-12 w-12 transition-all duration-300 object-contain shrink-0" 
        />
        
        {/* Uygulama adı — daraltılmış modda gizlenir */}
        <div
          className={`overflow-hidden whitespace-nowrap transition-all duration-300 ${
            isCollapsed ? 'w-0 opacity-0' : 'w-auto opacity-100'
          }`}
        >
          <p className="text-xl font-bold leading-tight tracking-tight text-white">
            MoneyFast
          </p>
        </div>
      </div>

      {/* ── Birincil Navigasyon ──────────────────────────────────────── */}
      <nav
        className="flex-1 overflow-y-auto overflow-x-hidden px-4 py-2"
        aria-label="Ana uygulama navigasyonu"
      >
        {/* Bölüm başlığı — daraltılmış modda gizlenir */}
        <p
          className={`mb-3 px-3 text-[11px] font-bold uppercase tracking-wider text-slate-400 overflow-hidden whitespace-nowrap transition-all duration-300 ${
            isCollapsed ? 'opacity-0 h-0 mb-0' : 'opacity-100 h-auto'
          }`}
        >
          Ana Menü
        </p>

        <ul className="space-y-1.5" role="list">
          {NAV_ITEMS.map((item) => (
            <SidebarNavItem key={item.to} item={item} isCollapsed={isCollapsed} />
          ))}
        </ul>
      </nav>

      {/* ── Kullanıcı Bilgisi ve Oturum Kapatma ─────────────────────── */}
      <div className="shrink-0 border-t border-white/10 p-4">
        <div className={`flex items-center py-2 ${isCollapsed ? 'justify-center' : 'justify-between px-2'}`}>
          <div className={`flex items-center ${isCollapsed ? '' : 'gap-3'}`}>
            {isLoading ? (
              <div className="h-10 w-10 shrink-0 animate-pulse rounded-full bg-slate-800" />
            ) : (
              <div
                className="flex h-10 w-10 shrink-0 items-center justify-center rounded-full bg-gradient-to-br from-brandBlue to-primary-500 text-[14px] font-bold text-white shadow-sm"
                aria-hidden="true"
              >
                {profile?.initials ?? 'K'}
              </div>
            )}

            {/* Kullanıcı adı ve üyelik seviyesi — daraltılmış modda gizlenir */}
            <div
              className={`overflow-hidden whitespace-nowrap transition-all duration-300 ${
                isCollapsed ? 'w-0 opacity-0' : 'w-auto opacity-100'
              }`}
            >
              {isLoading ? (
                <div className="space-y-1">
                  <div className="h-2.5 w-16 animate-pulse rounded bg-slate-800" />
                  <div className="h-2 w-10 animate-pulse rounded bg-slate-800/50" />
                </div>
              ) : (
                <>
                  <p className="text-[15px] font-bold leading-tight text-white">
                    {profile?.fullName ?? 'Kullanıcı'}
                  </p>
                  <p className="text-[13px] font-medium text-slate-400">Premium Üye</p>
                </>
              )}
            </div>
          </div>

          {/* Oturum kapatma — daraltılmış modda gizlenir */}
          {!isCollapsed && (
            <button
              type="button"
              onClick={handleLogout}
              aria-label="Oturumu kapat"
              title="Oturumu Kapat"
              className="p-1 text-slate-400 transition-colors hover:text-white"
            >
              <IconLogout className="h-5 w-5" />
            </button>
          )}
        </div>
      </div>
    </aside>
  )
}

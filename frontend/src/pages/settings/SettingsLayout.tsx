import { NavLink, Outlet } from 'react-router-dom'
import { SettingsErrorBoundary } from './SettingsErrorBoundary'

/**
 * SettingsLayout — Ayarlar Modülü Ana Kapsayıcı Şablonu
 *
 * MİMARİ KARAR:
 * Uygulamanın kesin kuralları gereği (state-based routing yasağı),
 * bu bileşen React Router'ın nested routing (iç içe rotalama) mimarisine
 * tam uyumlu şekilde tasarlanmıştır. Navigasyon için `NavLink`, alt
 * rotaları render etmek için ise `<Outlet />` kullanılmaktadır.
 *
 * TASARIM KARARI:
 * Tasarım, projenin geri kalanıyla (Premium Dark Mode & Glassmorphism)
 * %100 uyumlu olacak şekilde `bg-slate-900/50`, `backdrop-blur-xl`,
 * `border-white/10` sınıfları etrafında inşa edilmiştir.
 */
export default function SettingsLayout() {
  const tabs = [
    { name: 'Profil & Kimlik', path: '/settings/profile' },
    { name: 'Güvenlik', path: '/settings/security' },
    { name: 'Bildirimler', path: '/settings/notifications' },
    { name: 'Görünüm', path: '/settings/appearance' },
    { name: 'Gizlilik & Veri', path: '/settings/privacy' },
  ]

  return (
    <div className="p-6 sm:p-8 min-h-screen max-w-7xl mx-auto">
      {/* ── Üst Başlık ve Açıklama ────────────────────────────────────────── */}
      <div className="mb-8">
        <h2 className="text-2xl font-bold tracking-tight text-white">Ayarlar</h2>
        <p className="mt-1 text-sm text-slate-400">
          Hesap bilgilerinizi, güvenlik tercihlerinizi ve sistem ayarlarınızı buradan yönetin.
        </p>
      </div>

      <div className="flex flex-col lg:flex-row gap-8">
        {/* ── Sol Menü (Navigasyon) ─────────────────────────────────────────── */}
        <div className="w-full lg:w-64 flex-shrink-0">
          <div className="rounded-2xl bg-slate-900/50 p-2 backdrop-blur-xl border border-white/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.2)]">
            <nav className="flex lg:flex-col gap-1 overflow-x-auto lg:overflow-x-visible pb-2 lg:pb-0 scrollbar-hide">
              {tabs.map((tab) => (
                <NavLink
                  key={tab.path}
                  to={tab.path}
                  className={({ isActive }) =>
                    `whitespace-nowrap text-left px-4 py-3 rounded-xl text-sm font-medium transition-all ${
                      isActive
                        ? 'bg-brandBlue text-white shadow-sm shadow-brandBlue/30'
                        : 'text-slate-400 hover:text-white hover:bg-white/5'
                    }`
                  }
                >
                  {tab.name}
                </NavLink>
              ))}
            </nav>
          </div>
        </div>

        {/* ── Sağ İçerik Alanı (Alt Rotalar) ────────────────────────────────── */}
        <div className="flex-1">
          <div className="rounded-2xl bg-slate-900/50 p-6 sm:p-8 backdrop-blur-xl border border-white/10 shadow-[0_4px_24px_-8px_rgba(0,0,0,0.2)]">
            {/* React Router bu bileşenin içine aktif alt rotayı (örn. ProfileSettings) monte edecektir */}
            <SettingsErrorBoundary>
              <Outlet />
            </SettingsErrorBoundary>
          </div>
        </div>
      </div>
    </div>
  )
}

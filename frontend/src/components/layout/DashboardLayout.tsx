/**
 * DashboardLayout — Oturum Gerektiren Sayfa Düzeni (v2)
 *
 * Önceki versiyona kıyasla yapılan değişiklikler:
 *  - Global AI Asistan FAB (Floating Action Button) eklendi
 *  - Atmosferik arka plan orb sayısı optimize edildi
 */

import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header  from './Header'

// ─── Rota → Sayfa Başlığı Eşleme Tablosu ─────────────────────────────────────

/**
 * Aktif pathname'i kullanıcı dostu Türkçe sayfa başlığına dönüştürür.
 * Yeni korumalı rota eklendiğinde bu tabloya da kayıt eklenmeli,
 * böylece Header doğru başlığı görüntüleyebilir.
 */
const ROUTE_TITLE_MAP: Record<string, string> = {
  '/dashboard':  'Gösterge Paneli',
  '/banking':    'Cüzdan & İşlemler',
  '/investment': 'Yatırımlar',
  '/chat':       'AI Finansal Asistan',
  '/risk':       'Risk Analizi',
  '/portfolio':  'Portföy',
}

const FALLBACK_TITLE = 'MoneyFast'

// ─── AI Asistan FAB Alt Bileşeni ──────────────────────────────────────────────

/**
 * Global AI Asistan Kayan Eylem Butonu (Floating Action Button)
 *
 * Ekranın sağ alt köşesine sabit konumlanmış; tüm sayfalardan
 * AI Asistan'a tek tıklamayla erişim sağlar.
 *
 * Tasarım özellikleri:
 *  - Zümrüt yeşili dolgu + emerald gölge (parlama efekti)
 *  - Hover'da `scale(1.05)` büyüme
 *  - Dış halka `ring-4 ring-emerald-500/20` ile derinlik hissi
 */
function AIAssistantFAB() {
  const navigate      = useNavigate()
  const location      = useLocation()
  const isOnChatPage  = location.pathname === '/chat'

  // Chat sayfasında zaten bulunuluyorsa FAB gösterilmez
  if (isOnChatPage) return null

  return (
    <button
      type="button"
      onClick={() => navigate('/chat')}
      aria-label="AI Finansal Asistan'ı aç"
      title="AI Finansal Asistan"
      className="fixed bottom-8 right-8 z-50 flex h-14 w-14 items-center justify-center rounded-full bg-emerald-500 text-white shadow-lg shadow-emerald-500/40 ring-4 ring-emerald-500/20 transition-all duration-200 hover:scale-105 hover:bg-emerald-600 hover:shadow-emerald-500/50 focus:outline-none focus:ring-4 focus:ring-emerald-400/50"
    >
      {/* AI Asistan sohbet balonu ikonu */}
      <svg
        width="22"
        height="22"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M21 15a2 2 0 0 1-2 2H7l-4 4V5a2 2 0 0 1 2-2h14a2 2 0 0 1 2 2z" />
        <line x1="9" y1="10" x2="15" y2="10" />
        <line x1="9" y1="14" x2="13" y2="14" />
      </svg>
    </button>
  )
}

// ─── Ana Bileşen ──────────────────────────────────────────────────────────────

/**
 * Dashboard Temel Düzen Bileşeni (v2)
 *
 * Auth sayfalarıyla birebir aynı renk paletini ve atmosferik
 * arka plan efektlerini kullanarak tema bütünlüğü sağlar.
 * FAB butonu, Outlet içeriğinin üzerine z-50 ile konumlanır.
 */
export default function DashboardLayout() {
  const location  = useLocation()
  const pageTitle = ROUTE_TITLE_MAP[location.pathname] ?? FALLBACK_TITLE

  return (
    <div className="relative flex h-screen overflow-hidden bg-gradient-to-br from-slate-50 via-white to-emerald-50/40">

      {/* ── Atmosferik Arka Plan Orb'ları ───────────────────────────── */}
      <div
        className="pointer-events-none absolute -left-40 -top-40 h-96 w-96 rounded-full bg-emerald-200/25 blur-3xl"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute -bottom-40 -right-40 h-96 w-96 rounded-full bg-teal-200/20 blur-3xl"
        aria-hidden="true"
      />
      <div
        className="pointer-events-none absolute left-1/2 top-1/3 h-72 w-72 -translate-x-1/2 rounded-full bg-emerald-100/15 blur-3xl"
        aria-hidden="true"
      />

      {/* ── Kenar Çubuğu ─────────────────────────────────────────────── */}
      <Sidebar />

      {/* ── İçerik Sütunu ────────────────────────────────────────────── */}
      <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
        <Header pageTitle={pageTitle} />

        <main className="flex-1 overflow-y-auto" id="main-content">
          <Outlet />
        </main>
      </div>

      {/* ── Global AI Asistan FAB ─────────────────────────────────────── */}
      <AIAssistantFAB />
    </div>
  )
}

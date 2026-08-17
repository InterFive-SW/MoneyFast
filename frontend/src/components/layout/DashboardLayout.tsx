/**
 * DashboardLayout — Oturum Gerektiren Sayfa Düzeni (v2)
 *
 * Önceki versiyona kıyasla yapılan değişiklikler:
 *  - Global AI Asistan FAB (Floating Action Button) eklendi
 *  - Atmosferik arka plan orb sayısı optimize edildi
 *  - ChatProvider ve ChatPopup entegrasyonu eklendi
 */

import React, { useState } from 'react'
import { Outlet, useLocation, useNavigate } from 'react-router-dom'
import Sidebar from './Sidebar'
import Header  from './Header'
import { ChatProvider } from '../../context/ChatContext'
import ChatPopup from '../chat/ChatPopup'

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

interface AIAssistantFABProps {
  onTogglePopup: () => void;
  isOpen: boolean;
}

/**
 * Global AI Asistan Kayan Eylem Butonu (Floating Action Button)
 *
 * Ekranın sağ alt köşesine sabit konumlanmış; tüm sayfalardan
 * AI Asistan'a tek tıklamayla erişim sağlar.
 * Cosmos.so ferahlığında, premium glassmorphism tasarımı.
 */
function AIAssistantFAB({ onTogglePopup, isOpen }: AIAssistantFABProps) {
  const location      = useLocation()
  const isOnChatPage  = location.pathname === '/chat'

  // Chat sayfasında zaten bulunuluyorsa FAB gösterilmez
  if (isOnChatPage) return null

  return (
    <button
      type="button"
      onClick={onTogglePopup}
      aria-label="AI Finansal Asistan'ı aç"
      title="AI Finansal Asistan"
      className={`fixed bottom-8 right-6 md:right-10 z-50 flex items-center justify-center gap-2 rounded-full px-5 py-3.5 shadow-2xl transition-all duration-300 hover:scale-105 hover:-translate-y-1 focus:outline-none overflow-hidden group ${
        isOpen 
          ? 'bg-slate-800 text-white shadow-slate-900/20 ring-1 ring-white/10' 
          : 'bg-white/70 backdrop-blur-md text-emerald-700 shadow-emerald-500/10 ring-1 ring-emerald-500/20 hover:bg-white/90 hover:shadow-emerald-500/20'
      }`}
    >
      {/* Arka plan parlaması (Kapalıyken) */}
      {!isOpen && (
        <div className="absolute inset-0 rounded-full bg-gradient-to-tr from-emerald-100/50 to-teal-50/50 opacity-0 transition-opacity duration-300 group-hover:opacity-100" />
      )}
      
      <div className="relative flex items-center gap-2">
        {isOpen ? (
          <svg className="w-5 h-5" fill="none" viewBox="0 0 24 24" stroke="currentColor">
            <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
          </svg>
        ) : (
          <svg
            className="w-5 h-5 text-emerald-500"
            fill="none"
            viewBox="0 0 24 24"
            stroke="currentColor"
          >
            <path
              strokeLinecap="round"
              strokeLinejoin="round"
              strokeWidth={2}
              d="M13 10V3L4 14h7v7l9-11h-7z"
            />
          </svg>
        )}
        
        {!isOpen && (
          <span className="text-sm font-semibold tracking-wide bg-gradient-to-r from-emerald-600 to-teal-600 bg-clip-text text-transparent">
            Yapay Zeka
          </span>
        )}
      </div>
    </button>
  )
}

// ─── Ana Bileşen ──────────────────────────────────────────────────────────────

/**
 * Dashboard Temel Düzen Bileşeni (v2)
 */
export default function DashboardLayout() {
  const location  = useLocation()
  const pageTitle = ROUTE_TITLE_MAP[location.pathname] ?? FALLBACK_TITLE
  const [isChatPopupOpen, setIsChatPopupOpen] = useState(false);

  // Chat sayfasına gidilirse popup'ı kapat
  React.useEffect(() => {
    if (location.pathname === '/chat') {
      setIsChatPopupOpen(false);
    }
  }, [location.pathname]);

  return (
    <ChatProvider>
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

        {/* ── Global AI Asistan FAB & Popup ────────────────────────────── */}
        <AIAssistantFAB isOpen={isChatPopupOpen} onTogglePopup={() => setIsChatPopupOpen(!isChatPopupOpen)} />
        <ChatPopup isOpen={isChatPopupOpen} onClose={() => setIsChatPopupOpen(false)} />
      </div>
    </ChatProvider>
  )
}

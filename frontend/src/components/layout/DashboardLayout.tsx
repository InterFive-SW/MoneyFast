/**
 * DashboardLayout — Oturum Gerektiren Sayfa Düzeni (v2)
 *
 * Önceki versiyona kıyasla yapılan değişiklikler:
 *  - Global AI Asistan FAB (Floating Action Button) eklendi
 *  - Atmosferik arka plan orb sayısı optimize edildi
 *  - ChatProvider ve ChatPopup entegrasyonu eklendi
 */

import React, { useState } from 'react'
import { titleFor } from '../../lib/routeTitle'
import { Outlet, useLocation } from 'react-router-dom'
import ErrorBoundary from '../ErrorBoundary'
import Sidebar from './Sidebar'
import Header  from './Header'
import SuitabilityBanner from '../risk/SuitabilityBanner'
import { ChatProvider } from '../../context/ChatContext'
import ChatPopup from '../chat/ChatPopup'

// ─── Rota → Sayfa Başlığı Eşleme Tablosu ─────────────────────────────────────

/**
 * Aktif pathname'i kullanıcı dostu Türkçe sayfa başlığına dönüştürür.
 * Yeni korumalı rota eklendiğinde bu tabloya da kayıt eklenmeli,
 * böylece Header doğru başlığı görüntüleyebilir.
 */
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
      onClick={onTogglePopup}
      aria-label={isOpen ? "AI Finansal Asistan'ı kapat" : "AI Finansal Asistan'ı aç"}
      aria-expanded={isOpen}
      title="AI Finansal Asistan"
      className={`group fixed bottom-6 right-6 z-40 flex h-14 w-14 items-center justify-center rounded-full shadow-2xl transition-all duration-300 hover:scale-105 focus:outline-none focus-visible:ring-2 focus-visible:ring-brandBlue focus-visible:ring-offset-2 focus-visible:ring-offset-slate-950 ${
        isOpen
          ? 'bg-slate-800 text-white ring-1 ring-white/10'
          : 'bg-brandBlue text-white shadow-[0_0_24px_rgba(75,123,229,0.45)] ring-1 ring-white/10 hover:shadow-[0_0_32px_rgba(75,123,229,0.65)]'
      }`}
    >
      {isOpen ? (
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M6 18L18 6M6 6l12 12" />
        </svg>
      ) : (
        <svg className="h-6 w-6" fill="none" viewBox="0 0 24 24" stroke="currentColor" aria-hidden="true">
          <path strokeLinecap="round" strokeLinejoin="round" strokeWidth={2} d="M13 10V3L4 14h7v7l9-11h-7z" />
        </svg>
      )}

      {/* Ad, butonun kapladığı alanı büyütmeden yalnızca üzerine gelindiğinde
          görünür: etiketi hep taşımak, balonu sağ alt köşedeki işlevsel
          düğmelerin üstüne oturacak kadar genişletiyordu. */}
      {!isOpen && (
        <span
          className="pointer-events-none absolute right-full mr-3 whitespace-nowrap rounded-lg bg-slate-900 px-2.5 py-1.5 text-xs font-medium text-white opacity-0 shadow-lg ring-1 ring-white/10 transition-opacity duration-200 group-hover:opacity-100"
          role="tooltip"
        >
          Yapay Zeka
        </span>
      )}
    </button>
  )
}

// ─── Ana Bileşen ──────────────────────────────────────────────────────────────

/**
 * Dashboard Temel Düzen Bileşeni (v2)
 */
export default function DashboardLayout() {
  const location  = useLocation()
  const pageTitle = titleFor(location.pathname)
  const [isChatPopupOpen, setIsChatPopupOpen] = useState(false);

  // Balonun gösterildiği tek koşul; hem FAB hem de alt dolgu bunu okuyor,
  // böylece ikisi ayrışamaz.
  const showAssistantBubble = location.pathname !== '/chat';

  // Chat sayfasına gidilirse popup'ı kapat
  React.useEffect(() => {
    if (location.pathname === '/chat') {
      setIsChatPopupOpen(false);
    }
  }, [location.pathname]);

  return (
    <ChatProvider>
      <div className="relative flex h-screen overflow-hidden bg-hologram-global font-sans text-slate-300 selection:bg-brandBlue selection:text-white">

        {/* ── Kenar Çubuğu ─────────────────────────────────────────────── */}
        <Sidebar />

        {/* ── İçerik Sütunu ────────────────────────────────────────────── */}
        <div className="flex min-w-0 flex-1 flex-col overflow-hidden">
          <Header pageTitle={pageTitle} />

          {/* Uygunluk testi daveti. Header'ın ALTINDA ve içeriğin üstünde:
              her sayfada görünmesi gerekiyor ama hiçbirini engellememeli. */}
          <SuitabilityBanner />

          {/* Alt boşluk YALNIZCA balon görünürken.

              Boşluk, sayfanın son satırının yüzen asistan balonunun altında
              kalmaması için var. Sohbet sayfasında balon zaten gizleniyor ve
              o sayfa `h-full`; dolayısıyla orada bu dolgu bir şeyin altından
              çıkmasını sağlamıyor, sayfayı 6rem erken bitiriyordu. */}
          <main
            className={`flex-1 overflow-y-auto ${showAssistantBubble ? 'pb-24' : ''}`}
            id="main-content"
          >
            {/* Sayfa çökerse sidebar ve header ayakta kalsın; kullanıcı
                boş beyaz ekranda kalmak yerine başka bir sayfaya geçebilsin. */}
            <ErrorBoundary label="Sayfa">
              <Outlet />
            </ErrorBoundary>
          </main>
        </div>

        {/* ── Global AI Asistan FAB & Popup ────────────────────────────── */}
        <AIAssistantFAB isOpen={isChatPopupOpen} onTogglePopup={() => setIsChatPopupOpen(!isChatPopupOpen)} />
        <ChatPopup isOpen={isChatPopupOpen} onClose={() => setIsChatPopupOpen(false)} />
      </div>
    </ChatProvider>
  )
}

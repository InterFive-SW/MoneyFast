/**
 * Header — Dashboard Üst Çubuğu Bileşeni (v2)
 *
 * Önceki versiyona kıyasla yapılan değişiklikler:
 *  - Hardcoded "Arda Kaya" kaldırıldı
 *  - UserContext üzerinden dinamik kullanıcı adı ve baş harfler alınıyor
 *  - Profil yüklenirken iskelet (skeleton) gösterimi eklendi
 */

import { useState, useEffect } from 'react'
import { useUser }             from '../../contexts/UserContext'

interface HeaderProps {
  /**
   * Aktif route'a karşılık gelen sayfa başlığı.
   * `DashboardLayout.tsx` içindeki rota-başlık eşleme tablosundan türetilir.
   */
  pageTitle: string
}

// ─── Tarih Biçimlendirme ──────────────────────────────────────────────────────

/**
 * Geçerli tarihi Türkçe uzun formatta biçimlendirir.
 * Örnek: "Perşembe, 14 Ağustos 2026"
 */
function getFormattedDate(): string {
  return new Date().toLocaleDateString('tr-TR', {
    weekday: 'long',
    day:     'numeric',
    month:   'long',
    year:    'numeric',
  })
}

// ─── Bildirim Butonu Alt Bileşeni ─────────────────────────────────────────────

function NotificationButton() {
  const [isOpen, setIsOpen] = useState(false)

  return (
    <div className="relative">
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Bildirimleri görüntüle"
        className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-slate-900/50 text-slate-400 shadow-sm backdrop-blur-sm transition hover:border-white/20 hover:bg-white/10 hover:text-white"
      >
        <svg width="16" height="16" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round">
          <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
          <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
        </svg>
        <span className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-brandBlue ring-2 ring-slate-950" />
      </button>

      {/* Tıklanınca açılacak menü */}
      {isOpen && (
        <div className="absolute right-0 mt-2 w-72 rounded-xl border border-white/10 bg-slate-900 p-4 shadow-xl backdrop-blur-md z-50">
          <h3 className="mb-3 text-sm font-semibold text-white border-b border-white/10 pb-2">Bildirimler</h3>
          <div className="flex flex-col gap-3">
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-brandBlue">Sistem</span>
              <span className="text-sm text-slate-300">MoneyFast'e hoş geldiniz! Piyasa verileri canlı akışa geçti.</span>
            </div>
            <div className="flex flex-col gap-1">
              <span className="text-xs font-medium text-emerald-400">Portföy</span>
              <span className="text-sm text-slate-300">Sektörel dağılım grafikleriniz güncellendi.</span>
            </div>
          </div>
        </div>
      )}
    </div>
  )
}



/**
 * Bildirim zili ikonu — okunmamış bildirim rozeti içerir.
 * Gerçek bildirim sayısı ilerideki bildirim modülü entegrasyonuyla bağlanacaktır.
 */
// function NotificationButton() {
//   return (
//     <button
//       type="button"
//       aria-label="Bildirimleri görüntüle"
//       className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-white/10 bg-slate-900/50 text-slate-400 shadow-sm backdrop-blur-sm transition hover:border-white/20 hover:bg-white/10 hover:text-white"
//     >
//       <svg
//         width="16"
//         height="16"
//         viewBox="0 0 24 24"
//         fill="none"
//         stroke="currentColor"
//         strokeWidth="2"
//         strokeLinecap="round"
//         strokeLinejoin="round"
//         aria-hidden="true"
//       >
//         <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
//         <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
//       </svg>
//       <span
//         className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-brandBlue ring-2 ring-slate-950"
//         aria-label="Okunmamış bildirim mevcut"
//       />
//     </button>
//   )
// }

// ─── Ana Bileşen ──────────────────────────────────────────────────────────────

/**
 * Dashboard Üst Çubuğu
 *
 * İçerik düzeni:
 *  - Sol: Sayfa başlığı + güncel Türkçe tarih
 *  - Sağ: Bildirim butonu + dinamik kullanıcı kimlik kartı
 */
export default function Header({ pageTitle }: HeaderProps) {
  const [dateStr, setDateStr] = useState<string>(getFormattedDate)
  const { profile, isLoading } = useUser()

  /**
   * Gece yarısı geçişinde tarih etiketini otomatik olarak günceller.
   * Bir sonraki gece yarısına kalan süre hesaplanarak tek bir setTimeout kurulur.
   */
  useEffect(() => {
    const now          = new Date()
    const tomorrow     = new Date(now.getFullYear(), now.getMonth(), now.getDate() + 1)
    const msToMidnight = tomorrow.getTime() - now.getTime()

    const timer = setTimeout(() => setDateStr(getFormattedDate()), msToMidnight)
    return () => clearTimeout(timer)
  }, [dateStr])

  return (
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-white/10 bg-slate-950/80 px-6 backdrop-blur-xl sm:px-8">

      {/* ── Sol: Sayfa Başlığı ve Tarih ──────────────────────────────── */}
      <div>
        <h1 className="text-base font-bold leading-none text-white">{pageTitle}</h1>
        <p className="mt-1 text-xs capitalize text-slate-400">{dateStr}</p>
      </div>

      {/* ── Sağ: Aksiyon Grubu ───────────────────────────────────────── */}
      <div className="flex items-center gap-2.5">
        <NotificationButton />

        {/* Kullanıcı kimlik kartı */}
        <div className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-slate-900/50 px-3 py-1.5 shadow-sm backdrop-blur-sm">

          {/* Gradient avatar — baş harfler veya iskelet */}
          {isLoading ? (
            <div className="h-6 w-6 animate-pulse rounded-lg bg-slate-800" />
          ) : (
            <div
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-brandBlue to-primary-500 text-[10px] font-bold text-white"
              aria-hidden="true"
            >
              {profile?.initials ?? 'KL'}
            </div>
          )}

          {/* Kullanıcı adı ve üyelik seviyesi */}
          <div className="hidden sm:block">
            {isLoading ? (
              <div className="space-y-1">
                <div className="h-2.5 w-20 animate-pulse rounded bg-slate-800" />
                <div className="h-2 w-14 animate-pulse rounded bg-slate-800/50" />
              </div>
            ) : (
              <>
                <p className="text-xs font-semibold leading-none text-white">
                  {profile?.fullName ?? 'Kullanıcı'}
                </p>
                <p className="mt-0.5 text-[10px] text-slate-400">Premium Üye</p>
              </>
            )}
          </div>
        </div>
      </div>
    </header>
  )
}

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

/**
 * Bildirim zili ikonu — okunmamış bildirim rozeti içerir.
 * Gerçek bildirim sayısı ilerideki bildirim modülü entegrasyonuyla bağlanacaktır.
 */
function NotificationButton() {
  return (
    <button
      type="button"
      aria-label="Bildirimleri görüntüle"
      className="relative flex h-9 w-9 items-center justify-center rounded-xl border border-slate-200/80 bg-white/80 text-slate-500 shadow-sm backdrop-blur-sm transition hover:border-slate-300 hover:bg-white hover:text-slate-700"
    >
      <svg
        width="16"
        height="16"
        viewBox="0 0 24 24"
        fill="none"
        stroke="currentColor"
        strokeWidth="2"
        strokeLinecap="round"
        strokeLinejoin="round"
        aria-hidden="true"
      >
        <path d="M6 8a6 6 0 0 1 12 0c0 7 3 9 3 9H3s3-2 3-9" />
        <path d="M10.3 21a1.94 1.94 0 0 0 3.4 0" />
      </svg>
      <span
        className="absolute right-1.5 top-1.5 h-2 w-2 rounded-full bg-emerald-500 ring-2 ring-white"
        aria-label="Okunmamış bildirim mevcut"
      />
    </button>
  )
}

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
    <header className="sticky top-0 z-20 flex h-16 items-center justify-between border-b border-slate-200/60 bg-white/70 px-6 backdrop-blur-xl sm:px-8">

      {/* ── Sol: Sayfa Başlığı ve Tarih ──────────────────────────────── */}
      <div>
        <h1 className="text-base font-bold leading-none text-slate-950">{pageTitle}</h1>
        <p className="mt-1 text-xs capitalize text-slate-400">{dateStr}</p>
      </div>

      {/* ── Sağ: Aksiyon Grubu ───────────────────────────────────────── */}
      <div className="flex items-center gap-2.5">
        <NotificationButton />

        {/* Kullanıcı kimlik kartı */}
        <div className="flex items-center gap-2.5 rounded-xl border border-slate-200/80 bg-white/80 px-3 py-1.5 shadow-sm backdrop-blur-sm">

          {/* Gradient avatar — baş harfler veya iskelet */}
          {isLoading ? (
            <div className="h-6 w-6 animate-pulse rounded-lg bg-slate-200" />
          ) : (
            <div
              className="flex h-6 w-6 shrink-0 items-center justify-center rounded-lg bg-gradient-to-br from-emerald-400 to-teal-500 text-[10px] font-bold text-white"
              aria-hidden="true"
            >
              {profile?.initials ?? 'KL'}
            </div>
          )}

          {/* Kullanıcı adı ve üyelik seviyesi */}
          <div className="hidden sm:block">
            {isLoading ? (
              <div className="space-y-1">
                <div className="h-2.5 w-20 animate-pulse rounded bg-slate-200" />
                <div className="h-2 w-14 animate-pulse rounded bg-slate-100" />
              </div>
            ) : (
              <>
                <p className="text-xs font-semibold leading-none text-slate-800">
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

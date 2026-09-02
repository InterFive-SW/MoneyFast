/**
 * Header — Dashboard Üst Çubuğu Bileşeni (v2)
 *
 * Önceki versiyona kıyasla yapılan değişiklikler:
 *  - Hardcoded "Arda Kaya" kaldırıldı
 *  - UserContext üzerinden dinamik kullanıcı adı ve baş harfler alınıyor
 *  - Profil yüklenirken iskelet (skeleton) gösterimi eklendi
 */

import { useState, useEffect, useRef, useCallback } from 'react'
import { useNavigate } from 'react-router-dom'
import { api, Notification } from '../../api/client'
import { useUser }             from '../../contexts/UserContext'
import { formatLongDate, msUntilLocalMidnight } from '../../lib/datetime'

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
  return formatLongDate(new Date())
}

// ─── Bildirim Butonu Alt Bileşeni ─────────────────────────────────────────────

/**
 * Bildirim zili ikonu — okunmamış bildirim rozeti içerir.
 * REST polling mimarisi kullanılarak her 30 saniyede bir backend'den güncel bildirimler çekilir.
 * WebSocket yerine polling tercih edilmesinin nedeni; mevcut altyapıda socket sunucusunun
 * bulunmaması ve bildirimlerin zaman hassasiyetinin 30 saniyelik gecikmeyi tolere edebilmesidir.
 */
function NotificationButton() {
  const [isOpen, setIsOpen] = useState(false)
  const [notifications, setNotifications] = useState<Notification[]>([])
  const [unreadCount, setUnreadCount] = useState(0)
  const dropdownRef = useRef<HTMLDivElement>(null)
  const navigate = useNavigate()

  /**
   * Sunucudan güncel bildirim listesini çeker.
   * Performans maliyetini düşürmek adına limit=50 varsayımıyla çalışır.
   */
  const fetchNotifications = useCallback(async () => {
    try {
      const data = await api.getNotifications(50)
      setNotifications(data.items)
      setUnreadCount(data.unread_count)
    } catch (error) {
      console.error("Bildirimler alınırken bir hata oluştu:", error)
    }
  }, [])

  /**
   * Polling Mekanizması ve Event Listener Yönetimi (Memory Management)
   * 
   * 1. Sayfa yüklendiğinde bildirimleri hemen bir kez çeker.
   * 2. Ardından her 30 saniyede bir periyodik olarak aynı isteği tekrarlar.
   * 3. useEffect hook'unun cleanup fonksiyonunda `clearInterval` çağrılarak 
   *    kullanıcı sayfadan ayrıldığında (unmount) zamanlayıcı iptal edilir.
   *    Aksi takdirde, React state güncellemeleri çökmeye (memory leak) sebep olur.
   */
    useEffect(() => {
    fetchNotifications()
    const intervalId = setInterval(fetchNotifications, 30000)

    function handleClickOutside(event: MouseEvent) {
      if (dropdownRef.current && !dropdownRef.current.contains(event.target as Node)) {
        setIsOpen(false)
      }
    }
    document.addEventListener("mousedown", handleClickOutside)
    window.addEventListener("refreshNotifications", fetchNotifications)

    return () => {
      clearInterval(intervalId) // Memory leak önlemi
      document.removeEventListener("mousedown", handleClickOutside)
      window.removeEventListener("refreshNotifications", fetchNotifications)
    }
  }, [fetchNotifications])

  /**
   * Belirli bir bildirime tıklandığında asenkron olarak "okundu" işaretleme
   * API çağrısını başlatır (beklemeden UI güncellenir - Optimistic Update).
   * Varsa link üzerinden yönlendirme (routing) yapar ve menüyü kapatır.
   */
  const handleNotificationClick = async (n: Notification) => {
    setIsOpen(false)
    if (!n.is_read) {
      setUnreadCount(prev => Math.max(0, prev - 1))
      setNotifications(prev => prev.map(item => item.id === n.id ? { ...item, is_read: true } : item))
      try {
        await api.markNotificationAsRead(n.id)
      } catch (e) {
        console.error("Bildirim okundu işaretlenemedi:", e)
      }
    }
    
    if (n.link_url) {
      navigate(n.link_url)
    }
  }

  /**
   * Okunmamış tüm bildirimleri tek seferde temizler.
   */
  const handleMarkAllAsRead = async () => {
    setUnreadCount(0)
    setNotifications(prev => prev.map(item => ({ ...item, is_read: true })))
    try {
      await api.markAllNotificationsAsRead()
    } catch (e) {
      console.error("Bildirimler topluca okundu işaretlenemedi:", e)
    }
  }

  return (
    <div className="relative" ref={dropdownRef}>
      <button
        type="button"
        onClick={() => setIsOpen(!isOpen)}
        aria-label="Bildirimleri görüntüle"
        className={`relative flex h-9 w-9 items-center justify-center rounded-xl border bg-slate-900/50 shadow-sm backdrop-blur-sm transition ${
          isOpen ? 'border-brandBlue text-brandBlue' : 'border-white/10 text-slate-400 hover:border-white/20 hover:bg-white/10 hover:text-white'
        }`}
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
        {unreadCount > 0 && (
          <span
            className="absolute -right-1 -top-1 flex h-4 w-4 items-center justify-center rounded-full bg-[#4b7be5] text-[9px] font-bold text-white shadow-[0_0_8px_rgba(75,123,229,0.5)] ring-2 ring-slate-950"
            aria-label={`${unreadCount} okunmamış bildirim`}
          >
            {unreadCount > 9 ? '9+' : unreadCount}
          </span>
        )}
      </button>

      {isOpen && (
        <div className="absolute right-0 mt-2 w-80 overflow-hidden rounded-2xl border border-white/10 bg-slate-900/95 shadow-2xl backdrop-blur-xl z-50">
          <div className="border-b border-white/10 px-4 py-3 flex items-center justify-between">
            <h3 className="text-sm font-semibold text-white">Bildirimler</h3>
            {unreadCount > 0 && (
              <span 
                className="text-xs text-[#4b7be5] cursor-pointer hover:underline transition-all"
                onClick={handleMarkAllAsRead}
              >
                Tümünü Okundu İşaretle
              </span>
            )}
          </div>
          <div className="max-h-80 overflow-y-auto custom-scrollbar">
            {notifications.length === 0 ? (
              <div className="p-6 text-center text-sm text-slate-400">
                Hiç bildiriminiz yok.
              </div>
            ) : (
              notifications.map(n => (
                <div 
                  key={n.id} 
                  onClick={() => handleNotificationClick(n)}
                  className={`border-b border-white/5 p-4 transition cursor-pointer relative group
                    ${!n.is_read ? 'bg-[#4b7be5]/5 hover:bg-[#4b7be5]/10' : 'opacity-70 hover:opacity-100 hover:bg-white/5'}
                  `}
                >
                  <div className="flex justify-between items-start mb-1">
                    <h4 className={`text-sm font-medium ${!n.is_read ? 'text-white' : 'text-slate-200'}`}>
                      {n.title}
                    </h4>
                    <span className="text-[10px] text-slate-500 shrink-0 ml-2">
                      {new Date(n.created_at).toLocaleTimeString('tr-TR', { hour: '2-digit', minute: '2-digit' })}
                    </span>
                  </div>
                  <p className="text-xs text-slate-400 leading-relaxed pr-2">{n.description}</p>
                  
                  {/* Okunmamış bildirim neon nokta göstergesi */}
                  {!n.is_read && (
                    <div className="absolute right-3 top-5 h-1.5 w-1.5 rounded-full bg-[#4b7be5] shadow-[0_0_6px_rgba(75,123,229,0.8)]" />
                  )}
                </div>
              ))
            )}
          </div>
          <div className="px-4 py-3 border-t border-white/10 text-center bg-white/[0.02]">
            <a href="/settings/notifications" className="text-xs font-medium text-slate-400 hover:text-white transition">Bildirim Ayarları</a>
          </div>
        </div>
      )}
    </div>
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
  const navigate = useNavigate()
  const [dateStr, setDateStr] = useState<string>(getFormattedDate)
  const { profile, isLoading } = useUser()

  /**
   * Gece yarısı geçişinde tarih etiketini otomatik olarak günceller.
   * Bir sonraki gece yarısına kalan süre hesaplanarak tek bir setTimeout kurulur.
   */
  useEffect(() => {
    // Gece yarısı ANKARA'nın gece yarısı: tarayıcının kendi diliminde
    // hesaplanan bir zamanlayıcı tarihi saatlerce erken ya da geç çevirirdi.
    const timer = setTimeout(() => setDateStr(getFormattedDate()), msUntilLocalMidnight())
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
        <button type="button" onClick={() => navigate('/profile')} className="flex items-center gap-2.5 rounded-xl border border-white/10 bg-slate-900/50 px-3 py-1.5 shadow-sm backdrop-blur-sm hover:bg-slate-800/50 transition-colors cursor-pointer focus:outline-none focus:ring-2 focus:ring-brandBlue/50 text-left">

          {/* Gradient avatar — baş harfler veya iskelet */}
          {isLoading ? (
            <div className="h-6 w-6 animate-pulse rounded-lg bg-slate-800" />
          ) : profile?.profilePictureUrl ? (
            <img src={`${import.meta.env.VITE_API_URL?.replace('/api', '') || 'http://localhost:8000'}${profile.profilePictureUrl}`} alt="Avatar" className="h-6 w-6 rounded-lg object-cover" />
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
              <div className="flex items-center">
                <p className="text-sm font-semibold leading-none text-white">
                  {profile?.fullName ?? 'Kullanıcı'}
                </p>
              </div>
            )}
          </div>
        </button>
      </div>
    </header>
  )
}

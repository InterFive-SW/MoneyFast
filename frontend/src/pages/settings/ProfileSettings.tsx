import { useState, FormEvent, useEffect } from 'react'
import { useUser } from '../../contexts/UserContext'
import { api } from '../../api/client'

/**
 * ProfileSettings — Profil ve Kimlik Bilgileri Ayarları Bileşeni
 *
 * MİMARİ & GÜVENLİK NOTLARI:
 * - KYC ve yasal zorunluluklar gereği (Ad, Soyad, TCKN) gibi veriler
 *   kullanıcı tarafından doğrudan değiştirilemez (salt okunur - read-only).
 * - Kullanıcının iletişim bilgileri (E-posta, Telefon) değiştirilebilir
 *   fakat yetkisiz işlemlere karşı asıl güncelleme backend (auth modülü)
 *   üzerinden yapılır ve yetkilendirilmiş (JWT-Bearer) bir istek gerektirir.
 * - Sadece kullanıcı gerçekten bir veri değişikliği yaptığında (isDirty state'i)
 *   'Kaydet' butonu aktifleşir. Bu yaklaşım gereksiz API çağrılarını engeller.
 */
export default function ProfileSettings() {
  const { profile, refetch } = useUser()

  // Form State
  const [email, setEmail] = useState(profile?.email || '')
  const [phone, setPhone] = useState(profile?.phoneNumber || '')

  // UI Durumları
  const [isLoading, setIsLoading] = useState(false)
  const [status, setStatus] = useState<{ type: 'success' | 'error', message: string } | null>(null)
  
  // Değişiklik olup olmadığını tespit (isDirty)
  const isDirty = email !== (profile?.email || '') || phone !== (profile?.phoneNumber || '')

  // Kullanıcı profili API'den geç gelirse (veya refetch edilirse) state'i senkronize et
  useEffect(() => {
    if (profile) {
      setEmail(profile.email || '')
      setPhone(profile.phoneNumber || '')
    }
  }, [profile])

  const handleProfileSubmit = async (e: FormEvent) => {
    e.preventDefault()
    if (!isDirty) return // Değişiklik yoksa boşuna istek atma

    setIsLoading(true)
    setStatus(null)
    
    try {
      // Merkezi API istemcisi üzerinden profil güncelleme isteği gönderiliyor
      await api.updateProfile({
        email,
        phone_number: phone || undefined,
      })
      await refetch()
      setStatus({ type: 'success', message: 'Profil bilgileriniz başarıyla güncellendi.' })
    } catch (err: any) {
      setStatus({ type: 'error', message: err.response?.data?.detail || 'Profil güncellenirken bir sistem hatası oluştu.' })
    } finally {
      setIsLoading(false)
    }
  }

  return (
    <div>
      <h3 className="text-lg font-semibold text-white mb-6">Profil & Kimlik Bilgileri</h3>
      
      {/* Kullanıcı Geribildirim Uyarıları */}
      {status && (
        <div className={`mb-6 p-4 rounded-xl border text-sm font-medium flex items-start gap-3 ${
          status.type === 'success' 
            ? 'bg-emerald-500/10 border-emerald-500/30 text-emerald-400' 
            : 'bg-rose-500/10 border-rose-500/30 text-rose-400'
        }`}>
          <span>{status.type === 'success' ? '✓' : '⚠'}</span>
          <p>{status.message}</p>
        </div>
      )}

      {/* E-posta Değişim Uyarı Mesajı */}
      {email !== profile?.email && (
        <div className="mb-6 p-4 rounded-xl border border-amber-500/30 bg-amber-500/10 text-amber-400 text-sm font-medium flex items-start gap-3">
          <span>⚠</span>
          <p>
            E-posta adresinizi değiştirmek üzeresiniz. Kaydettiğinizde, yeni adresinize
            bir doğrulama bağlantısı gönderilecektir. Doğrulama yapana kadar eski
            adresiniz geçerli olmaya devam edebilir.
          </p>
        </div>
      )}

      <form onSubmit={handleProfileSubmit} className="space-y-6 max-w-2xl">
        
        {/* Yasal / KYC Bilgileri Alanı (Salt Okunur) */}
        <div className="p-5 rounded-xl border border-white/5 bg-white/5">
          <h4 className="text-sm font-semibold text-white mb-4">Kimlik Doğrulama Bilgileri (KYC)</h4>
          <div className="grid grid-cols-1 md:grid-cols-2 gap-5">
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Ad</label>
              <input 
                type="text" 
                value={profile?.firstName || ''} 
                disabled 
                className="w-full rounded-xl border border-white/5 bg-slate-950/30 px-4 py-2.5 text-slate-400 opacity-80 cursor-not-allowed focus:outline-none"
              />
            </div>
            <div>
              <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">Soyad</label>
              <input 
                type="text" 
                value={profile?.lastName || ''} 
                disabled 
                className="w-full rounded-xl border border-white/5 bg-slate-950/30 px-4 py-2.5 text-slate-400 opacity-80 cursor-not-allowed focus:outline-none"
              />
            </div>
            <div className="md:col-span-2">
              <label className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">T.C. Kimlik No</label>
              <input 
                type="text" 
                value={profile?.tcNo || '***********'} 
                disabled 
                className="w-full rounded-xl border border-white/5 bg-slate-950/30 px-4 py-2.5 text-slate-400 opacity-80 cursor-not-allowed focus:outline-none font-mono"
              />
              <p className="mt-2 text-xs text-slate-500 flex items-center gap-1.5">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2" strokeLinecap="round" strokeLinejoin="round"><circle cx="12" cy="12" r="10"></circle><line x1="12" y1="16" x2="12" y2="12"></line><line x1="12" y1="8" x2="12.01" y2="8"></line></svg>
                Bu bilgileri güncellemek için lütfen Müşteri Hizmetleri ile iletişime geçin.
              </p>
            </div>
          </div>
        </div>

        {/* İletişim Bilgileri (Düzenlenebilir) */}
        <div className="space-y-5 pt-2">
          <div>
            <label htmlFor="emailInput" className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider">E-posta Adresi</label>
            <input 
              id="emailInput"
              type="email" 
              required
              value={email}
              onChange={e => setEmail(e.target.value)}
              className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white placeholder-slate-600 outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all"
            />
          </div>

          <div>
            <label htmlFor="phoneInput" className="block text-xs font-medium text-slate-400 mb-1.5 uppercase tracking-wider flex items-center justify-between">
              <span>Telefon Numarası</span>
              {/* Telefon doğrulanmış kabul ediliyor mock olarak */}
              <span className="text-emerald-400 normal-case flex items-center gap-1">
                <svg width="12" height="12" viewBox="0 0 24 24" fill="none" stroke="currentColor" strokeWidth="2.5" strokeLinecap="round" strokeLinejoin="round"><polyline points="20 6 9 17 4 12"></polyline></svg>
                Doğrulanmış
              </span>
            </label>
            <input 
              id="phoneInput"
              type="tel" 
              value={phone}
              onChange={e => setPhone(e.target.value)}
              placeholder="+90 555 123 45 67"
              className="w-full rounded-xl border border-white/20 bg-slate-950 px-4 py-2.5 text-white placeholder-slate-600 outline-none focus:border-brandBlue focus:ring-1 focus:ring-brandBlue transition-all font-mono"
            />
          </div>
        </div>

        {/* Aksiyon Butonları */}
        <div className="pt-6 border-t border-white/10 flex justify-end">
          <button 
            type="submit" 
            disabled={!isDirty || isLoading}
            className="rounded-xl bg-brandBlue px-6 py-2.5 text-sm font-semibold text-white shadow-sm shadow-brandBlue/30 transition-all hover:bg-brandBlue/90 disabled:opacity-50 disabled:hover:bg-brandBlue disabled:cursor-not-allowed"
          >
            {isLoading ? 'Kaydediliyor...' : 'Değişiklikleri Kaydet'}
          </button>
        </div>
      </form>
    </div>
  )
}
